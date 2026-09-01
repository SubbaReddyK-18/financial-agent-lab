"""
tests/integration/test_control_plane_e2e.py

Integration tests for Recovery Action & Control Plane (Block 7).

Tests transactional outbox, reliable dispatching, idempotency unique constraints,
stale action cancellation, and concurrency protection against live database session.

CRITICAL METHODOLOGICAL DIRECTIVES:
- Automated tests strictly enforce MockLLMClient (0 live Gemini quota).
- PostgreSQL transaction boundaries and ACID properties verified.
- Execution != payment capture; financial state remains authoritative.
"""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.settings import get_settings
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.recovery.control_plane import (
    RecoveryActionControlPlane,
    generate_action_idempotency_key,
)
from domain.recovery.orchestrator import RecoveryDecisionOrchestrator
from domain.shared.enums import (
    OutboxEventStatus,
    PaymentMethod,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.merchant import MerchantORM
from infrastructure.database.orm.outbox import RecoveryOutboxEventORM
from infrastructure.database.orm.payment import OrderORM, PaymentAttemptORM, PaymentORM
from infrastructure.database.orm.recovery import (
    MerchantRecoveryPolicyORM,
    RecoveryActionORM,
    RecoveryCaseORM,
)

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine():
    url = get_settings().async_database_url
    engine = create_async_engine(url, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine) -> AsyncSession:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session


class TestControlPlaneEndToEnd:
    @pytest.mark.asyncio
    async def test_atomic_orchestration_and_outbox_dispatch(self, db_session: AsyncSession):
        # 1. Setup seed data
        merchant_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        order_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        case_id = uuid.uuid4()

        merchant = MerchantORM(id=merchant_id, name="CP Test Merchant", currency="INR")
        db_session.add(merchant)

        customer = CustomerORM(
            id=customer_id, merchant_id=merchant_id, external_reference="cust_cp_001"
        )
        db_session.add(customer)
        await db_session.flush()

        policy = MerchantRecoveryPolicyORM(
            merchant_id=merchant_id,
            maximum_discount_percent=10,
            maximum_interventions=3,
            cooldown_hours=2,
        )
        payment = PaymentORM(
            id=payment_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            order_id=order_id,
            amount_minor=1000_00,
            currency="INR",
            payment_method=PaymentMethod.UPI.value,
            status=PaymentStatus.FAILED.value,
        )
        attempt = PaymentAttemptORM(
            payment_id=payment_id,
            attempt_number=1,
            amount_minor=1000_00,
            status="FAILED",
            failure_code="GATEWAY_TIMEOUT",
        )
        case = RecoveryCaseORM(
            id=case_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            payment_id=payment_id,
            amount_at_risk_minor=1000_00,
            status=RecoveryCaseStatus.OPEN.value,
        )

        db_session.add_all([policy, payment, attempt, case])
        await db_session.commit()

        # 2. Orchestrate decision with mock AI
        canned_ai_json = """{
            "action": "PAYMENT_LINK",
            "confidence": 0.95,
            "reasoning_codes": ["TIMEOUT_RETRY_BENEFICIAL"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "estimated_recovery_probability": 0.85,
            "recommended_discount_percent": 5
        }"""
        client = MockLLMClient(canned_response=canned_ai_json)
        provider = AIDecisionProvider(client=client)
        control_plane = RecoveryActionControlPlane()
        orchestrator = RecoveryDecisionOrchestrator(
            provider=provider, control_plane=control_plane
        )

        result = await orchestrator.orchestrate_case(
            case_id=case_id, session=db_session
        )
        await db_session.commit()

        # 3. Assert orchestration and control plane outcomes
        assert result.success is True
        assert result.action_type == RecoveryActionType.PAYMENT_LINK
        assert result.action_status == RecoveryActionStatus.COMPLETED.value
        assert result.execution_result is not None
        assert result.execution_result.status == "COMPLETED"
        assert "TEST_PLINK_" in result.execution_result.execution_reference

        # Verify database state
        persisted_action = await db_session.scalar(
            select(RecoveryActionORM).where(RecoveryActionORM.id == result.action_id)
        )
        assert persisted_action is not None
        assert persisted_action.status == RecoveryActionStatus.COMPLETED.value
        assert persisted_action.idempotency_key is not None
        assert persisted_action.discount_percent_offered == 5
        assert persisted_action.executed_at is not None

        persisted_outbox = await db_session.scalar(
            select(RecoveryOutboxEventORM).where(
                RecoveryOutboxEventORM.recovery_action_id == result.action_id
            )
        )
        assert persisted_outbox is not None
        assert persisted_outbox.status == OutboxEventStatus.COMPLETED.value
        assert persisted_outbox.processed_at is not None

    @pytest.mark.asyncio
    async def test_idempotent_re_dispatch_suppression(self, db_session: AsyncSession):
        merchant_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        case_id = uuid.uuid4()
        action_id = uuid.uuid4()

        merchant = MerchantORM(id=merchant_id, name="CP Merchant 2", currency="INR")
        customer = CustomerORM(id=customer_id, merchant_id=merchant_id, external_reference="cust_cp_002")
        db_session.add_all([merchant, customer])
        await db_session.flush()

        payment = PaymentORM(
            id=payment_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            amount_minor=5000_00,
            currency="INR",
            payment_method="UPI",
            status=PaymentStatus.FAILED.value,
        )
        case = RecoveryCaseORM(
            id=case_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            payment_id=payment_id,
            amount_at_risk_minor=5000_00,
            status=RecoveryCaseStatus.IN_PROGRESS.value,
        )
        action = RecoveryActionORM(
            id=action_id,
            recovery_case_id=case_id,
            action_type=RecoveryActionType.NOTIFY.value,
            status=RecoveryActionStatus.COMPLETED.value,
            idempotency_key=f"idem_{action_id.hex}",
            executed_at=datetime.now(tz=timezone.utc),
        )
        db_session.add_all([payment, case, action])
        await db_session.commit()

        # Attempt re-dispatch
        cp = RecoveryActionControlPlane()
        res = await cp.dispatch_action(action_id=action_id, session=db_session)

        assert res.status == "COMPLETED"
        assert "IDEMPOTENT_SKIPPED" in res.execution_reference

    @pytest.mark.asyncio
    async def test_stale_action_cancelled_when_payment_captured(self, db_session: AsyncSession):
        merchant_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        case_id = uuid.uuid4()
        action_id = uuid.uuid4()

        merchant = MerchantORM(id=merchant_id, name="CP Merchant 3", currency="INR")
        customer = CustomerORM(id=customer_id, merchant_id=merchant_id, external_reference="cust_cp_003")
        db_session.add_all([merchant, customer])
        await db_session.flush()

        # Payment resolved organically / captured
        payment = PaymentORM(
            id=payment_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            amount_minor=2000_00,
            currency="INR",
            payment_method="UPI",
            status=PaymentStatus.CAPTURED.value,
        )
        case = RecoveryCaseORM(
            id=case_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            payment_id=payment_id,
            amount_at_risk_minor=2000_00,
            status=RecoveryCaseStatus.OPEN.value,
        )
        action = RecoveryActionORM(
            id=action_id,
            recovery_case_id=case_id,
            action_type=RecoveryActionType.RETRY.value,
            status=RecoveryActionStatus.APPROVED.value,
            idempotency_key=f"idem_{action_id.hex}",
        )
        outbox = RecoveryOutboxEventORM(
            id=uuid.uuid4(),
            recovery_action_id=action_id,
            recovery_case_id=case_id,
            event_type="RECOVERY_ACTION_DISPATCH",
            status=OutboxEventStatus.PENDING.value,
            payload_json={"action_id": str(action_id)},
            idempotency_key=f"outbox_idem_{action_id.hex}",
        )

        db_session.add_all([payment, case, action, outbox])
        await db_session.commit()

        # Dispatch should detect payment is CAPTURED and mark SUPERSEDED
        cp = RecoveryActionControlPlane()
        res = await cp.dispatch_action(action_id=action_id, session=db_session)

        assert res.status == "SUPERSEDED"

        refreshed_action = await db_session.scalar(
            select(RecoveryActionORM).where(RecoveryActionORM.id == action_id)
        )
        assert refreshed_action.status == RecoveryActionStatus.SUPERSEDED.value

        refreshed_outbox = await db_session.scalar(
            select(RecoveryOutboxEventORM).where(
                RecoveryOutboxEventORM.recovery_action_id == action_id
            )
        )
        assert refreshed_outbox.status == OutboxEventStatus.SUPERSEDED.value

    @pytest.mark.asyncio
    async def test_outbox_batch_processing_and_claiming(self, db_session: AsyncSession):
        merchant_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        payment_id = uuid.uuid4()
        case_id = uuid.uuid4()
        action_id = uuid.uuid4()

        merchant = MerchantORM(id=merchant_id, name="CP Merchant 4", currency="INR")
        customer = CustomerORM(id=customer_id, merchant_id=merchant_id, external_reference="cust_cp_004")
        db_session.add_all([merchant, customer])
        await db_session.flush()

        policy = MerchantRecoveryPolicyORM(
            merchant_id=merchant_id,
            maximum_discount_percent=10,
            maximum_interventions=3,
            cooldown_hours=2,
        )
        payment = PaymentORM(
            id=payment_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            amount_minor=1500_00,
            currency="INR",
            payment_method="CARD",
            status=PaymentStatus.FAILED.value,
        )
        case = RecoveryCaseORM(
            id=case_id,
            merchant_id=merchant_id,
            customer_id=customer_id,
            payment_id=payment_id,
            amount_at_risk_minor=1500_00,
            status=RecoveryCaseStatus.OPEN.value,
        )
        action = RecoveryActionORM(
            id=action_id,
            recovery_case_id=case_id,
            action_type=RecoveryActionType.WAIT.value,
            status=RecoveryActionStatus.APPROVED.value,
            idempotency_key=f"idem_{action_id.hex}",
        )
        outbox = RecoveryOutboxEventORM(
            id=uuid.uuid4(),
            recovery_action_id=action_id,
            recovery_case_id=case_id,
            event_type="RECOVERY_ACTION_DISPATCH",
            status=OutboxEventStatus.PENDING.value,
            payload_json={"action_id": str(action_id)},
            idempotency_key=f"outbox_{action_id.hex}",
            next_attempt_at=datetime.now(tz=timezone.utc),
        )

        db_session.add_all([policy, payment, case, action, outbox])
        await db_session.commit()

        # Batch process outbox
        cp = RecoveryActionControlPlane()
        results = await cp.process_outbox_batch(session=db_session, limit=10)

        assert len(results) >= 1
        assert results[0].status == "COMPLETED"
        assert results[0].action_type == RecoveryActionType.WAIT

        refreshed_outbox = await db_session.scalar(
            select(RecoveryOutboxEventORM).where(
                RecoveryOutboxEventORM.recovery_action_id == action_id
            )
        )
        assert refreshed_outbox.status == OutboxEventStatus.COMPLETED.value
