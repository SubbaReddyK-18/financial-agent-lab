"""Unit coverage for the webhook financial-authority boundary."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domain.shared.enums import PaymentStatus
from infrastructure.database.orm.payment import OrderORM, PaymentORM
from infrastructure.database.orm.webhook import RazorpayWebhookEventORM
from infrastructure.gateways.razorpay.parser import ParsedPaymentEntity
from infrastructure.workers.webhook_processor import (
    _find_authoritative_payment,
    _validate_authoritative_payment_match,
    process_single_webhook_event,
)
from tests.fixtures.razorpay_webhooks import build_razorpay_payment_payload


def _payment_and_order(*, amount_minor: int = 50_000) -> tuple[PaymentORM, OrderORM]:
    order = OrderORM(
        id=uuid.uuid4(),
        merchant_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        amount_minor=amount_minor,
        currency="INR",
        status="CREATED",
        razorpay_order_id="order_authoritative",
    )
    payment = PaymentORM(
        id=uuid.uuid4(),
        order_id=order.id,
        customer_id=order.customer_id,
        amount_minor=amount_minor,
        currency="INR",
        status="CREATED",
        razorpay_payment_id="pay_authoritative",
    )
    return payment, order


def _parsed_payment(*, amount_minor: int = 50_000, currency: str = "INR") -> ParsedPaymentEntity:
    return ParsedPaymentEntity(
        razorpay_payment_id="pay_authoritative",
        razorpay_order_id="order_authoritative",
        amount_minor=amount_minor,
        currency=currency,
        status=PaymentStatus.FAILED,
        payment_method=None,
    )


def test_matching_webhook_uses_existing_internal_amount_without_mutation():
    payment, order = _payment_and_order()

    match = _validate_authoritative_payment_match(payment, order, _parsed_payment())

    assert match.payment is payment
    assert match.order is order
    assert payment.amount_minor == 50_000
    assert order.amount_minor == 50_000


@pytest.mark.parametrize(
    ("webhook_amount", "currency", "expected_reason"),
    [
        (50_001, "INR", "webhook amount conflicts"),
        (50_000, "USD", "webhook currency conflicts"),
    ],
)
def test_conflicting_webhook_financial_facts_are_not_authoritative(
    webhook_amount: int, currency: str, expected_reason: str
):
    payment, order = _payment_and_order()

    match = _validate_authoritative_payment_match(
        payment, order, _parsed_payment(amount_minor=webhook_amount, currency=currency)
    )

    assert match.payment is None
    assert expected_reason in match.quarantine_reason
    assert payment.amount_minor == 50_000
    assert order.amount_minor == 50_000


@pytest.mark.asyncio
async def test_unmatched_webhook_is_quarantined_without_financial_side_effects():
    payload = build_razorpay_payment_payload(
        event_type="payment.failed",
        payment_id="pay_unmatched",
        order_id="order_unmatched",
        amount_minor=85_000,
    )
    event = RazorpayWebhookEventORM(
        id=uuid.uuid4(),
        razorpay_event_id="evt_unmatched",
        event_type="payment.failed",
        payload=payload,
        raw_payload="{}",
        signature="test-signature",
        processing_status="RECEIVED",
    )
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[None, None])
    session.flush = AsyncMock()
    session.add = AsyncMock()

    result = await process_single_webhook_event(event, session)

    assert result.success is True
    assert result.payment_id is None
    assert event.processing_status == "QUARANTINED"
    assert event.error_message.startswith("RECONCILIATION_REQUIRED:")
    session.add.assert_not_called()


@pytest.mark.asyncio
async def test_existing_payment_match_is_rejected_when_webhook_amount_conflicts():
    payment, order = _payment_and_order()
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[payment, order])

    match = await _find_authoritative_payment(
        session, _parsed_payment(amount_minor=51_000)
    )

    assert match.payment is None
    assert "webhook amount conflicts" in match.quarantine_reason
    assert payment.amount_minor == 50_000


@pytest.mark.asyncio
async def test_unique_internal_order_match_binds_only_external_identity():
    payment, order = _payment_and_order()
    payment.razorpay_payment_id = None
    session = AsyncMock()
    session.scalar = AsyncMock(side_effect=[None, order])
    result = SimpleNamespace(all=lambda: [payment])
    session.scalars = AsyncMock(return_value=result)

    match = await _find_authoritative_payment(session, _parsed_payment())

    assert match.payment is payment
    assert payment.razorpay_payment_id == "pay_authoritative"
    assert payment.amount_minor == order.amount_minor == 50_000
