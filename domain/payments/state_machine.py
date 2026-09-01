"""
domain/payments/state_machine.py

Deterministic state machine for Payment and PaymentAttempt lifecycle,
including authoritative event reconciliation.

ARCHITECTURAL PRINCIPLES (P-01, P-03, FS-06):
    State transition validation is DETERMINISTIC. It does not call any LLM.
    All state changes must pass through these validators before being applied.

LATE / OUT-OF-ORDER EVENTS & RECONCILIATION:
    Webhook/event arrival order is not automatically equivalent to financial state truth.
    In real-world payment flows (e.g. Razorpay UPI user-initiated retries, late bank
    authorizations, or delayed webhook delivery), a payment initially observed as FAILED
    may later be superseded by an authoritative CAPTURED or AUTHORIZED event.

    This module cleanly separates:
    1. `validate_payment_transition(...)` — strict sequential forward lifecycle validation.
    2. `reconcile_payment_state(...)` — authoritative event reconciliation that handles
       superseding states (e.g. FAILED -> CAPTURED), idempotent duplicates, and strictly
       rejects invalid state downgrades (e.g. CAPTURED -> FAILED).

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.shared.enums import (
    PaymentAttemptStatus,
    PaymentStatus,
)
from domain.shared.errors import InvalidStateTransitionError

# ---------------------------------------------------------------------------
# Payment forward transition graph (normal sequential workflow)
# ---------------------------------------------------------------------------

#: Valid forward transitions for Payment.status in normal sequential workflow.
#: Format: {current_status: {allowed_next_statuses}}
VALID_PAYMENT_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.CREATED: frozenset({
        PaymentStatus.AUTHORIZED,
        PaymentStatus.FAILED,
    }),
    PaymentStatus.AUTHORIZED: frozenset({
        PaymentStatus.CAPTURED,
        PaymentStatus.FAILED,
    }),
    PaymentStatus.CAPTURED: frozenset({
        PaymentStatus.REFUNDED,
    }),
    # In strict forward progression, FAILED and REFUNDED have no forward path.
    # Out-of-order and late authoritative events must use reconcile_payment_state().
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


def validate_payment_transition(
    current: PaymentStatus,
    next_status: PaymentStatus,
) -> None:
    """
    Assert that transitioning a Payment from `current` to `next_status` is valid
    under standard forward sequential progression.

    Raises:
        InvalidStateTransitionError: if the transition is not in the allowed forward graph.

    Note:
        For handling incoming authoritative events (such as late captures on earlier
        failed payments, out-of-order webhooks, or duplicate deliveries), use
        `reconcile_payment_state(...)`.
    """
    allowed = VALID_PAYMENT_TRANSITIONS.get(current, frozenset())
    if next_status not in allowed:
        raise InvalidStateTransitionError(
            entity="Payment",
            from_state=current.value,
            to_state=next_status.value,
        )


# ---------------------------------------------------------------------------
# Authoritative payment state reconciliation
# ---------------------------------------------------------------------------

#: Allowed transitions when reconciling an authoritative incoming payment event.
#: Enforces that:
#: - Idempotent duplicates are allowed (current == incoming)
#: - Normal progressive transitions are allowed
#: - FAILED state can be superseded by AUTHORIZED or CAPTURED (late capture / retry)
#: - Financial downgrades are FORBIDDEN (CAPTURED/REFUNDED cannot become FAILED)
RECONCILIATION_ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.CREATED: frozenset({
        PaymentStatus.CREATED,     # idempotent
        PaymentStatus.AUTHORIZED,  # normal progression
        PaymentStatus.CAPTURED,    # direct capture
        PaymentStatus.FAILED,      # failure
    }),
    PaymentStatus.AUTHORIZED: frozenset({
        PaymentStatus.AUTHORIZED,  # idempotent
        PaymentStatus.CAPTURED,    # normal progression
        PaymentStatus.FAILED,      # late auth failure / expiration
    }),
    PaymentStatus.FAILED: frozenset({
        PaymentStatus.FAILED,      # idempotent
        PaymentStatus.AUTHORIZED,  # late authorization (supersedes failed)
        PaymentStatus.CAPTURED,    # late capture / UPI retry (supersedes failed)
    }),
    PaymentStatus.CAPTURED: frozenset({
        PaymentStatus.CAPTURED,    # idempotent
        PaymentStatus.REFUNDED,    # normal refund
    }),
    PaymentStatus.REFUNDED: frozenset({
        PaymentStatus.REFUNDED,    # idempotent
    }),
}


@dataclass(frozen=True)
class PaymentReconciliationResult:
    """
    Immutable result of reconciling an incoming authoritative payment event.

    Attributes:
        target_status:
            The authoritative resulting PaymentStatus.
        state_changed:
            True if the incoming event updated the system state;
            False if it was an idempotent duplicate / no-op.
        is_reconciled_from_failed:
            True if an earlier observed FAILED state was superseded by a later
            authoritative success state (e.g. FAILED -> CAPTURED).
    """

    target_status: PaymentStatus
    state_changed: bool
    is_reconciled_from_failed: bool = False


def reconcile_payment_state(
    current: PaymentStatus,
    incoming: PaymentStatus,
) -> PaymentReconciliationResult:
    """
    Deterministically reconcile an incoming authoritative payment state against
    the current stored payment state.

    Guarantees:
    1. Idempotent delivery: if `current == incoming`, returns `state_changed=False`.
    2. Event superseding: if `current == FAILED` and `incoming` is `CAPTURED` or `AUTHORIZED`,
       the authoritative event supersedes the failure (`is_reconciled_from_failed=True`).
    3. Downgrade protection: strictly rejects attempts to downgrade terminal/final states
       (e.g. CAPTURED -> FAILED, REFUNDED -> FAILED, CAPTURED -> AUTHORIZED).
    4. Arbitrary state reset protection: strictly rejects resetting to CREATED from any
       subsequent state.

    Args:
        current: The existing recorded PaymentStatus in our system.
        incoming: The incoming authoritative PaymentStatus (e.g. from gateway event/API).

    Returns:
        PaymentReconciliationResult with the resulting status and metadata.

    Raises:
        InvalidStateTransitionError: if the transition violates reconciliation rules.
    """
    allowed = RECONCILIATION_ALLOWED_TRANSITIONS.get(current, frozenset())
    if incoming not in allowed:
        raise InvalidStateTransitionError(
            entity="Payment",
            from_state=current.value,
            to_state=incoming.value,
        )

    # Case 1: Idempotent duplicate event
    if current == incoming:
        return PaymentReconciliationResult(
            target_status=current,
            state_changed=False,
            is_reconciled_from_failed=False,
        )

    # Case 2: Later authoritative success superseding an earlier observed failure
    if current == PaymentStatus.FAILED and incoming in {PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED}:
        return PaymentReconciliationResult(
            target_status=incoming,
            state_changed=True,
            is_reconciled_from_failed=True,
        )

    # Case 3: Standard state progression
    return PaymentReconciliationResult(
        target_status=incoming,
        state_changed=True,
        is_reconciled_from_failed=False,
    )


def is_payment_recoverable(status: PaymentStatus) -> bool:
    """
    Return True if this payment status makes the payment eligible for recovery.

    A FAILED payment can be recovered. CAPTURED/REFUNDED cannot.
    CREATED/AUTHORIZED payments that are stuck could also be candidates
    (handled in future blocks via timeout detection).
    """
    return status == PaymentStatus.FAILED


# ---------------------------------------------------------------------------
# PaymentAttempt state machine
# ---------------------------------------------------------------------------

#: Valid transitions for PaymentAttempt.status.
VALID_ATTEMPT_TRANSITIONS: dict[PaymentAttemptStatus, frozenset[PaymentAttemptStatus]] = {
    PaymentAttemptStatus.PENDING: frozenset({
        PaymentAttemptStatus.SUCCESS,
        PaymentAttemptStatus.FAILED,
        PaymentAttemptStatus.TIMEOUT,
    }),
    # All non-PENDING statuses are terminal for an attempt.
    PaymentAttemptStatus.SUCCESS: frozenset(),
    PaymentAttemptStatus.FAILED: frozenset(),
    PaymentAttemptStatus.TIMEOUT: frozenset(),
}


def validate_attempt_transition(
    current: PaymentAttemptStatus,
    next_status: PaymentAttemptStatus,
) -> None:
    """
    Assert that transitioning a PaymentAttempt from `current` to `next_status` is valid.

    Raises:
        InvalidStateTransitionError: if the transition is not in the allowed graph.
    """
    allowed = VALID_ATTEMPT_TRANSITIONS.get(current, frozenset())
    if next_status not in allowed:
        raise InvalidStateTransitionError(
            entity="PaymentAttempt",
            from_state=current.value,
            to_state=next_status.value,
        )


def next_attempt_number(existing_attempt_numbers: list[int]) -> int:
    """
    Return the next sequential attempt number given existing attempt numbers.

    Args:
        existing_attempt_numbers: List of attempt_number values already recorded
                                  for this payment. May be empty.

    Returns:
        Next attempt number (1-indexed).
    """
    if not existing_attempt_numbers:
        return 1
    return max(existing_attempt_numbers) + 1
