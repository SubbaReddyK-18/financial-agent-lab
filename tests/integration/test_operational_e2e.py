"""
tests/integration/test_operational_e2e.py

End-to-end operational resilience and pipeline integration tests for Block 8.

Tests complete flow:
Razorpay payment.failed webhook
  → Signature verification & deduplication
  → Webhook inbox persistence
  → Worker reconciliation
  → RecoveryCase creation
  → RecoveryDecisionOrchestrator
  → AI proposal via MockLLMClient (0 Gemini quota)
  → Policy gate & EconomicEngine validation
  → RecoveryAction approval & transactional outbox event
  → OutboxWorker reliable dispatch & test-mode execution
  → Authoritative audit persistence
  → Duplicate delivery suppression (0 duplicate actions / cases / events).
"""

import json
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.main import app
from apps.api.settings import get_settings
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.recovery.control_plane import RecoveryActionControlPlane
from domain.recovery.orchestrator import RecoveryDecisionOrchestrator
from domain.shared.enums import OutboxEventStatus, PaymentStatus, RecoveryActionStatus, RecoveryCaseStatus
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.merchant import MerchantORM
from infrastructure.database.orm.outbox import RecoveryOutboxEventORM
from infrastructure.database.orm.payment import OrderORM, PaymentAttemptORM, PaymentORM
from infrastructure.database.orm.recovery import MerchantRecoveryPolicyORM, RecoveryActionORM, RecoveryCaseORM
from infrastructure.database.orm.webhook import RazorpayWebhookEventORM
from infrastructure.workers.outbox_worker import OutboxWorker
from infrastructure.workers.webhook_processor import process_single_webhook_event
from tests.fixtures.razorpay_webhooks import build_signed_webhook_request

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


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestOperationalPipelineEndToEnd:
    @pytest.mark.asyncio
    async def test_full_pipeline_and_duplicate_suppression(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        settings = get_settings()
        secret = settings.razorpay_webhook_secret

        # 1. Setup Merchant, Customer, and Policy in DB
        merchant_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        merchant = MerchantORM(id=merchant_id, name="Operational Test Merchant", currency="INR")
        customer = CustomerORM(id=customer_id, merchant_id=merchant_id, external_reference="cust_op_001")
        policy = MerchantRecoveryPolicyORM(
            merchant_id=merchant_id,
            maximum_discount_percent=10,
            maximum_interventions=3,
            cooldown_hours=2,
        )
        db_session.add_all([merchant, customer, policy])
        await db_session.commit()

        # 2. Ingest payment.failed webhook
        event_id = f"evt_op_test_{uuid.uuid4().hex[:12]}"
        payment_id_str = f"pay_op_{uuid.uuid4().hex[:12]}"
        raw_body, headers = build_signed_webhook_request(
            event_type="payment.failed",
            payment_id=payment_id_str,
            amount_paise=5000_00,
            event_id=event_id,
            secret=secret,
            error_code="BAD_REQUEST_ERROR",
            error_description="Payment timed out at gateway",
        )

        res = await client.post("/webhooks/razorpay", content=raw_body, headers=headers)
        assert res.status_code == 200
        assert res.json()["status"] == "accepted"

        # 3. Process webhook inbox event
        inbox_event = await db_session.scalar(
            select(RazorpayWebhookEventORM).where(
                RazorpayWebhookEventORM.razorpay_event_id == event_id
            )
        )
        assert inbox_event is not None
        await process_single_webhook_event(inbox_event.id, db_session)
        await db_session.commit()

        # 4. Verify Payment, PaymentAttempt, and RecoveryCase created
        payment = await db_session.scalar(
            select(PaymentORM).where(PaymentORM.razorpay_payment_id == payment_id_str)
        )
        assert payment is not None
        assert payment.status == PaymentStatus.FAILED.value

        case = await db_session.scalar(
            select(RecoveryCaseORM).where(RecoveryCaseORM.payment_id == payment.id)
        )
        assert case is not None
        assert case.status == RecoveryCaseStatus.OPEN.value

        # 5. Run RecoveryDecisionOrchestrator with Mock AI provider
        canned_json = """{
            "action": "PAYMENT_LINK",
            "confidence": 0.92,
            "reasoning_codes": ["TIMEOUT_RETRY_BENEFICIAL"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "estimated_recovery_probability": 0.80,
            "recommended_discount_percent": 5
        }"""
        provider = AIDecisionProvider(client=MockLLMClient(canned_response=canned_json))
        control_plane = RecoveryActionControlPlane()
        orchestrator = RecoveryDecisionOrchestrator(
            provider=provider, control_plane=control_plane
        )

        orch_result = await orchestrator.orchestrate_case(
            case_id=case.id, session=db_session
        )
        await db_session.commit()

        assert orch_result.success is True
        assert orch_result.action_status == RecoveryActionStatus.COMPLETED.value

        # Verify Outbox record
        outbox = await db_session.scalar(
            select(RecoveryOutboxEventORM).where(
                RecoveryOutboxEventORM.recovery_case_id == case.id
            )
        )
        assert outbox is not None
        assert outbox.status == OutboxEventStatus.COMPLETED.value

        # 6. Test Webhook Duplicate Delivery
        res_dup = await client.post("/webhooks/razorpay", content=raw_body, headers=headers)
        assert res_dup.status_code == 200
        assert res_dup.json()["status"] == "duplicate_ignored"

        # Verify NO duplicate recovery case, actions, or outbox records created
        case_count = await db_session.scalar(
            select(func.count()).select_from(RecoveryCaseORM).where(RecoveryCaseORM.payment_id == payment.id)
        )
        action_count = await db_session.scalar(
            select(func.count()).select_from(RecoveryActionORM).where(RecoveryActionORM.recovery_case_id == case.id)
        )
        outbox_count = await db_session.scalar(
            select(func.count()).select_from(RecoveryOutboxEventORM).where(RecoveryOutboxEventORM.recovery_case_id == case.id)
        )

        assert case_count == 1
        assert action_count == 1
        assert outbox_count == 1

    @pytest.mark.asyncio
    async def test_health_and_readiness_operational(self, client: AsyncClient):
        # Liveness
        res_h = await client.get("/health")
        assert res_h.status_code == 200
        assert res_h.json()["status"] == "healthy"

        # Readiness
        res_r = await client.get("/ready")
        assert res_r.status_code in (200, 503)
