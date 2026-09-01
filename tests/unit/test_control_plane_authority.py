"""Execution-time policy and retry invariants for the recovery control plane."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.intelligence.models.context import CustomerProfile, PaymentFailureDetails, RecoveryContext
from domain.policies.models import MerchantRecoveryPolicy
from domain.recovery.control_plane import RecoveryActionControlPlane
from domain.recovery.execution import ActionExecutionResult
from domain.shared.enums import RecoveryActionType


def _approved_action() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(), recovery_case_id=uuid.uuid4(), action_type="NOTIFY",
        status="APPROVED", created_at=datetime.now(tz=timezone.utc),
        discount_percent_offered=0, metadata_json={}, retry_count=0, max_retries=3,
        next_retry_at=None, failure_reason=None,
    )


def _case_and_payment(action):
    case = SimpleNamespace(
        id=action.recovery_case_id, merchant_id=uuid.uuid4(), customer_id=uuid.uuid4(),
        payment_id=uuid.uuid4(), amount_at_risk_minor=10_000, status="OPEN",
        opened_at=datetime.now(tz=timezone.utc), closed_at=None,
    )
    payment = SimpleNamespace(id=case.payment_id, status="FAILED")
    return case, payment


def _policy(case, **overrides):
    data = dict(
        merchant_id=case.merchant_id, maximum_discount_percent=10,
        maximum_interventions=3, cooldown_hours=0,
        high_value_threshold_minor=None, high_value_requires_approval=False,
        low_confidence_requires_review=False,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


def _context(case):
    return RecoveryContext(
        payment=PaymentFailureDetails(payment_id=case.payment_id, amount_minor=10_000,
                                      attempt_count=1, failure_code="TIMEOUT"),
        customer=CustomerProfile(customer_id=case.customer_id),
        policy=MerchantRecoveryPolicy(merchant_id=case.merchant_id, cooldown_hours=0),
    )


def _session(values):
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=values)
    session.flush = AsyncMock()
    return session


@pytest.mark.asyncio
async def test_execution_time_policy_violation_cancels_action_and_dispatch(monkeypatch):
    action = _approved_action()
    action.discount_percent_offered = 25
    case, payment = _case_and_payment(action)
    outbox = SimpleNamespace(status="PROCESSING", processed_at=None, error_message=None)
    session = _session([action, case, payment, None, _policy(case), 0, None, outbox])
    executor = MagicMock()
    monkeypatch.setattr("domain.recovery.control_plane.get_action_executor", executor)

    result = await RecoveryActionControlPlane().dispatch_action(action.id, session, context=_context(case))

    assert result.status == "CANCELLED"
    assert result.error_code == "POLICY_REVALIDATION_FAILED"
    assert action.status == "CANCELLED"
    assert outbox.status == "CANCELLED"
    executor.assert_not_called()


@pytest.mark.asyncio
async def test_execution_time_missing_required_approval_cancels_action(monkeypatch):
    action = _approved_action()
    case, payment = _case_and_payment(action)
    outbox = SimpleNamespace(status="PROCESSING", processed_at=None, error_message=None)
    session = _session([
        action, case, payment, None,
        _policy(case, high_value_threshold_minor=1, high_value_requires_approval=True),
        0, None, None, outbox,
    ])
    executor = MagicMock()
    monkeypatch.setattr("domain.recovery.control_plane.get_action_executor", executor)

    result = await RecoveryActionControlPlane().dispatch_action(action.id, session, context=_context(case))

    assert result.status == "CANCELLED"
    assert result.error_code == "AUTHORIZATION_REVALIDATION_FAILED"
    assert action.status == "CANCELLED"
    assert outbox.status == "CANCELLED"
    executor.assert_not_called()


@pytest.mark.asyncio
async def test_retryable_failure_reuses_same_approved_action_and_reschedules_outbox(monkeypatch):
    now = datetime.now(tz=timezone.utc)
    action = _approved_action()
    case, payment = _case_and_payment(action)
    outbox = SimpleNamespace(status="PROCESSING", attempt_count=1, max_attempts=3,
                             next_attempt_at=None, processed_at=None, error_message=None)
    session = _session([action, case, payment, None, _policy(case), 0, None, outbox, outbox, outbox])
    failure = ActionExecutionResult(action_id=action.id, action_type=RecoveryActionType.NOTIFY,
                                    status="FAILED", execution_reference="test-failure",
                                    is_retryable=True, error_message="temporary", error_code="TEMP",
                                    executed_at=now)
    monkeypatch.setattr("domain.recovery.control_plane.get_action_executor", lambda _: SimpleNamespace(execute=AsyncMock(return_value=failure)))

    result = await RecoveryActionControlPlane().dispatch_action(action.id, session, context=_context(case), now=now)

    assert result is failure
    assert action.status == "APPROVED"
    assert action.retry_count == 1
    assert action.next_retry_at == now + timedelta(seconds=20)
    assert outbox.status == "PENDING"
    assert outbox.attempt_count == 1
    assert outbox.next_attempt_at == action.next_retry_at


@pytest.mark.asyncio
async def test_terminal_failure_cannot_retain_pending_or_processing_outbox(monkeypatch):
    now = datetime.now(tz=timezone.utc)
    action = _approved_action()
    case, payment = _case_and_payment(action)
    outbox = SimpleNamespace(status="PROCESSING", attempt_count=3, max_attempts=3,
                             next_attempt_at=None, processed_at=None, error_message=None)
    session = _session([action, case, payment, None, _policy(case), 0, None, outbox, outbox, outbox])
    failure = ActionExecutionResult(action_id=action.id, action_type=RecoveryActionType.NOTIFY,
                                    status="FAILED", execution_reference="test-failure",
                                    is_retryable=True, error_message="exhausted", error_code="TEMP",
                                    executed_at=now)
    monkeypatch.setattr("domain.recovery.control_plane.get_action_executor", lambda _: SimpleNamespace(execute=AsyncMock(return_value=failure)))

    await RecoveryActionControlPlane().dispatch_action(action.id, session, context=_context(case), now=now)

    assert action.status == "FAILED"
    assert outbox.status == "FAILED"
    assert outbox.status not in {"PENDING", "PROCESSING"}


@pytest.mark.asyncio
async def test_reclaimed_terminal_action_normalizes_processing_outbox_without_execution():
    action = _approved_action()
    action.status = "SUPERSEDED"
    outbox = SimpleNamespace(status="PROCESSING", processed_at=None, error_message=None)
    session = _session([action, outbox])

    result = await RecoveryActionControlPlane().dispatch_action(action.id, session)

    assert result.status == "SUPERSEDED"
    assert outbox.status == "SUPERSEDED"


@pytest.mark.asyncio
async def test_only_approved_actions_can_enter_execution():
    action = _approved_action()
    action.status = "PROPOSED"
    outbox = SimpleNamespace(status="PENDING", processed_at=None, error_message=None)
    session = _session([action, outbox])

    result = await RecoveryActionControlPlane().dispatch_action(action.id, session)

    assert result.status == "PROPOSED"
    assert action.status == "PROPOSED"
    assert outbox.status == "CANCELLED"


@pytest.mark.asyncio
async def test_currently_policy_permitted_approved_action_executes(monkeypatch):
    action = _approved_action()
    case, payment = _case_and_payment(action)
    outbox = SimpleNamespace(status="PENDING", attempt_count=1, max_attempts=3,
                             next_attempt_at=None, processed_at=None, error_message=None)
    session = _session([action, case, payment, None, _policy(case), 0, None, outbox, outbox])
    completed = ActionExecutionResult(action_id=action.id, action_type=RecoveryActionType.NOTIFY,
                                      status="COMPLETED", execution_reference="test-complete",
                                      executed_at=datetime.now(tz=timezone.utc))
    executor = SimpleNamespace(execute=AsyncMock(return_value=completed))
    monkeypatch.setattr("domain.recovery.control_plane.get_action_executor", lambda _: executor)

    result = await RecoveryActionControlPlane().dispatch_action(action.id, session, context=_context(case))

    assert result is completed
    assert action.status == "COMPLETED"
    assert outbox.status == "COMPLETED"
    executor.execute.assert_awaited_once()
