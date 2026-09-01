"""
tests/unit/test_razorpay_parser.py

Unit tests for Razorpay webhook payload parser and adapter.
"""

import pytest

from domain.shared.enums import PaymentMethod, PaymentStatus
from infrastructure.gateways.razorpay.parser import (
    RazorpayPayloadError,
    parse_razorpay_webhook_payload,
)
from tests.fixtures.razorpay_webhooks import build_razorpay_payment_payload


class TestRazorpayParser:
    def test_parse_payment_captured(self):
        payload = build_razorpay_payment_payload(
            event_type="payment.captured",
            payment_id="pay_cap_001",
            order_id="order_cap_001",
            amount_minor=250000,
            currency="INR",
            method="card",
        )
        parsed = parse_razorpay_webhook_payload(payload, event_id_header="evt_001")

        assert parsed.event_id == "evt_001"
        assert parsed.event_type == "payment.captured"
        assert parsed.payment is not None
        assert parsed.payment.razorpay_payment_id == "pay_cap_001"
        assert parsed.payment.razorpay_order_id == "order_cap_001"
        assert parsed.payment.amount_minor == 250000
        assert parsed.payment.currency == "INR"
        assert parsed.payment.status == PaymentStatus.CAPTURED
        assert parsed.payment.payment_method == PaymentMethod.CARD

    def test_parse_payment_failed_with_errors(self):
        payload = build_razorpay_payment_payload(
            event_type="payment.failed",
            payment_id="pay_fail_002",
            error_code="INSUFFICIENT_FUNDS",
            error_description="Account has insufficient balance.",
            method="upi",
        )
        parsed = parse_razorpay_webhook_payload(payload, event_id_header="evt_002")

        assert parsed.payment is not None
        assert parsed.payment.status == PaymentStatus.FAILED
        assert parsed.payment.payment_method == PaymentMethod.UPI
        assert parsed.payment.error_code == "INSUFFICIENT_FUNDS"
        assert parsed.payment.error_description == "Account has insufficient balance."

    def test_parse_payment_authorized(self):
        payload = build_razorpay_payment_payload(
            event_type="payment.authorized",
            payment_id="pay_auth_003",
            method="netbanking",
        )
        parsed = parse_razorpay_webhook_payload(payload, event_id_header="evt_003")

        assert parsed.payment is not None
        assert parsed.payment.status == PaymentStatus.AUTHORIZED
        assert parsed.payment.payment_method == PaymentMethod.NETBANKING

    def test_missing_event_field_raises(self):
        with pytest.raises(RazorpayPayloadError, match="'event'"):
            parse_razorpay_webhook_payload({"entity": "event"}, event_id_header="evt_err")

    def test_missing_payment_id_raises(self):
        payload = {
            "event": "payment.captured",
            "payload": {
                "payment": {
                    "entity": {
                        "amount": 1000,
                        "status": "captured",
                    }
                }
            },
        }
        with pytest.raises(RazorpayPayloadError, match="'id'"):
            parse_razorpay_webhook_payload(payload, event_id_header="evt_err")

    def test_invalid_payload_type_raises(self):
        with pytest.raises(RazorpayPayloadError):
            parse_razorpay_webhook_payload("not a dict", event_id_header="evt_err")  # type: ignore[arg-type]
