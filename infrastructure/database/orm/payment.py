"""
infrastructure/database/orm/payment.py

SQLAlchemy ORM models for orders, payments, and payment attempts.

IMPORTANT INTEGRITY RULES (P-08):
- amount_minor uses BigInteger — never Float or Numeric with scale > 0.
- PaymentAttempt.attempt_number is unique per payment (DB constraint).
- Payment.order_id is non-nullable; a payment must belong to an order.
- Currency is stored as a 3-char ISO 4217 string.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class OrderORM(Base):
    """Persistence model for Order."""

    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_orders_amount_minor_positive"),
        Index(
            "uq_orders_razorpay_order_id",
            "razorpay_order_id",
            unique=True,
            postgresql_where=text("razorpay_order_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # FS-01: amount stored as integer minor units (BigInteger = BIGINT in PG)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    razorpay_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    payments: Mapped[list["PaymentORM"]] = relationship(
        "PaymentORM", back_populates="order", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<OrderORM id={self.id} amount_minor={self.amount_minor} status={self.status!r}>"


class PaymentORM(Base):
    """Persistence model for Payment."""

    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_payments_amount_minor_positive"),
        Index(
            "uq_payments_razorpay_payment_id",
            "razorpay_payment_id",
            unique=True,
            postgresql_where=text("razorpay_payment_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # FS-01: BIGINT for monetary amounts — never FLOAT or NUMERIC(x,y)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED", index=True)
    payment_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    order: Mapped["OrderORM"] = relationship("OrderORM", back_populates="payments")
    attempts: Mapped[list["PaymentAttemptORM"]] = relationship(
        "PaymentAttemptORM", back_populates="payment", lazy="select"
    )
    recovery_cases: Mapped[list["RecoveryCaseORM"]] = relationship(  # noqa: F821
        "RecoveryCaseORM", back_populates="payment", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<PaymentORM id={self.id} amount_minor={self.amount_minor} "
            f"status={self.status!r}>"
        )


class PaymentAttemptORM(Base):
    """
    Persistence model for PaymentAttempt.

    DB constraint: (payment_id, attempt_number) must be unique.
    This prevents two attempts with the same number for the same payment.
    """

    __tablename__ = "payment_attempts"
    __table_args__ = (
        UniqueConstraint("payment_id", "attempt_number", name="uq_attempt_payment_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    failure_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    payment: Mapped["PaymentORM"] = relationship("PaymentORM", back_populates="attempts")

    def __repr__(self) -> str:
        return (
            f"<PaymentAttemptORM id={self.id} payment_id={self.payment_id} "
            f"attempt_number={self.attempt_number} status={self.status!r}>"
        )
