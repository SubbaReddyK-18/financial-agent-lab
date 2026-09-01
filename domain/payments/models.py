"""
domain/payments/models.py

Payment domain entities: Order, Payment, PaymentAttempt.

KEY DESIGN DECISIONS:
- Payment and PaymentAttempt are deliberately separate concepts.
  One Payment can have multiple PaymentAttempts (e.g. card decline, retry).
- Amounts are stored as integer minor units (FS-01). No floats.
- State transitions are NOT enforced here; see state_machine.py.
  Models are mutable data containers; the state machine enforces correctness.
- payment_method is optional because it may be unknown at Payment creation.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.shared.enums import (
    Currency,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentMethod,
    PaymentStatus,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# Order
# ---------------------------------------------------------------------------

@dataclass
class Order:
    """
    A merchant's order, representing commercial intent.

    One Order may have at most one active Payment in the MVP.
    (Multiple payment attempts are tracked at the PaymentAttempt level,
    not at the Order level.)

    Attributes:
        id:            Globally unique identifier (UUID).
        merchant_id:   Owning merchant.
        customer_id:   Customer who placed the order.
        amount_minor:  Order value in currency minor units (e.g. paise).
        currency:      ISO 4217 currency code.
        status:        Current OrderStatus.
        created_at:    UTC timestamp.
        updated_at:    UTC timestamp.
    """

    merchant_id: uuid.UUID
    customer_id: uuid.UUID
    amount_minor: int
    currency: str = Currency.INR
    status: OrderStatus = OrderStatus.CREATED
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise TypeError(
                f"Order.amount_minor must be int, got {type(self.amount_minor).__name__}. "
                "Floating-point amounts are forbidden (FS-01)."
            )
        if self.amount_minor <= 0:
            raise ValueError(f"Order.amount_minor must be positive, got {self.amount_minor}.")
        if self.currency not in {c.value for c in Currency}:
            raise ValueError(f"Unsupported currency: {self.currency!r}")

    def __repr__(self) -> str:
        return (
            f"Order(id={self.id}, amount_minor={self.amount_minor}, "
            f"currency={self.currency!r}, status={self.status!r})"
        )


# ---------------------------------------------------------------------------
# Payment
# ---------------------------------------------------------------------------

@dataclass
class Payment:
    """
    A payment against an Order.

    IMPORTANT: This entity represents the payment lifecycle overall.
    Individual gateway/network attempts are tracked by PaymentAttempt.

    State transitions are validated by domain/payments/state_machine.py,
    not by this class directly.

    Attributes:
        id:             Globally unique identifier (UUID).
        order_id:       The order this payment is for.
        customer_id:    The paying customer.
        amount_minor:   Payment amount in minor units (must equal order amount).
        currency:       ISO 4217 currency code.
        status:         Current PaymentStatus.
        payment_method: How the customer is paying (may be unknown at creation).
        created_at:     UTC timestamp.
        updated_at:     UTC timestamp.
    """

    order_id: uuid.UUID
    customer_id: uuid.UUID
    amount_minor: int
    currency: str = Currency.INR
    status: PaymentStatus = PaymentStatus.CREATED
    payment_method: Optional[PaymentMethod] = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise TypeError(
                f"Payment.amount_minor must be int, got {type(self.amount_minor).__name__}. "
                "Floating-point amounts are forbidden (FS-01)."
            )
        if self.amount_minor <= 0:
            raise ValueError(f"Payment.amount_minor must be positive, got {self.amount_minor}.")
        if self.currency not in {c.value for c in Currency}:
            raise ValueError(f"Unsupported currency: {self.currency!r}")

    def is_failed(self) -> bool:
        return self.status == PaymentStatus.FAILED

    def is_captured(self) -> bool:
        return self.status == PaymentStatus.CAPTURED

    def is_terminal(self) -> bool:
        """Return True if no further state progression is expected."""
        return self.status in {PaymentStatus.CAPTURED, PaymentStatus.REFUNDED}

    def __repr__(self) -> str:
        return (
            f"Payment(id={self.id}, order_id={self.order_id}, "
            f"amount_minor={self.amount_minor}, currency={self.currency!r}, "
            f"status={self.status!r})"
        )


# ---------------------------------------------------------------------------
# PaymentAttempt
# ---------------------------------------------------------------------------

@dataclass
class PaymentAttempt:
    """
    A single network/gateway attempt to process a Payment.

    Design: Payment and PaymentAttempt are DIFFERENT entities.
    - Payment tracks the overall lifecycle.
    - PaymentAttempt tracks each individual attempt (e.g. card network call).

    A FAILED PaymentAttempt does not necessarily mean the Payment is FAILED —
    a retry may succeed on a subsequent attempt.

    Attributes:
        id:             Globally unique identifier (UUID).
        payment_id:     The parent Payment.
        attempt_number: Sequential attempt number (1-indexed). Must be unique
                        per payment. Enforced at the DB level.
        status:         Current attempt status.
        failure_code:   Gateway/network failure code (e.g. "INSUFFICIENT_FUNDS").
        failure_reason: Human-readable failure description.
        attempted_at:   When the attempt was initiated (UTC).
    """

    payment_id: uuid.UUID
    attempt_number: int
    status: PaymentAttemptStatus = PaymentAttemptStatus.PENDING
    failure_code: Optional[str] = None
    failure_reason: Optional[str] = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    attempted_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError(
                f"attempt_number must be >= 1, got {self.attempt_number}."
            )
        # failure fields are only meaningful when status is FAILED
        if self.status != PaymentAttemptStatus.FAILED:
            if self.failure_code is not None or self.failure_reason is not None:
                raise ValueError(
                    "failure_code and failure_reason must be None when status is not FAILED."
                )

    def is_terminal(self) -> bool:
        return self.status in {
            PaymentAttemptStatus.SUCCESS,
            PaymentAttemptStatus.FAILED,
            PaymentAttemptStatus.TIMEOUT,
        }

    def __repr__(self) -> str:
        return (
            f"PaymentAttempt(id={self.id}, payment_id={self.payment_id}, "
            f"attempt_number={self.attempt_number}, status={self.status!r})"
        )
