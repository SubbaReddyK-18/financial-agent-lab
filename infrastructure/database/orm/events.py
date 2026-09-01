"""
infrastructure/database/orm/events.py

SQLAlchemy ORM model for FinancialEvent.

Financial events are the durable record of every important state transition.
This table is append-only (FS-07): no updates, no deletes.

The outbox pattern (Block 2) will use this table (or a separate outbox table)
to guarantee at-least-once delivery of domain events to downstream consumers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class FinancialEventORM(Base):
    """
    Immutable record of a domain event.

    DO NOT add UPDATE or DELETE operations on this table.
    Corrections are new append-only records referencing the superseded event.
    """

    __tablename__ = "financial_events"
    __table_args__ = (
        # Efficiently query all events for a given aggregate.
        Index("ix_financial_events_aggregate", "aggregate_type", "aggregate_id"),
        # Efficiently query events by type (e.g. all PAYMENT_FAILED events).
        Index("ix_financial_events_type", "event_type"),
        # Correlation ID index for tracing event chains.
        Index("ix_financial_events_correlation", "correlation_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # aggregate_id stored as string to accommodate any UUID-based aggregate.
    aggregate_id: Mapped[str] = mapped_column(String(36), nullable=False)
    # occurred_at: when the event happened in the domain (may differ from created_at)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # payload: the full event data. Schema is versioned via schema_version field within.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # correlation_id: links related events across aggregate boundaries.
    correlation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    # created_at: when this record was inserted (always server time).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )

    def __repr__(self) -> str:
        return (
            f"<FinancialEventORM id={self.id} type={self.event_type!r} "
            f"aggregate={self.aggregate_type}/{self.aggregate_id}>"
        )
