"""
infrastructure/database/orm/customer.py

SQLAlchemy ORM model for the customers table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class CustomerORM(Base):
    """Persistence model for Customer."""

    __tablename__ = "customers"
    __table_args__ = (
        # A merchant's external_reference must be unique per merchant
        # when provided. Partial uniqueness (NULLs not constrained) is
        # handled by a conditional unique index in Alembic.
        UniqueConstraint("merchant_id", "external_reference", name="uq_customer_merchant_extref"),
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
    external_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    merchant: Mapped["MerchantORM"] = relationship(  # noqa: F821
        "MerchantORM", back_populates="customers"
    )

    def __repr__(self) -> str:
        return f"<CustomerORM id={self.id} merchant_id={self.merchant_id}>"
