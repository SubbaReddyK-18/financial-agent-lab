"""
tests/unit/test_payment_states.py

Unit tests for the Payment state machine and reconciliation logic.

Tests cover:
- Standard forward state transitions (validate_payment_transition)
- Authoritative event reconciliation (reconcile_payment_state)
- Razorpay-style late-capture and UPI retry reconciliation (FAILED -> CAPTURED)
- Idempotent duplicate event handling
- Strict rejection of financial downgrades (CAPTURED -> FAILED, REFUNDED -> FAILED, etc.)
- Recoverability checks and error detail validation

No I/O. No database. No external services.
"""

import uuid
import pytest

from domain.payments.models import Payment
from domain.payments.state_machine import (
    VALID_PAYMENT_TRANSITIONS,
    is_payment_recoverable,
    reconcile_payment_state,
    validate_payment_transition,
)
from domain.shared.enums import PaymentStatus
from domain.shared.errors import InvalidStateTransitionError


# ---------------------------------------------------------------------------
# Standard forward transitions (validate_payment_transition)
# ---------------------------------------------------------------------------

class TestValidPaymentTransitions:
    def test_created_to_authorized(self):
        validate_payment_transition(PaymentStatus.CREATED, PaymentStatus.AUTHORIZED)

    def test_created_to_failed(self):
        validate_payment_transition(PaymentStatus.CREATED, PaymentStatus.FAILED)

    def test_authorized_to_captured(self):
        validate_payment_transition(PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED)

    def test_authorized_to_failed(self):
        validate_payment_transition(PaymentStatus.AUTHORIZED, PaymentStatus.FAILED)

    def test_captured_to_refunded(self):
        validate_payment_transition(PaymentStatus.CAPTURED, PaymentStatus.REFUNDED)


