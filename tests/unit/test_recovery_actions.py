"""
tests/unit/test_recovery_actions.py

Unit tests for RecoveryAction domain entity and action state machine.

Tests cover: action creation, valid action types, state transitions,
terminal states, and discount validation.

No I/O. No database. No external services.
"""

import uuid

import pytest

from domain.recovery.models import RecoveryAction
from domain.recovery.state_machine import validate_action_transition
from domain.shared.enums import RecoveryActionStatus, RecoveryActionType
from domain.shared.errors import InvalidStateTransitionError


class TestRecoveryActionConstruction:
    def test_wait_action(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.WAIT,
        )
        assert action.action_type == RecoveryActionType.WAIT
        assert action.status == RecoveryActionStatus.PROPOSED
        assert action.discount_percent_offered == 0

    def test_retry_action(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.RETRY,
        )
        assert action.action_type == RecoveryActionType.RETRY

    def test_payment_link_action_with_discount(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.PAYMENT_LINK,
            discount_percent_offered=10,
        )
        assert action.discount_percent_offered == 10

    def test_notify_action(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.NOTIFY,
            metadata={"channel": "sms", "template": "payment_failed_v1"},
        )
        assert action.metadata["channel"] == "sms"

    def test_escalate_action(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.ESCALATE,
        )
        assert action.action_type == RecoveryActionType.ESCALATE

    def test_all_action_types_are_constructible(self):
        for action_type in RecoveryActionType:
            action = RecoveryAction(
                recovery_case_id=uuid.uuid4(),
                action_type=action_type,
            )
            assert action.action_type == action_type

    def test_discount_above_100_rejected(self):
        with pytest.raises(ValueError, match="discount"):
            RecoveryAction(
                recovery_case_id=uuid.uuid4(),
                action_type=RecoveryActionType.PAYMENT_LINK,
                discount_percent_offered=101,
            )

    def test_negative_discount_rejected(self):
        with pytest.raises(ValueError):
            RecoveryAction(
                recovery_case_id=uuid.uuid4(),
                action_type=RecoveryActionType.PAYMENT_LINK,
                discount_percent_offered=-1,
            )

    def test_executed_at_not_set_when_proposed(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.RETRY,
        )
        assert action.executed_at is None

    def test_cannot_set_executed_at_with_proposed_status(self):
        from datetime import datetime, timezone
        with pytest.raises(ValueError, match="executed_at"):
            RecoveryAction(
                recovery_case_id=uuid.uuid4(),
                action_type=RecoveryActionType.RETRY,
                status=RecoveryActionStatus.PROPOSED,
                executed_at=datetime.now(tz=timezone.utc),
            )


class TestRecoveryActionStateMachine:
    def test_proposed_to_approved(self):
        validate_action_transition(
            RecoveryActionStatus.PROPOSED, RecoveryActionStatus.APPROVED
        )

    def test_proposed_to_cancelled(self):
        validate_action_transition(
            RecoveryActionStatus.PROPOSED, RecoveryActionStatus.CANCELLED
        )

    def test_approved_to_executing(self):
        validate_action_transition(
            RecoveryActionStatus.APPROVED, RecoveryActionStatus.EXECUTING
        )

    def test_approved_to_cancelled(self):
        validate_action_transition(
            RecoveryActionStatus.APPROVED, RecoveryActionStatus.CANCELLED
        )

    def test_executing_to_completed(self):
        validate_action_transition(
            RecoveryActionStatus.EXECUTING, RecoveryActionStatus.COMPLETED
        )

    def test_executing_to_failed(self):
        validate_action_transition(
            RecoveryActionStatus.EXECUTING, RecoveryActionStatus.FAILED
        )

    def test_completed_is_terminal(self):
        for target in RecoveryActionStatus:
            with pytest.raises(InvalidStateTransitionError):
                validate_action_transition(RecoveryActionStatus.COMPLETED, target)

    def test_failed_is_terminal(self):
        for target in RecoveryActionStatus:
            with pytest.raises(InvalidStateTransitionError):
                validate_action_transition(RecoveryActionStatus.FAILED, target)

    def test_cancelled_is_terminal(self):
        for target in RecoveryActionStatus:
            with pytest.raises(InvalidStateTransitionError):
                validate_action_transition(RecoveryActionStatus.CANCELLED, target)

    def test_proposed_to_executing_invalid(self):
        """Must go through APPROVED before EXECUTING."""
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(
                RecoveryActionStatus.PROPOSED, RecoveryActionStatus.EXECUTING
            )

    def test_proposed_to_completed_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(
                RecoveryActionStatus.PROPOSED, RecoveryActionStatus.COMPLETED
            )


class TestRecoveryActionIsTerminal:
    def test_completed_is_terminal(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.WAIT,
            status=RecoveryActionStatus.COMPLETED,
        )
        assert action.is_terminal()

    def test_proposed_is_not_terminal(self):
        action = RecoveryAction(
            recovery_case_id=uuid.uuid4(),
            action_type=RecoveryActionType.WAIT,
        )
        assert not action.is_terminal()
