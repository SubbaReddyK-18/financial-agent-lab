"""
infrastructure/database/orm/merchant.py

SQLAlchemy ORM model for the merchants table.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class MerchantORM(Base):
    """Persistence model for Merchant."""

    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )

    # Relationships (back-populated from child tables)
    customers: Mapped[list["CustomerORM"]] = relationship(  # noqa: F821
        "CustomerORM", back_populates="merchant", lazy="select"
    )
    recovery_policy: Mapped["MerchantRecoveryPolicyORM"] = relationship(  # noqa: F821
        "MerchantRecoveryPolicyORM", back_populates="merchant", uselist=False, lazy="select"
    )

    def __repr__(self) -> str:
        return f"<MerchantORM id={self.id} name={self.name!r}>"