class TestInvalidPaymentTransitions:
    def test_created_to_captured_invalid_in_forward_machine(self):
        """In strict sequential forward flow, CREATED -> CAPTURED skips AUTHORIZED."""
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            validate_payment_transition(PaymentStatus.CREATED, PaymentStatus.CAPTURED)
        assert "CREATED" in str(exc_info.value)
        assert "CAPTURED" in str(exc_info.value)

    def test_created_to_refunded_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_payment_transition(PaymentStatus.CREATED, PaymentStatus.REFUNDED)

    def test_failed_in_forward_machine_is_terminal(self):
        """Standard forward state-machine does not allow forward transitions from FAILED.
        Reconciliation must be used instead for late gateway events."""
        with pytest.raises(InvalidStateTransitionError):
            validate_payment_transition(PaymentStatus.FAILED, PaymentStatus.AUTHORIZED)
        with pytest.raises(InvalidStateTransitionError):
            validate_payment_transition(PaymentStatus.FAILED, PaymentStatus.CAPTURED)

    def test_refunded_to_any_is_invalid(self):
        """REFUNDED is terminal in forward machine."""
        for target in PaymentStatus:
            with pytest.raises(InvalidStateTransitionError):
                validate_payment_transition(PaymentStatus.REFUNDED, target)

    def test_captured_to_created_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_payment_transition(PaymentStatus.CAPTURED, PaymentStatus.CREATED)

    def test_failed_to_failed_invalid_in_forward_machine(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_payment_transition(PaymentStatus.FAILED, PaymentStatus.FAILED)

    def test_authorized_to_created_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_payment_transition(PaymentStatus.AUTHORIZED, PaymentStatus.CREATED)


# ---------------------------------------------------------------------------
# Authoritative event reconciliation (reconcile_payment_state)
# ---------------------------------------------------------------------------

class TestPaymentReconciliation:
    def test_failed_to_captured_through_reconciliation_valid(self):
        """1. FAILED -> CAPTURED through reconciliation = valid (e.g. Razorpay late capture / UPI retry)."""
        res = reconcile_payment_state(PaymentStatus.FAILED, PaymentStatus.CAPTURED)
        assert res.target_status == PaymentStatus.CAPTURED
        assert res.state_changed is True
        assert res.is_reconciled_from_failed is True

    def test_failed_to_authorized_through_reconciliation_valid(self):
        """2. FAILED -> AUTHORIZED through reconciliation = valid (e.g. late authorization)."""
        res = reconcile_payment_state(PaymentStatus.FAILED, PaymentStatus.AUTHORIZED)
        assert res.target_status == PaymentStatus.AUTHORIZED
        assert res.state_changed is True
        assert res.is_reconciled_from_failed is True

    def test_authorized_to_captured_through_reconciliation_valid(self):
        """3. AUTHORIZED -> CAPTURED = valid."""
        res = reconcile_payment_state(PaymentStatus.AUTHORIZED, PaymentStatus.CAPTURED)
        assert res.target_status == PaymentStatus.CAPTURED
        assert res.state_changed is True
        assert res.is_reconciled_from_failed is False

    def test_captured_to_failed_reconciliation_invalid(self):
        """4. CAPTURED -> FAILED = invalid (downgrade forbidden)."""
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            reconcile_payment_state(PaymentStatus.CAPTURED, PaymentStatus.FAILED)
        assert "CAPTURED" in str(exc_info.value)
        assert "FAILED" in str(exc_info.value)

    def test_captured_to_authorized_reconciliation_invalid(self):
        """5. CAPTURED -> AUTHORIZED = invalid (downgrade forbidden)."""
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.CAPTURED, PaymentStatus.AUTHORIZED)

    def test_refunded_to_failed_reconciliation_invalid(self):
        """6. REFUNDED -> FAILED = invalid (downgrade forbidden)."""
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.REFUNDED, PaymentStatus.FAILED)

    def test_refunded_to_captured_reconciliation_invalid(self):
        """7. REFUNDED -> CAPTURED = invalid (un-refund forbidden)."""
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.REFUNDED, PaymentStatus.CAPTURED)

    def test_repeated_captured_is_idempotent(self):
        """8. repeated CAPTURED remains idempotent / safely handled without state change."""
        res = reconcile_payment_state(PaymentStatus.CAPTURED, PaymentStatus.CAPTURED)
        assert res.target_status == PaymentStatus.CAPTURED
        assert res.state_changed is False
        assert res.is_reconciled_from_failed is False

    def test_repeated_authorized_is_idempotent(self):
        res = reconcile_payment_state(PaymentStatus.AUTHORIZED, PaymentStatus.AUTHORIZED)
        assert res.target_status == PaymentStatus.AUTHORIZED
        assert res.state_changed is False

    def test_repeated_failed_is_idempotent(self):
        res = reconcile_payment_state(PaymentStatus.FAILED, PaymentStatus.FAILED)
        assert res.target_status == PaymentStatus.FAILED
        assert res.state_changed is False

    def test_repeated_refunded_is_idempotent(self):
        res = reconcile_payment_state(PaymentStatus.REFUNDED, PaymentStatus.REFUNDED)
        assert res.target_status == PaymentStatus.REFUNDED
        assert res.state_changed is False

    def test_reconciliation_does_not_allow_arbitrary_resets(self):
        """10. Reconciliation does not allow resetting to CREATED or invalid jumps."""
        # Cannot reset to CREATED from any subsequent state
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.FAILED, PaymentStatus.CREATED)
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.AUTHORIZED, PaymentStatus.CREATED)
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.CAPTURED, PaymentStatus.CREATED)
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.REFUNDED, PaymentStatus.CREATED)
        # Cannot jump to REFUNDED without being CAPTURED
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.CREATED, PaymentStatus.REFUNDED)
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.AUTHORIZED, PaymentStatus.REFUNDED)
        with pytest.raises(InvalidStateTransitionError):
            reconcile_payment_state(PaymentStatus.FAILED, PaymentStatus.REFUNDED)


# ---------------------------------------------------------------------------
# Razorpay-style scenario test
# ---------------------------------------------------------------------------

