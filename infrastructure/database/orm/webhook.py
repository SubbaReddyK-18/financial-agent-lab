"""
infrastructure/database/orm/webhook.py

SQLAlchemy ORM model for the razorpay_webhook_events table (durable webhook inbox).

Provides auditability, replayability, idempotency tracking, and durable
background processing state for all incoming Razorpay Test Mode webhooks.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class RazorpayWebhookEventORM(Base):
    """
    Persistence model for durable webhook event inbox.

    DB constraint: razorpay_event_id is strictly unique.
    """

    __tablename__ = "razorpay_webhook_events"
    __table_args__ = (
        UniqueConstraint("razorpay_event_id", name="uq_webhook_razorpay_event_id"),
        Index("ix_webhook_events_status", "processing_status"),
        Index("ix_webhook_events_type", "event_type"),
        Index("ix_webhook_events_correlation", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    razorpay_event_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    account_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    raw_payload: Mapped[str] = mapped_column(Text, nullable=False)
    signature: Mapped[str] = mapped_column(String(128), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    event_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="RECEIVED"
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<RazorpayWebhookEventORM id={self.id} "
            f"event_id={self.razorpay_event_id!r} type={self.event_type!r} "
            f"status={self.processing_status!r}>"
        )
