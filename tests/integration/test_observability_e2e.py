"""
tests/integration/test_observability_e2e.py

Integration tests verifying the Observability and Evaluation API endpoints
against live PostgreSQL database records.

Flow tested:
payment.failed webhook
  → Webhook processor opens recovery case
  → RecoveryDecisionOrchestrator orchestrates decision and execution
  → Observability API queries reconstruct complete decision trace from PostgreSQL
  → Summary metrics and simulation evaluation endpoints verified.
"""

import hashlib
import hmac
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
from infrastructure.ai.client import MockLLMClient
from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.merchant import MerchantORM
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


class TestObservabilityAPIIntegration:
    async def test_end_to_end_orchestration_and_observability_queries(
        self, client: AsyncClient, db: AsyncSession
    ):
        settings = get_settings()
        secret = settings.razorpay_webhook_secret

        # 1. Seed Merchant, Customer, Policy
        merchant_id = uuid.uuid4()
        merchant = MerchantORM(id=merchant_id, name="Obs Merchant", currency="INR")
        db.add(merchant)

        customer = CustomerORM(id=uuid.uuid4(), merchant_id=merchant_id, external_reference="cust_obs_001")
        db.add(customer)
        await db.flush()

        policy = MerchantRecoveryPolicyORM(
            id=uuid.uuid4(),
            merchant_id=merchant_id,
            maximum_discount_percent=10,
            maximum_interventions=3,
            cooldown_hours=2,
        )
        db.add(policy)
        await db.commit()

        # 2. Ingest payment.failed Webhook
        razorpay_event_id = f"event_obs_{uuid.uuid4().hex[:12]}"
        razorpay_pay_id = f"pay_obs_{uuid.uuid4().hex[:12]}"
        razorpay_order_id = f"order_obs_{uuid.uuid4().hex[:12]}"

        payload_dict = {
            "entity": "event",
            "account_id": "acc_obs_test",
            "event": "payment.failed",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": razorpay_pay_id,
                        "entity": "payment",
                        "amount": 180000,  # ₹1,800.00
                        "currency": "INR",
                        "status": "failed",
                        "order_id": razorpay_order_id,
                        "method": "card",
                        "error_code": "INSUFFICIENT_FUNDS",
                        "error_description": "Card balance inadequate",
                        "created_at": 1700000000,
                    }
                }
            },
            "created_at": 1700000000,
        }
        body_bytes = json.dumps(payload_dict).encode("utf-8")
        signature = hmac.new(secret.encode("utf-8"), body_bytes, hashlib.sha256).hexdigest()

        resp = await client.post(
            "/webhooks/razorpay",
            content=body_bytes,
            headers={
                "X-Razorpay-Signature": signature,
                "X-Razorpay-Event-Id": razorpay_event_id,
                "Content-Type": "application/json",
            },
        )
        assert resp.status_code == 200

        # 3. Process Webhook Event to Open RecoveryCase
        inbox_record = await db.scalar(
            select(RazorpayWebhookEventORM).where(
                RazorpayWebhookEventORM.razorpay_event_id == razorpay_event_id
            )
        )
        proc_result = await process_single_webhook_event(inbox_record, db)
        assert proc_result.success is True
        await db.commit()

        recovery_case = await db.scalar(
            select(RecoveryCaseORM).where(RecoveryCaseORM.payment_id == proc_result.payment_id)
        )
        assert recovery_case is not None

        # 4. Orchestrate with Mock LLM
        canned_proposal = """{
            "recommended_action": "PAYMENT_LINK",
            "confidence": 0.90,
            "estimated_action_success_probability": 0.75,
            "estimated_natural_recovery_probability": 0.15,
            "reasoning_codes": ["INSUFFICIENT_FUNDS_ALTERNATIVE_RAIL"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "concise_rationale": "Offer payment link for alternative rail.",
            "recommended_discount_percent": 5
        }"""
        mock_client = MockLLMClient(canned_response=canned_proposal)
        ai_provider = AIDecisionProvider(client=mock_client)
        orchestrator = RecoveryDecisionOrchestrator(provider=ai_provider)

        orch_res = await orchestrator.orchestrate_case(
            case_id=recovery_case.id,
            session=db,
            correlation_id="obs_corr_123",
        )
        await db.commit()
        assert orch_res.success is True

        # 5. Query GET /observability/summary
        summary_resp = await client.get("/observability/summary")
        assert summary_resp.status_code == 200
        summary_data = summary_resp.json()
        assert summary_data["source_type"] == "LIVE_PRODUCTION"
        assert summary_data["decision_metrics"]["total_decisions"] >= 1
        assert "PAYMENT_LINK" in summary_data["decision_metrics"]["final_action_distribution"]
        assert "realized_captured_revenue_minor" in summary_data["economic_metrics"]
        assert "realized_net_incremental_revenue_minor" not in summary_data["economic_metrics"]

        # 6. Query GET /observability/recovery/{recovery_case_id}
        case_resp = await client.get(f"/observability/recovery/{recovery_case.id}")
        assert case_resp.status_code == 200
        case_data = case_resp.json()
        assert case_data["recovery_case_id"] == str(recovery_case.id)
        assert case_data["proposed_action"] == "PAYMENT_LINK"
        assert case_data["final_action"] == "PAYMENT_LINK"
        assert case_data["execution_status"] == "COMPLETED"
        assert "TEST_PLINK_" in case_data["execution_reference"]

        # 7. Query GET /observability/decisions/{decision_id}
        decision_id = case_data["decision_id"]
        dec_resp = await client.get(f"/observability/decisions/{decision_id}")
        assert dec_resp.status_code == 200
        dec_data = dec_resp.json()
        assert dec_data["decision_id"] == decision_id
        assert dec_data["confidence"] == 0.90
        assert dec_data["reasoning_codes"] == ["INSUFFICIENT_FUNDS_ALTERNATIVE_RAIL"]

        # 8. Query POST /observability/simulation/evaluate
        sim_resp = await client.post(
            "/observability/simulation/evaluate",
            json={"scenario_count": 5, "seed": 42},
        )
        assert sim_resp.status_code == 200
        sim_data = sim_resp.json()
        assert sim_data["source_type"] == "SYNTHETIC_SIMULATION"
        assert sim_data["scenario_count"] == 5
        assert "regret" in sim_data
        assert "calibration" in sim_data

        # 9. Query GET /observability/simulation/{run_id}
        run_id = sim_data["run_id"]
        run_resp = await client.get(f"/observability/simulation/{run_id}")
        assert run_resp.status_code == 200
        run_data = run_resp.json()
        assert run_data["run_id"] == run_id
