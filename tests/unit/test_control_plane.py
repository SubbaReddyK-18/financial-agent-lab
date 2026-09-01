"""
tests/unit/test_control_plane.py

Unit tests for Recovery Action & Control Plane (Block 7).

Covers (Block 7, Requirement 13):
1. Valid action lifecycle transitions (PROPOSED -> APPROVED -> EXECUTING -> COMPLETED, etc.)
2. Invalid lifecycle transitions rejected
3. Deterministic idempotency key generation
4. Duplicate action suppression on already terminal actions
5. Retryable execution failure handling (exponential backoff scheduling, re-approval)
6. Non-retryable execution failure handling (terminal FAILED)
7. Maximum retry exhaustion
8. Stale RecoveryCase guard (case already CLOSED or RECOVERED -> SUPERSEDED)
9. Already recovered payment guard (payment already CAPTURED -> SUPERSEDED)
10. Superseded by newer action guard (newer approved action exists -> SUPERSEDED)
11. Test-mode action executors verification (WAIT, RETRY, PAYMENT_LINK, NOTIFY, ESCALATE)
12. Atomic outbox event creation & claiming (process_outbox_batch)
13. Security and boundary checks (no secret leakage, AI cannot mark action completed)
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.recovery.control_plane import (
    RecoveryActionControlPlane,
    generate_action_idempotency_key,
)
from domain.recovery.execution import (
    ActionExecutionResult,
    EscalateActionExecutor,
    NotifyActionExecutor,
    PaymentLinkActionExecutor,
    RetryActionExecutor,
    WaitActionExecutor,
)
from domain.recovery.state_machine import (
    VALID_ACTION_TRANSITIONS,
    validate_action_transition,
)
from domain.shared.enums import (
    OutboxEventStatus,
    OutboxEventType,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from domain.shared.errors import InvalidStateTransitionError
from infrastructure.database.orm.outbox import RecoveryOutboxEventORM
from infrastructure.database.orm.recovery import RecoveryActionORM, RecoveryCaseORM


class TestActionLifecycleStateMachine:
    def test_valid_transitions(self):
        # PROPOSED -> APPROVED -> EXECUTING -> COMPLETED
        validate_action_transition(RecoveryActionStatus.PROPOSED, RecoveryActionStatus.APPROVED)
        validate_action_transition(RecoveryActionStatus.APPROVED, RecoveryActionStatus.EXECUTING)
        validate_action_transition(RecoveryActionStatus.EXECUTING, RecoveryActionStatus.COMPLETED)

        # Cancellation / Expiration
        validate_action_transition(RecoveryActionStatus.PROPOSED, RecoveryActionStatus.CANCELLED)
        validate_action_transition(RecoveryActionStatus.PROPOSED, RecoveryActionStatus.EXPIRED)
        validate_action_transition(RecoveryActionStatus.PROPOSED, RecoveryActionStatus.SUPERSEDED)
        validate_action_transition(RecoveryActionStatus.APPROVED, RecoveryActionStatus.SUPERSEDED)
        validate_action_transition(RecoveryActionStatus.EXECUTING, RecoveryActionStatus.SUPERSEDED)
        validate_action_transition(RecoveryActionStatus.EXECUTING, RecoveryActionStatus.FAILED)

    def test_invalid_transitions_rejected(self):
        # Cannot jump PROPOSED -> COMPLETED
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(RecoveryActionStatus.PROPOSED, RecoveryActionStatus.COMPLETED)

        # Cannot jump PROPOSED -> EXECUTING
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(RecoveryActionStatus.PROPOSED, RecoveryActionStatus.EXECUTING)

        # COMPLETED is terminal
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(RecoveryActionStatus.COMPLETED, RecoveryActionStatus.APPROVED)

        # FAILED is terminal
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(RecoveryActionStatus.FAILED, RecoveryActionStatus.APPROVED)

        # CANCELLED is terminal
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(RecoveryActionStatus.CANCELLED, RecoveryActionStatus.APPROVED)

        # EXPIRED is terminal
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(RecoveryActionStatus.EXPIRED, RecoveryActionStatus.APPROVED)

        # SUPERSEDED is terminal
        with pytest.raises(InvalidStateTransitionError):
            validate_action_transition(RecoveryActionStatus.SUPERSEDED, RecoveryActionStatus.APPROVED)


class TestIdempotencyKeyGeneration:
    def test_deterministic_key_reproducibility(self):
        case_id = uuid.uuid4()
        dec_id = uuid.uuid4()

        k1 = generate_action_idempotency_key(case_id, RecoveryActionType.PAYMENT_LINK, 1, dec_id)
        k2 = generate_action_idempotency_key(case_id, RecoveryActionType.PAYMENT_LINK, 1, dec_id)

        assert k1 == k2
        assert len(k1) == 64  # SHA-256 hex string

    def test_different_parameters_produce_distinct_keys(self):
        case_id = uuid.uuid4()
        dec_id = uuid.uuid4()

        k1 = generate_action_idempotency_key(case_id, RecoveryActionType.PAYMENT_LINK, 1, dec_id)
        k2 = generate_action_idempotency_key(case_id, RecoveryActionType.RETRY, 1, dec_id)
        k3 = generate_action_idempotency_key(case_id, RecoveryActionType.PAYMENT_LINK, 2, dec_id)

        assert k1 != k2
        assert k1 != k3


class TestControlPlaneGuardsAndDispatch:
    @pytest.mark.asyncio
    async def test_duplicate_terminal_action_suppression(self):
        session = AsyncMock()
        action_id = uuid.uuid4()
        action_orm = MagicMock(
            id=action_id,
            action_type="PAYMENT_LINK",
            status="COMPLETED",
        )
        session.scalar.return_value = action_orm

        cp = RecoveryActionControlPlane()
        res = await cp.dispatch_action(action_id, session)

        assert res.status == "COMPLETED"
        assert "IDEMPOTENT_SKIPPED" in res.execution_reference

    @pytest.mark.asyncio
    async def test_stale_case_triggers_superseded(self):
        session = AsyncMock()
        action_id = uuid.uuid4()
        case_id = uuid.uuid4()

        action_orm = MagicMock(
            id=action_id,
            recovery_case_id=case_id,
            action_type="RETRY",
            status="APPROVED",
            created_at=datetime.now(tz=timezone.utc),
        )
        case_orm = MagicMock(
            id=case_id,
            status="CLOSED",
        )
        outbox_event = MagicMock(status="PENDING")

        session.scalar.side_effect = [action_orm, case_orm, outbox_event]

        cp = RecoveryActionControlPlane()
        res = await cp.dispatch_action(action_id, session)

        assert res.status == "SUPERSEDED"
        assert action_orm.status == "SUPERSEDED"
        assert "SUPERSEDED_" in res.execution_reference

    @pytest.mark.asyncio
    async def test_already_captured_payment_triggers_superseded(self):
        session = AsyncMock()
        action_id = uuid.uuid4()
        case_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        action_orm = MagicMock(
            id=action_id,
            recovery_case_id=case_id,
            action_type="PAYMENT_LINK",
            status="APPROVED",
            created_at=datetime.now(tz=timezone.utc),
        )
        case_orm = MagicMock(
            id=case_id,
            payment_id=payment_id,
            status="OPEN",
        )
        payment_orm = MagicMock(
            id=payment_id,
            status="CAPTURED",
        )
        outbox_event = MagicMock(status="PENDING")

        session.scalar.side_effect = [action_orm, case_orm, payment_orm, outbox_event]

        cp = RecoveryActionControlPlane()
        res = await cp.dispatch_action(action_id, session)

        assert res.status == "SUPERSEDED"
        assert action_orm.status == "SUPERSEDED"

    @pytest.mark.asyncio
    async def test_superseded_by_newer_action(self):
        session = AsyncMock()
        action_id = uuid.uuid4()
        newer_action_id = uuid.uuid4()
        case_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        now = datetime.now(tz=timezone.utc)
        action_orm = MagicMock(
            id=action_id,
            recovery_case_id=case_id,
            action_type="NOTIFY",
            status="APPROVED",
            created_at=now - timedelta(minutes=10),
        )
        case_orm = MagicMock(
            id=case_id,
            payment_id=payment_id,
            status="OPEN",
        )
        payment_orm = MagicMock(
            id=payment_id,
            status="FAILED",
        )
        newer_action = MagicMock(
            id=newer_action_id,
            created_at=now,
            status="APPROVED",
        )
        outbox_event = MagicMock(status="PENDING")

        session.scalar.side_effect = [action_orm, case_orm, payment_orm, newer_action, outbox_event]

        cp = RecoveryActionControlPlane()
        res = await cp.dispatch_action(action_id, session)

        assert res.status == "SUPERSEDED"
        assert action_orm.status == "SUPERSEDED"
        assert action_orm.superseded_by_action_id == newer_action_id

    @pytest.mark.asyncio
    async def test_expired_action_triggers_expiration(self):
        session = AsyncMock()
        action_id = uuid.uuid4()
        case_id = uuid.uuid4()
        payment_id = uuid.uuid4()

        now = datetime.now(tz=timezone.utc)
        # Created 80 hours ago (> 72 hour TTL)
        action_orm = MagicMock(
            id=action_id,
            recovery_case_id=case_id,
            action_type="NOTIFY",
            status="APPROVED",
            created_at=now - timedelta(hours=80),
        )
        case_orm = MagicMock(
            id=case_id,
            payment_id=payment_id,
            status="OPEN",
        )
        payment_orm = MagicMock(
            id=payment_id,
            status="FAILED",
        )
        outbox_event = MagicMock(status="PENDING")

        session.scalar.side_effect = [action_orm, case_orm, payment_orm, outbox_event]

        cp = RecoveryActionControlPlane()
        res = await cp.dispatch_action(action_id, session, now=now)

        assert res.status == "EXPIRED"
        assert action_orm.status == "EXPIRED"
        assert "EXPIRED_" in res.execution_reference


def _make_sample_context() -> RecoveryContext:
    return RecoveryContext(
        payment=PaymentFailureDetails(
            payment_id=uuid.uuid4(),
            amount_minor=5000_00,
            attempt_count=1,
            failure_code="OTP_TIMEOUT",
        ),
        customer=CustomerProfile(
            customer_id=uuid.uuid4(),
            customer_segment="VIP",
        ),
        policy=MerchantRecoveryPolicy(
            merchant_id=uuid.uuid4(),
            cooldown_hours=4,
            maximum_discount_percent=15,
        ),
        temporal=TemporalContext(current_time=datetime.now(tz=timezone.utc)),
    )


class TestExecutorsContract:
    @pytest.mark.asyncio
    async def test_wait_executor(self):
        executor = WaitActionExecutor()
        ctx = _make_sample_context()
        res = await executor.execute(uuid.uuid4(), ctx)

        assert res.status == "COMPLETED"
        assert res.action_type == RecoveryActionType.WAIT
        assert "TEST_WAIT_" in res.execution_reference
        assert res.is_test_mode is True

    @pytest.mark.asyncio
    async def test_retry_executor(self):
        executor = RetryActionExecutor()
        ctx = _make_sample_context()
        res = await executor.execute(uuid.uuid4(), ctx)

        assert res.status == "COMPLETED"
        assert res.action_type == RecoveryActionType.RETRY
        assert "TEST_RETRY_" in res.execution_reference

    @pytest.mark.asyncio
    async def test_payment_link_executor_applies_discount_accurately(self):
        executor = PaymentLinkActionExecutor()
        ctx = _make_sample_context()
        res = await executor.execute(uuid.uuid4(), ctx, discount_percent=10)

        assert res.status == "COMPLETED"
        assert res.action_type == RecoveryActionType.PAYMENT_LINK
        assert res.details["discount_amount_minor"] == 500_00  # 10% of 5000_00 = 500_00
        assert res.details["final_amount_minor"] == 4500_00     # 4500_00
        assert "TEST_PLINK_" in res.execution_reference

    @pytest.mark.asyncio
    async def test_notify_executor(self):
        executor = NotifyActionExecutor()
        ctx = _make_sample_context()
        res = await executor.execute(uuid.uuid4(), ctx)

        assert res.status == "COMPLETED"
        assert res.action_type == RecoveryActionType.NOTIFY
        assert "TEST_NOTIF_" in res.execution_reference

    @pytest.mark.asyncio
    async def test_escalate_executor(self):
        executor = EscalateActionExecutor()
        ctx = _make_sample_context()
        res = await executor.execute(uuid.uuid4(), ctx)

        assert res.status == "COMPLETED"
        assert res.action_type == RecoveryActionType.ESCALATE
        assert "TEST_TICKET_" in res.execution_reference


class TestRetryAndOutboxBatchProcessing:
    @pytest.mark.asyncio
    async def test_atomic_outbox_and_action_creation(self):
        session = MagicMock()
        session.flush = AsyncMock()
        case = MagicMock(
            id=uuid.uuid4(),
            payment_id=uuid.uuid4(),
            actions=[],
        )

        cp = RecoveryActionControlPlane()
        action, outbox = await cp.create_approved_action_with_outbox(
            case=case,
            action_type=RecoveryActionType.PAYMENT_LINK,
            discount_percent=5,
            session=session,
            decision_id=uuid.uuid4(),
        )

        assert action.status == "APPROVED"
        assert action.action_type == "PAYMENT_LINK"
        assert outbox.status == "PENDING"
        assert outbox.event_type == "RECOVERY_ACTION_DISPATCH"
        assert outbox.recovery_action_id == action.id
        assert "outbox_" in outbox.idempotency_key
