"""
tests/integration/test_recovery_orchestration_e2e.py

End-to-end integration test against live PostgreSQL.

Flow tested:
payment.failed webhook
  → Durable inbox ingestion
  → Webhook worker reconciliation & recovery case creation
  → RecoveryDecisionOrchestrator execution
  → AI/Deterministic baseline decisioning
  → Merchant policy gate validation
  → Deterministic economic valuation in paise
  → Test-mode action execution (COMPLETED)
  → FinancialEvent and AIDecisionRecord audit persistence.
"""

import hmac
import hashlib
import json
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.main import app
from apps.api.settings import get_settings
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.recovery.orchestrator import RecoveryDecisionOrchestrator
from domain.shared.enums import RecoveryActionType
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.merchant import MerchantORM
from infrastructure.database.orm.payment import OrderORM, PaymentORM
from infrastructure.database.orm.recovery import (
    MerchantRecoveryPolicyORM,
    RecoveryActionORM,
    RecoveryCaseORM,
)
from infrastructure.database.orm.webhook import RazorpayWebhookEventORM
from infrastructure.workers.webhook_processor import process_single_webhook_event

pytestmark = pytest.mark.integration


@pytest.fixture
async def engine():
    url = get_settings().async_database_url
    engine = create_async_engine(url, echo=False, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db(engine) -> AsyncSession:
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestRecoveryOrchestrationE2E:
    async def test_end_to_end_failed_webhook_to_orchestrated_action(
        self, client: AsyncClient, db: AsyncSession
    ):
        settings = get_settings()
        secret = settings.razorpay_webhook_secret

        # 1. Setup Merchant, Customer, Policy, Order, and Payment in PostgreSQL
        merchant_id = uuid.uuid4()
        merchant = MerchantORM(
            id=merchant_id,
            name="Test E2E Merchant",
            currency="INR",
        )
        db.add(merchant)

        customer_id = uuid.uuid4()
        customer = CustomerORM(
            id=customer_id,
            merchant_id=merchant_id,
            external_reference="cust_e2e_001",
        )
        db.add(customer)
        await db.flush()

        razorpay_event_id = f"event_e2e_{uuid.uuid4().hex[:12]}"
        razorpay_pay_id = f"pay_e2e_{uuid.uuid4().hex[:12]}"
        razorpay_order_id = f"order_e2e_{uuid.uuid4().hex[:12]}"

        order = OrderORM(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            customer_id=customer_id,
            amount_minor=250000,
            currency="INR",
            status="CREATED",
            razorpay_order_id=razorpay_order_id,
        )
        db.add(order)
        await db.flush()

        payment = PaymentORM(
            id=uuid.uuid4(),
            order_id=order.id,
            customer_id=customer_id,
            amount_minor=250000,
            currency="INR",
            status="CREATED",
            razorpay_payment_id=razorpay_pay_id,
        )
        db.add(payment)

        policy = MerchantRecoveryPolicyORM(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            maximum_discount_percent=10,
            maximum_interventions=3,
            cooldown_hours=2,
            high_value_threshold_minor=10000_00,
        )
        db.add(policy)
        await db.commit()

        # 2. Ingest payment.failed Webhook
        payload_dict = {
            "entity": "event",
            "account_id": "acc_test_e2e_123",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": razorpay_pay_id,
                        "entity": "payment",
                        "amount": 250000,  # ₹2,500.00
                        "currency": "INR",
                        "status": "failed",
                        "order_id": razorpay_order_id,
                        "method": "card",
                        "error_code": "GATEWAY_TIMEOUT",
                        "error_description": "Issuer switch response timed out",
                        "created_at": 1700000000,
                    }
                }
            },
            "created_at": 1700000000,
        }
        body_bytes = json.dumps(payload_dict).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

        response = await client.post(
            "/webhooks/razorpay",
            content=body_bytes,
            headers={
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": razorpay_event_id,
                "Content-Type": "application/json",
            },
        )
        assert response.status_code == 200

        # 3. Process Webhook Inbox Event via Webhook Worker
        inbox_record = await db.scalar(
            select(RazorpayWebhookEventORM).where(
                RazorpayWebhookEventORM.razorpay_event_id == razorpay_event_id
            )
        )
        assert inbox_record is not None

        proc_result = await process_single_webhook_event(inbox_record, db)
        assert proc_result.success is True
        await db.commit()

        # 4. Verify Recovery Case Opened
        recovery_case = await db.scalar(
            select(RecoveryCaseORM).where(RecoveryCaseORM.payment_id == proc_result.payment_id)
        )
        assert recovery_case is not None
        assert recovery_case.status == "OPEN"
        assert recovery_case.amount_at_risk_minor == 250000

        # 5. Run RecoveryDecisionOrchestrator with Mock LLM
        canned_ai_proposal = """{
            "recommended_action": "RETRY",
            "confidence": 0.88,
            "estimated_action_success_probability": 0.70,
            "estimated_natural_recovery_probability": 0.20,
            "reasoning_codes": ["TRANSIENT_TECHNICAL_FAILURE", "FIRST_ATTEMPT"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "concise_rationale": "Clear technical network timeout on first attempt.",
            "recommended_discount_percent": 0
        }"""
        mock_client = MockLLMClient(canned_response=canned_ai_proposal)
        ai_provider = AIDecisionProvider(client=mock_client)
        orchestrator = RecoveryDecisionOrchestrator(provider=ai_provider)

        orch_res = await orchestrator.orchestrate_case(
            case_id=recovery_case.id,
            session=db,
            correlation_id="e2e_test_correlation_123",
        )
        await db.commit()

        assert orch_res.success is True
        assert orch_res.action_type == RecoveryActionType.RETRY
        assert orch_res.action_status == "APPROVED"

        # Dispatch via ControlPlane (simulating outbox worker execution)
        from domain.recovery.control_plane import RecoveryActionControlPlane
        cp = RecoveryActionControlPlane()
        exec_res = await cp.dispatch_action(action_id=orch_res.action_id, session=db)
        await db.commit()

        assert exec_res is not None
        assert exec_res.status == "COMPLETED"
        assert orch_res.fallback_used is False
        assert "TEST_RETRY_" in exec_res.execution_reference

        # 7. Verify Database Records
        # A. Recovery Action Record
        action_in_db = await db.scalar(
            select(RecoveryActionORM).where(RecoveryActionORM.id == orch_res.action_id)
        )
        assert action_in_db is not None
        assert action_in_db.status == "COMPLETED"
        assert action_in_db.action_type == "RETRY"
        assert action_in_db.executed_at is not None

        # B. Recovery Case Status Transitioned to IN_PROGRESS
        case_in_db = await db.scalar(
            select(RecoveryCaseORM).where(RecoveryCaseORM.id == recovery_case.id)
        )
        assert case_in_db.status == "IN_PROGRESS"

        # C. Append-only Financial Event Recorded
        fin_event = await db.scalar(
            select(FinancialEventORM).where(
                FinancialEventORM.aggregate_id == str(orch_res.action_id)
            )
        )
        assert fin_event is not None
        assert fin_event.event_type == "RECOVERY_ACTION_APPROVED"
        assert fin_event.correlation_id == "e2e_test_correlation_123"

        # D. AI Decision Audit Record Persisted
        ai_audit = await db.scalar(
            select(AIDecisionRecordORM).where(
                AIDecisionRecordORM.scenario_id == str(recovery_case.id)
            )
        )
        assert ai_audit is not None
        assert ai_audit.recommended_action == "RETRY"
        assert ai_audit.confidence == 0.88
        assert ai_audit.fallback_used is False

    async def test_repeated_orchestration_on_closed_case_is_strictly_idempotent(
        self, db: AsyncSession
    ):
        merchant_id = uuid.uuid4()
        merchant = MerchantORM(id=merchant_id, name="Idem Merchant", currency="INR")
        db.add(merchant)

        customer = CustomerORM(id=uuid.uuid4(), merchant_id=merchant_id, external_reference="cust_idem")
        db.add(customer)
        await db.flush()

        order = OrderORM(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            customer_id=customer.id,
            amount_minor=5000_00,
            currency="INR",
            status="FAILED",
        )
        db.add(order)
        await db.flush()

        payment_id = uuid.uuid4()
        payment = PaymentORM(
            id=payment_id,
            order_id=order.id,
            customer_id=customer.id,
            amount_minor=5000_00,
            currency="INR",
            status="FAILED",
        )
        db.add(payment)
        await db.flush()

        case_id = uuid.uuid4()
        case = RecoveryCaseORM(
            id=case_id,
            merchant_id=merchant_id,
            customer_id=customer.id,
            payment_id=payment_id,
            amount_at_risk_minor=5000_00,
            status="CLOSED",
        )
        db.add(case)
        await db.commit()

        orchestrator = RecoveryDecisionOrchestrator()
        result = await orchestrator.orchestrate_case(case_id=case_id, session=db)
        await db.commit()

        assert result.success is True
        assert result.is_idempotent is True
        assert result.action_id is None

        # Verify zero recovery actions were created
        actions = (
            await db.scalars(
                select(RecoveryActionORM).where(RecoveryActionORM.recovery_case_id == case_id)
            )
        ).all()
        assert len(actions) == 0
