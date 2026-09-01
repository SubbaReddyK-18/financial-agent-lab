"""
tests/unit/test_payment_attempts.py

Unit tests for PaymentAttempt domain entity.

Tests cover: attempt creation, attempt numbering, multiple attempts,
failed attempt field validation, and attempt state machine.

No I/O. No database. No external services.
"""

import uuid

import pytest

from domain.payments.models import PaymentAttempt
from domain.payments.state_machine import (
    next_attempt_number,
    validate_attempt_transition,
)
from domain.shared.enums import PaymentAttemptStatus
from domain.shared.errors import InvalidStateTransitionError


class TestPaymentAttemptConstruction:
    def test_first_attempt(self):
        attempt = PaymentAttempt(
            payment_id=uuid.uuid4(),
            attempt_number=1,
            status=PaymentAttemptStatus.PENDING,
        )
        assert attempt.attempt_number == 1
        assert attempt.status == PaymentAttemptStatus.PENDING
        assert attempt.failure_code is None
        assert attempt.failure_reason is None

    def test_attempt_number_zero_rejected(self):
        with pytest.raises(ValueError, match="attempt_number"):
            PaymentAttempt(
                payment_id=uuid.uuid4(),
                attempt_number=0,
            )

    def test_attempt_number_negative_rejected(self):
        with pytest.raises(ValueError):
            PaymentAttempt(
                payment_id=uuid.uuid4(),
                attempt_number=-1,
            )

    def test_failure_fields_on_failed_attempt(self):
        attempt = PaymentAttempt(
            payment_id=uuid.uuid4(),
            attempt_number=1,
            status=PaymentAttemptStatus.FAILED,
            failure_code="INSUFFICIENT_FUNDS",
            failure_reason="Card declined: insufficient funds.",
        )
        assert attempt.failure_code == "INSUFFICIENT_FUNDS"
        assert attempt.failure_reason == "Card declined: insufficient funds."

    def test_failure_fields_on_non_failed_attempt_rejected(self):
        """failure_code must be None unless status is FAILED."""
        with pytest.raises(ValueError):
            PaymentAttempt(
                payment_id=uuid.uuid4(),
                attempt_number=1,
                status=PaymentAttemptStatus.PENDING,
                failure_code="SOME_CODE",
            )

    def test_failure_reason_on_non_failed_attempt_rejected(self):
        with pytest.raises(ValueError):
            PaymentAttempt(
                payment_id=uuid.uuid4(),
                attempt_number=1,
                status=PaymentAttemptStatus.SUCCESS,
                failure_reason="Should not be set",
            )

    def test_auto_uuid_generation(self):
        attempt = PaymentAttempt(payment_id=uuid.uuid4(), attempt_number=1)
        assert isinstance(attempt.id, uuid.UUID)


class TestMultipleAttempts:
    def test_multiple_attempts_have_sequential_numbers(self):
        payment_id = uuid.uuid4()
        attempts = [
            PaymentAttempt(payment_id=payment_id, attempt_number=n)
            for n in range(1, 4)
        ]
        numbers = [a.attempt_number for a in attempts]
        assert numbers == [1, 2, 3]

    def test_attempts_have_unique_ids(self):
        payment_id = uuid.uuid4()
        attempts = [
            PaymentAttempt(payment_id=payment_id, attempt_number=n)
            for n in range(1, 4)
        ]
        ids = {a.id for a in attempts}
        assert len(ids) == 3

    def test_failed_then_successful_attempt(self):
        payment_id = uuid.uuid4()
        first = PaymentAttempt(
            payment_id=payment_id,
            attempt_number=1,
            status=PaymentAttemptStatus.FAILED,
            failure_code="TIMEOUT",
            failure_reason="Gateway timeout.",
        )
        second = PaymentAttempt(
            payment_id=payment_id,
            attempt_number=2,
            status=PaymentAttemptStatus.SUCCESS,
        )
        assert first.status == PaymentAttemptStatus.FAILED
        assert second.status == PaymentAttemptStatus.SUCCESS
        assert second.attempt_number == first.attempt_number + 1


class TestNextAttemptNumber:
    def test_first_attempt_when_empty(self):
        assert next_attempt_number([]) == 1

    def test_next_after_one(self):
        assert next_attempt_number([1]) == 2

    def test_next_after_multiple(self):
        assert next_attempt_number([1, 2, 3]) == 4

    def test_next_handles_gaps(self):
        # If somehow there's a gap (shouldn't happen in normal flow),
        # we take max + 1 to avoid collisions.
        assert next_attempt_number([1, 3]) == 4


class TestAttemptStateMachine:
    def test_pending_to_success(self):
        validate_attempt_transition(
            PaymentAttemptStatus.PENDING, PaymentAttemptStatus.SUCCESS
        )

    def test_pending_to_failed(self):
        validate_attempt_transition(
            PaymentAttemptStatus.PENDING, PaymentAttemptStatus.FAILED
        )

    def test_pending_to_timeout(self):
        validate_attempt_transition(
            PaymentAttemptStatus.PENDING, PaymentAttemptStatus.TIMEOUT
        )

    def test_success_to_anything_invalid(self):
        for target in PaymentAttemptStatus:
            with pytest.raises(InvalidStateTransitionError):
                validate_attempt_transition(PaymentAttemptStatus.SUCCESS, target)

    def test_failed_to_anything_invalid(self):
        for target in PaymentAttemptStatus:
            with pytest.raises(InvalidStateTransitionError):
                validate_attempt_transition(PaymentAttemptStatus.FAILED, target)


class TestAttemptIsTerminal:
    def test_success_is_terminal(self):
        a = PaymentAttempt(
            payment_id=uuid.uuid4(),
            attempt_number=1,
            status=PaymentAttemptStatus.SUCCESS,
        )
        assert a.is_terminal()

    def test_pending_is_not_terminal(self):
        a = PaymentAttempt(payment_id=uuid.uuid4(), attempt_number=1)
        assert not a.is_terminal()
