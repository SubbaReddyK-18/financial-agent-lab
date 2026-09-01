"""
infrastructure/database/orm/recovery.py

SQLAlchemy ORM models for recovery cases, recovery actions, and
merchant recovery policies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class MerchantRecoveryPolicyORM(Base):
    """
    Persistence model for MerchantRecoveryPolicy.

    DB constraint: one policy per merchant (UNIQUE on merchant_id).
    Discount stored as integer percent (0–100) — no floating point.
    Thresholds stored as BIGINT minor units.
    """

    __tablename__ = "merchant_recovery_policies"
    __table_args__ = (
        UniqueConstraint("merchant_id", name="uq_policy_merchant"),
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
    )
    # Integer percentage (0–100). No floating point.
    maximum_discount_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    maximum_interventions: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    cooldown_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    # BIGINT minor units — null means no high-value threshold active.
    high_value_threshold_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    high_value_requires_approval: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    low_confidence_requires_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    merchant: Mapped["MerchantORM"] = relationship(  # noqa: F821
        "MerchantORM", back_populates="recovery_policy"
    )

    def __repr__(self) -> str:
        return (
            f"<MerchantRecoveryPolicyORM merchant_id={self.merchant_id} "
            f"max_discount={self.maximum_discount_percent}%>"
        )


class RecoveryCaseORM(Base):
    """Persistence model for RecoveryCase."""

    __tablename__ = "recovery_cases"
    __table_args__ = (
        CheckConstraint(
            "amount_at_risk_minor > 0",
            name="ck_recovery_cases_amount_at_risk_positive",
        ),
        Index(
            "uq_recovery_cases_active_payment",
            "payment_id",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
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
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payments.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # BIGINT minor units (FS-01)
    amount_at_risk_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", index=True)
    opened_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    payment: Mapped["PaymentORM"] = relationship(  # noqa: F821
        "PaymentORM", back_populates="recovery_cases"
    )
    actions: Mapped[list["RecoveryActionORM"]] = relationship(
        "RecoveryActionORM", back_populates="case", lazy="select"
    )

    def __repr__(self) -> str:
        return (
            f"<RecoveryCaseORM id={self.id} payment_id={self.payment_id} "
            f"status={self.status!r}>"
        )


class RecoveryActionORM(Base):
    """
    Persistence model for RecoveryAction.

    metadata_json stores extensible action-specific data (JSONB).
    discount_percent_offered is stored as an integer column for direct
    SQL queries (avoiding JSON extraction for policy auditing).
    """

    __tablename__ = "recovery_actions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_recovery_action_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    recovery_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recovery_cases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    action_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED", index=True)
    # Integer percent (0–100). Direct column for auditing/querying.
    discount_percent_offered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Control Plane & Idempotency
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    execution_attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    superseded_by_action_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Extensible JSONB for action-specific data.
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped["RecoveryCaseORM"] = relationship("RecoveryCaseORM", back_populates="actions")

    def __repr__(self) -> str:
        return (
            f"<RecoveryActionORM id={self.id} type={self.action_type!r} "
            f"status={self.status!r} attempt={self.execution_attempt}>"
        )
