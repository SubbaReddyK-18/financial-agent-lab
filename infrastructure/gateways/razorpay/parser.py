"""
infrastructure/gateways/razorpay/parser.py

Dedicated adapter and parser for Razorpay webhook payloads.

Isolates external Razorpay-specific JSON structures from the core domain.
Translates external event envelopes into typed internal value objects.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from domain.shared.enums import PaymentMethod, PaymentStatus


class RazorpayPayloadError(Exception):
    """Raised when a Razorpay webhook payload is structurally invalid or unparseable."""


@dataclass(frozen=True)
class ParsedPaymentEntity:
    """
    Typed representation of the payment entity extracted from a Razorpay webhook.
    """

    razorpay_payment_id: str
    razorpay_order_id: Optional[str]
    amount_minor: int
    currency: str
    status: PaymentStatus
    payment_method: Optional[PaymentMethod]
    error_code: Optional[str] = None
    error_description: Optional[str] = None
    created_at: Optional[datetime] = None


@dataclass(frozen=True)
class ParsedRazorpayEvent:
    """
    Typed representation of a parsed Razorpay webhook event.
    """

    event_id: str
    event_type: str
    account_id: Optional[str]
    event_created_at: Optional[datetime]
    payment: Optional[ParsedPaymentEntity]
    raw_dict: dict[str, Any]


def _map_payment_status(raw_status: str | None) -> PaymentStatus:
    """Map Razorpay payment status string to domain PaymentStatus."""
    if not raw_status:
        return PaymentStatus.CREATED
    status_lower = raw_status.lower()
    if status_lower == "captured":
        return PaymentStatus.CAPTURED
    if status_lower == "authorized":
        return PaymentStatus.AUTHORIZED
    if status_lower == "failed":
        return PaymentStatus.FAILED
    if status_lower == "refunded":
        return PaymentStatus.REFUNDED
    if status_lower == "created":
        return PaymentStatus.CREATED
    raise RazorpayPayloadError(f"Unrecognized Razorpay payment status: {raw_status!r}")


def _map_payment_method(raw_method: str | None) -> Optional[PaymentMethod]:
    """Map Razorpay payment method string to domain PaymentMethod."""
    if not raw_method:
        return None
    method_lower = raw_method.lower()
    if method_lower in {"card", "credit_card", "debit_card"}:
        return PaymentMethod.CARD
    if method_lower == "upi":
        return PaymentMethod.UPI
    if method_lower in {"netbanking", "net_banking"}:
        return PaymentMethod.NETBANKING
    if method_lower == "wallet":
        return PaymentMethod.WALLET
    return PaymentMethod.UNKNOWN


def _parse_unix_timestamp(ts: Any) -> Optional[datetime]:
    """Convert Unix epoch integer to timezone-aware UTC datetime."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def parse_razorpay_webhook_payload(
    payload_dict: dict[str, Any],
    event_id_header: str,
) -> ParsedRazorpayEvent:
    """
    Parse and validate a decoded Razorpay webhook payload dictionary.

    Args:
        payload_dict: The decoded JSON dictionary from the webhook request.
        event_id_header: The value from the X-Razorpay-Event-Id header (fallback to body if present).

    Returns:
        ParsedRazorpayEvent typed object.

    Raises:
        RazorpayPayloadError: if the structure is missing required event fields.
    """
    if not isinstance(payload_dict, dict):
        raise RazorpayPayloadError("Webhook payload must be a JSON object.")

    event_type = payload_dict.get("event")
    if not event_type or not isinstance(event_type, str):
        raise RazorpayPayloadError("Webhook payload missing 'event' field.")

    account_id = payload_dict.get("account_id")
    event_created_at = _parse_unix_timestamp(payload_dict.get("created_at"))

    # Extract payment entity if contained in payload
    payment_entity: Optional[ParsedPaymentEntity] = None
    payload_section = payload_dict.get("payload", {})
    if isinstance(payload_section, dict):
        payment_data = payload_section.get("payment", {}).get("entity")
        if isinstance(payment_data, dict):
            pay_id = payment_data.get("id")
            if not pay_id or not isinstance(pay_id, str):
                raise RazorpayPayloadError("Payment entity missing 'id' field.")

            amount = payment_data.get("amount")
            if amount is None or not isinstance(amount, int) or amount < 0:
                raise RazorpayPayloadError("Payment entity missing valid integer 'amount'.")

            currency = payment_data.get("currency", "INR")
            raw_status = payment_data.get("status")
            status = _map_payment_status(raw_status)
            method = _map_payment_method(payment_data.get("method"))
            order_id = payment_data.get("order_id")
            error_code = payment_data.get("error_code")
            error_description = payment_data.get("error_description")
            payment_created_at = _parse_unix_timestamp(payment_data.get("created_at"))

            payment_entity = ParsedPaymentEntity(
                razorpay_payment_id=pay_id,
                razorpay_order_id=order_id if isinstance(order_id, str) else None,
                amount_minor=amount,
                currency=currency,
                status=status,
                payment_method=method,
                error_code=str(error_code) if error_code is not None else None,
                error_description=str(error_description) if error_description is not None else None,
                created_at=payment_created_at,
            )

    return ParsedRazorpayEvent(
        event_id=event_id_header,
        event_type=event_type,
        account_id=str(account_id) if account_id is not None else None,
        event_created_at=event_created_at,
        payment=payment_entity,
        raw_dict=payload_dict,
    )