class TestRazorpayScenario:
    def test_razorpay_failed_then_late_captured_scenario(self):
        """
        Demonstrates the exact Razorpay-style scenario:
        1. Payment is created (CREATED)
        2. Payment failure webhook/event observed (transitioned to FAILED)
        3. Customer initiates UPI retry or bank confirms late capture (incoming event = CAPTURED)
        4. Reconciled payment state correctly updates to CAPTURED
        """
        payment = Payment(
            order_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            amount_minor=125050,  # ₹1,250.50
            currency="INR",
            status=PaymentStatus.CREATED,
        )
        assert payment.status == PaymentStatus.CREATED

        # Step 1: Initial failure event observed
        rec1 = reconcile_payment_state(payment.status, PaymentStatus.FAILED)
        payment.status = rec1.target_status
        assert payment.status == PaymentStatus.FAILED
        assert payment.is_failed() is True

        # Step 2: Later authoritative CAPTURED event arrives (e.g. UPI retry / late bank capture)
        rec2 = reconcile_payment_state(payment.status, PaymentStatus.CAPTURED)
        assert rec2.is_reconciled_from_failed is True
        assert rec2.state_changed is True

        payment.status = rec2.target_status
        assert payment.status == PaymentStatus.CAPTURED
        assert payment.is_captured() is True
        assert payment.is_terminal() is True

    def test_razorpay_failed_then_late_auth_then_captured_scenario(self):
        """
        Demonstrates:
        1. Payment FAILED
        2. Late AUTHORIZED event arrives -> reconciled to AUTHORIZED
        3. Subsequent CAPTURED event arrives -> reconciled to CAPTURED
        """
        payment = Payment(
            order_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            amount_minor=500000,
            currency="INR",
            status=PaymentStatus.FAILED,
        )

        # Step 1: Late auth
        rec1 = reconcile_payment_state(payment.status, PaymentStatus.AUTHORIZED)
        payment.status = rec1.target_status
        assert payment.status == PaymentStatus.AUTHORIZED
        assert rec1.is_reconciled_from_failed is True

        # Step 2: Capture
        rec2 = reconcile_payment_state(payment.status, PaymentStatus.CAPTURED)
        payment.status = rec2.target_status
        assert payment.status == PaymentStatus.CAPTURED
        assert rec2.is_reconciled_from_failed is False


# ---------------------------------------------------------------------------
# Terminal and recoverability checks
# ---------------------------------------------------------------------------

class TestTerminalStates:
    def test_failed_has_no_allowed_forward_transitions(self):
        assert VALID_PAYMENT_TRANSITIONS[PaymentStatus.FAILED] == frozenset()

    def test_refunded_has_no_allowed_forward_transitions(self):
        assert VALID_PAYMENT_TRANSITIONS[PaymentStatus.REFUNDED] == frozenset()

    def test_all_statuses_are_in_transition_map(self):
        """Every PaymentStatus must have an entry in the transition graph."""
        for status in PaymentStatus:
            assert status in VALID_PAYMENT_TRANSITIONS, (
                f"{status!r} is not in VALID_PAYMENT_TRANSITIONS — "
                "add it with an empty frozenset() if terminal."
            )


class TestPaymentRecoverability:
    def test_failed_payment_is_recoverable(self):
        assert is_payment_recoverable(PaymentStatus.FAILED) is True

    def test_captured_payment_is_not_recoverable(self):
        assert is_payment_recoverable(PaymentStatus.CAPTURED) is False

    def test_refunded_payment_is_not_recoverable(self):
        assert is_payment_recoverable(PaymentStatus.REFUNDED) is False

    def test_created_payment_is_not_recoverable(self):
        assert is_payment_recoverable(PaymentStatus.CREATED) is False

    def test_authorized_payment_is_not_recoverable(self):
        assert is_payment_recoverable(PaymentStatus.AUTHORIZED) is False


class TestStateTransitionErrorDetails:
    def test_error_contains_entity_name(self):
        with pytest.raises(InvalidStateTransitionError) as exc_info:
            validate_payment_transition(PaymentStatus.CREATED, PaymentStatus.REFUNDED)
        err = exc_info.value
        assert err.entity == "Payment"
        assert err.from_state == "CREATED"
        assert err.to_state == "REFUNDED"
