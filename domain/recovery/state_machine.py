"""
domain/recovery/state_machine.py

Deterministic state machine for RecoveryCase and RecoveryAction lifecycle.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

from domain.shared.enums import RecoveryActionStatus, RecoveryCaseStatus
from domain.shared.errors import InvalidStateTransitionError

# ---------------------------------------------------------------------------
# RecoveryCase state machine
# ---------------------------------------------------------------------------

#: Valid transitions for RecoveryCase.status.
VALID_CASE_TRANSITIONS: dict[RecoveryCaseStatus, frozenset[RecoveryCaseStatus]] = {
    RecoveryCaseStatus.OPEN: frozenset({
        RecoveryCaseStatus.IN_PROGRESS,
        RecoveryCaseStatus.IRRECOVERABLE,  # closed directly if no action possible
        RecoveryCaseStatus.CLOSED,
    }),
    RecoveryCaseStatus.IN_PROGRESS: frozenset({
        RecoveryCaseStatus.RECOVERED,
        RecoveryCaseStatus.IRRECOVERABLE,
        RecoveryCaseStatus.OPEN,            # rollback to OPEN if action fails/cancels
    }),
    RecoveryCaseStatus.RECOVERED: frozenset({
        RecoveryCaseStatus.CLOSED,
    }),
    RecoveryCaseStatus.IRRECOVERABLE: frozenset({
        RecoveryCaseStatus.CLOSED,
    }),
    # CLOSED is terminal.
    RecoveryCaseStatus.CLOSED: frozenset(),
}


def validate_case_transition(
    current: RecoveryCaseStatus,
    next_status: RecoveryCaseStatus,
) -> None:
    """
    Assert that transitioning a RecoveryCase from `current` to `next_status` is valid.

    Raises:
        InvalidStateTransitionError: if the transition is not permitted.
    """
    allowed = VALID_CASE_TRANSITIONS.get(current, frozenset())
    if next_status not in allowed:
        raise InvalidStateTransitionError(
            entity="RecoveryCase",
            from_state=current.value,
            to_state=next_status.value,
        )


# ---------------------------------------------------------------------------
# RecoveryAction state machine
# ---------------------------------------------------------------------------

#: Valid transitions for RecoveryAction.status.
VALID_ACTION_TRANSITIONS: dict[RecoveryActionStatus, frozenset[RecoveryActionStatus]] = {
    RecoveryActionStatus.PROPOSED: frozenset({
        RecoveryActionStatus.PENDING_APPROVAL,
        RecoveryActionStatus.APPROVED,
        RecoveryActionStatus.CANCELLED,
        RecoveryActionStatus.EXPIRED,
        RecoveryActionStatus.SUPERSEDED,
    }),
    RecoveryActionStatus.PENDING_APPROVAL: frozenset({
        RecoveryActionStatus.APPROVED,
        RecoveryActionStatus.CANCELLED,
        RecoveryActionStatus.EXPIRED,
        RecoveryActionStatus.SUPERSEDED,
    }),
    RecoveryActionStatus.APPROVED: frozenset({
        RecoveryActionStatus.EXECUTING,
        RecoveryActionStatus.CANCELLED,
        RecoveryActionStatus.EXPIRED,
        RecoveryActionStatus.SUPERSEDED,
    }),
    RecoveryActionStatus.EXECUTING: frozenset({
        # A retryable executor failure retains the same approved action and
        # idempotency key; the outbox later redelivers that action.
        RecoveryActionStatus.APPROVED,
        RecoveryActionStatus.COMPLETED,
        RecoveryActionStatus.FAILED,
        RecoveryActionStatus.CANCELLED,
        RecoveryActionStatus.EXPIRED,
        RecoveryActionStatus.SUPERSEDED,
    }),
    # Terminal states — no further transitions.
    RecoveryActionStatus.COMPLETED: frozenset(),
    RecoveryActionStatus.FAILED: frozenset(),
    RecoveryActionStatus.CANCELLED: frozenset(),
    RecoveryActionStatus.EXPIRED: frozenset(),
    RecoveryActionStatus.SUPERSEDED: frozenset(),
}


def validate_action_transition(
    current: RecoveryActionStatus,
    next_status: RecoveryActionStatus,
) -> None:
    """
    Assert that transitioning a RecoveryAction from `current` to `next_status` is valid.

    Raises:
        InvalidStateTransitionError: if the transition is not permitted.
    """
    allowed = VALID_ACTION_TRANSITIONS.get(current, frozenset())
    if next_status not in allowed:
        raise InvalidStateTransitionError(
            entity="RecoveryAction",
            from_state=current.value,
            to_state=next_status.value,
        )
