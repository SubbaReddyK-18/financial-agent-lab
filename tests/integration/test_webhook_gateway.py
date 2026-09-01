"""
tests/integration/test_webhook_gateway.py

Comprehensive integration tests for Razorpay Test Mode webhook ingestion,
signature verification, deduplication, worker processing, payment reconciliation,
and recovery case lifecycle.

Requires live PostgreSQL.
"""

import json
import uuid
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from apps.api.main import app
from apps.api.settings import get_settings
from domain.shared.enums import PaymentStatus, RecoveryCaseStatus
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.payment import PaymentORM
from infrastructure.database.orm.recovery import RecoveryCaseORM
from infrastructure.database.orm.webhook import RazorpayWebhookEventORM
from infrastructure.workers.runner import process_pending_webhooks
from tests.fixtures.razorpay_webhooks import (
    build_razorpay_payment_payload,
    build_signed_webhook_request,
    sign_payload,
)

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
        await session.rollback()


@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestWebhookEndpointIngestion:
    async def test_valid_webhook_ingestion_persists_inbox(
        self, client: AsyncClient, db: AsyncSession
    ):
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        raw_body, headers = build_signed_webhook_request(
            event_type="payment.captured",
            event_id=event_id,
            payment_id=f"pay_{uuid.uuid4().hex[:12]}",
            amount_minor=150000,
        )

        response = await client.post(
            "/webhooks/razorpay",
            content=raw_body,
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"
        assert data["event_id"] == event_id

        # Verify record in database
        event_record = await db.scalar(
            select(RazorpayWebhookEventORM).where(
                RazorpayWebhookEventORM.razorpay_event_id == event_id
            )
        )
        assert event_record is not None
        assert event_record.event_type == "payment.captured"
        assert event_record.processing_status == "RECEIVED"

    async def test_missing_headers_rejected(self, client: AsyncClient):
        response = await client.post(
            "/webhooks/razorpay",
            content=b'{"event": "payment.captured"}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400
        assert "Missing required headers" in response.json()["detail"]

    async def test_invalid_signature_rejected_with_401(self, client: AsyncClient):
        event_id = f"evt_{uuid.uuid4().hex[:16]}"
        raw_body, headers = build_signed_webhook_request(
            event_type="payment.captured",
            event_id=event_id,
        )
        headers["X-Razorpay-Signature"] = "invalid_bogus_hmac_signature_000000000000"

        response = await client.post(
            "/webhooks/razorpay",
            content=raw_body,
            headers=headers,
        )
        assert response.status_code == 401
        assert "Invalid webhook signature" in response.json()["detail"]

    async def test_malformed_json_body_rejected(self, client: AsyncClient):
        secret = get_settings().razorpay_webhook_secret
        raw_body = b"{malformed_json_payload"
        sig = sign_payload(raw_body, secret)
        headers = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": "evt_malformed_001",
        }

        response = await client.post(
            "/webhooks/razorpay",
            content=raw_body,
            headers=headers,
        )
        assert response.status_code == 400

    async def test_duplicate_event_id_deduplicated_safely(
        self, client: AsyncClient, db: AsyncSession
    ):
        event_id = f"evt_dup_{uuid.uuid4().hex[:12]}"
        raw_body, headers = build_signed_webhook_request(
            event_type="payment.captured",
            event_id=event_id,
        )

        # First delivery -> accepted
        r1 = await client.post("/webhooks/razorpay", content=raw_body, headers=headers)
        assert r1.status_code == 200
        assert r1.json()["status"] == "accepted"

        # Second delivery with same X-Razorpay-Event-Id -> duplicate_ignored
        r2 = await client.post("/webhooks/razorpay", content=raw_body, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "duplicate_ignored"


class TestWorkerProcessingAndReconciliation:
    async def test_failed_event_opens_recovery_case(
        self, client: AsyncClient, db: AsyncSession
    ):
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        event_id = f"evt_{uuid.uuid4().hex[:12]}"

        raw_body, headers = build_signed_webhook_request(
            event_type="payment.failed",
            event_id=event_id,
            payment_id=payment_id,
            amount_minor=500000,
            error_code="INSUFFICIENT_FUNDS",
            error_description="Card declined due to low funds.",
        )
        await client.post("/webhooks/razorpay", content=raw_body, headers=headers)

        # Run worker to process inbox
        results = await process_pending_webhooks(db, limit=10)
        await db.commit()

        assert any(r.event_id == event_id and r.success for r in results)

        # Verify Payment state = FAILED
        payment = await db.scalar(
            select(PaymentORM).where(PaymentORM.razorpay_payment_id == payment_id)
        )
        assert payment is not None
        assert payment.status == PaymentStatus.FAILED.value

        # Verify RecoveryCase is OPEN
        case = await db.scalar(
            select(RecoveryCaseORM).where(RecoveryCaseORM.payment_id == payment.id)
        )
        assert case is not None
        assert case.status == RecoveryCaseStatus.OPEN.value
        assert case.amount_at_risk_minor == 500000

        # Verify FinancialEvent was logged
        events = (
            await db.scalars(
                select(FinancialEventORM).where(
                    FinancialEventORM.aggregate_id == str(payment.id)
                )
            )
        ).all()
        assert len(events) >= 1
        assert any(e.event_type == "PAYMENT_FAILED" for e in events)

    async def test_razorpay_failed_then_captured_resolves_recovery_case(
        self, client: AsyncClient, db: AsyncSession
    ):
        """
        The crucial Razorpay reconciliation flow:
        1. payment.failed arrives -> status FAILED, RecoveryCase OPEN
        2. later payment.captured arrives (UPI retry / late bank capture) -> status CAPTURED, RecoveryCase RECOVERED
        """
        payment_id = f"pay_reconcile_{uuid.uuid4().hex[:12]}"
        event_failed_id = f"evt_fail_{uuid.uuid4().hex[:12]}"
        event_cap_id = f"evt_cap_{uuid.uuid4().hex[:12]}"

        # Step 1: Failed event
        raw_failed, headers_failed = build_signed_webhook_request(
            event_type="payment.failed",
            event_id=event_failed_id,
            payment_id=payment_id,
            amount_minor=300000,
        )
        await client.post("/webhooks/razorpay", content=raw_failed, headers=headers_failed)
        await process_pending_webhooks(db, limit=10)
        await db.commit()

        # Step 2: Captured event arrives later
        raw_cap, headers_cap = build_signed_webhook_request(
            event_type="payment.captured",
            event_id=event_cap_id,
            payment_id=payment_id,
            amount_minor=300000,
        )
        await client.post("/webhooks/razorpay", content=raw_cap, headers=headers_cap)
        await process_pending_webhooks(db, limit=10)
        await db.commit()

        # Verify Payment state updated to CAPTURED
        payment = await db.scalar(
            select(PaymentORM).where(PaymentORM.razorpay_payment_id == payment_id)
        )
        assert payment is not None
        assert payment.status == PaymentStatus.CAPTURED.value

        # Verify RecoveryCase transitioned to RECOVERED and closed
        case = await db.scalar(
            select(RecoveryCaseORM).where(RecoveryCaseORM.payment_id == payment.id)
        )
        assert case is not None
        assert case.status == RecoveryCaseStatus.RECOVERED.value
        assert case.closed_at is not None

    async def test_captured_followed_by_late_failed_cannot_downgrade(
        self, client: AsyncClient, db: AsyncSession
    ):
        """
        Safety invariant: Once CAPTURED, late payment.failed cannot downgrade status
        and cannot open a false recovery case.
        """
        payment_id = f"pay_nodowngrade_{uuid.uuid4().hex[:12]}"
        event_cap_id = f"evt_cap_{uuid.uuid4().hex[:12]}"
        event_late_fail_id = f"evt_latefail_{uuid.uuid4().hex[:12]}"

        # Step 1: Captured first
        raw_cap, headers_cap = build_signed_webhook_request(
            event_type="payment.captured",
            event_id=event_cap_id,
            payment_id=payment_id,
            amount_minor=200000,
        )
        await client.post("/webhooks/razorpay", content=raw_cap, headers=headers_cap)
        await process_pending_webhooks(db, limit=10)
        await db.commit()

        # Step 2: Late failed arrives out of order
        raw_fail, headers_fail = build_signed_webhook_request(
            event_type="payment.failed",
            event_id=event_late_fail_id,
            payment_id=payment_id,
            amount_minor=200000,
        )
        await client.post("/webhooks/razorpay", content=raw_fail, headers=headers_fail)
        await process_pending_webhooks(db, limit=10)
        await db.commit()

        # State must remain CAPTURED
        payment = await db.scalar(
            select(PaymentORM).where(PaymentORM.razorpay_payment_id == payment_id)
        )
        assert payment.status == PaymentStatus.CAPTURED.value

        # No recovery case should exist for captured payment
        cases = (
            await db.scalars(
                select(RecoveryCaseORM).where(RecoveryCaseORM.payment_id == payment.id)
            )
        ).all()
        assert len(cases) == 0

    async def test_captured_before_authorized_reconciliation(
        self, client: AsyncClient, db: AsyncSession
    ):
        """
        Out of order: payment.captured webhook processed before payment.authorized webhook.
        Final state must remain CAPTURED.
        """
        payment_id = f"pay_ooo_{uuid.uuid4().hex[:12]}"
        event_cap_id = f"evt_cap_ooo_{uuid.uuid4().hex[:12]}"
        event_auth_id = f"evt_auth_ooo_{uuid.uuid4().hex[:12]}"

        # Captured arrives first
        raw_cap, headers_cap = build_signed_webhook_request(
            event_type="payment.captured",
            event_id=event_cap_id,
            payment_id=payment_id,
            amount_minor=100000,
        )
        await client.post("/webhooks/razorpay", content=raw_cap, headers=headers_cap)
        await process_pending_webhooks(db, limit=10)
        await db.commit()

        # Delayed authorized arrives second
        raw_auth, headers_auth = build_signed_webhook_request(
            event_type="payment.authorized",
            event_id=event_auth_id,
            payment_id=payment_id,
            amount_minor=100000,
        )
        await client.post("/webhooks/razorpay", content=raw_auth, headers=headers_auth)
        await process_pending_webhooks(db, limit=10)
        await db.commit()

        payment = await db.scalar(
            select(PaymentORM).where(PaymentORM.razorpay_payment_id == payment_id)
        )
        assert payment.status == PaymentStatus.CAPTURED.value
