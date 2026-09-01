"""
tests/fixtures/razorpay_webhooks.py

Sanitized synthetic Razorpay webhook fixtures for testing.

Does NOT use real customer information or real API keys.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from infrastructure.security.webhook_verifier import compute_razorpay_signature


def sign_payload(raw_body: bytes, secret: str = "test_webhook_secret_local") -> str:
    """Convenience helper: compute valid HMAC-SHA256 signature for test bytes."""
    return compute_razorpay_signature(raw_body, secret)


import uuid


def build_razorpay_payment_payload(
    *,
    event_type: str,
    payment_id: Optional[str] = None,
    order_id: Optional[str] = None,
    amount_minor: int = 125050,  # ₹1,250.50
    currency: str = "INR",
    payment_status: Optional[str] = None,
    method: str = "upi",
    error_code: Optional[str] = None,
    error_description: Optional[str] = None,
    created_at_epoch: Optional[int] = None,
    account_id: str = "acc_test_merchant_01",
) -> dict[str, Any]:
    """
    Construct a realistic, sanitized Razorpay webhook dictionary.
    """
    if payment_id is None:
        payment_id = f"pay_test_{uuid.uuid4().hex[:12]}"
    if order_id is None:
        order_id = f"order_test_{uuid.uuid4().hex[:12]}"
    if created_at_epoch is None:
        created_at_epoch = int(time.time())

    if payment_status is None:
        if event_type == "payment.captured":
            payment_status = "captured"
        elif event_type == "payment.authorized":
            payment_status = "authorized"
        elif event_type == "payment.failed":
            payment_status = "failed"
            error_code = error_code or "BAD_REQUEST_ERROR"
            error_description = error_description or "Payment was declined by issuing bank."
        else:
            payment_status = "created"

    return {
        "entity": "event",
        "account_id": account_id,
        "event": event_type,
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount_minor,
                    "currency": currency,
                    "status": payment_status,
                    "order_id": order_id,
                    "invoice_id": None,
                    "international": False,
                    "method": method,
                    "amount_refunded": 0,
                    "refund_status": None,
                    "captured": payment_status == "captured",
                    "description": "Financial Agent Lab Test Payment",
                    "card_id": None,
                    "bank": None,
                    "wallet": None,
                    "vpa": "customer@okhdfcbank" if method == "upi" else None,
                    "email": "synthetic_customer@example.com",
                    "contact": "+919876543210",
                    "notes": [],
                    "fee": 250,
                    "tax": 45,
                    "error_code": error_code,
                    "error_description": error_description,
                    "error_source": "issuing_bank" if error_code else None,
                    "error_step": "payment_authentication" if error_code else None,
                    "error_reason": "payment_declined" if error_code else None,
                    "created_at": created_at_epoch,
                }
            }
        },
        "created_at": created_at_epoch,
    }


def build_signed_webhook_request(
    *,
    event_type: str,
    event_id: str = "evt_test_00000001",
    secret: str = "test_webhook_secret_local",
    **payload_kwargs,
) -> tuple[bytes, dict[str, str]]:
    """
    Build raw payload bytes and required headers including valid X-Razorpay-Signature.
    """
    payload_dict = build_razorpay_payment_payload(event_type=event_type, **payload_kwargs)
    raw_body = json.dumps(payload_dict).encode("utf-8")
    signature = sign_payload(raw_body, secret)
    headers = {
        "Content-Type": "application/json",
        "X-Razorpay-Signature": signature,
        "X-Razorpay-Event-Id": event_id,
    }
    return raw_body, headers
