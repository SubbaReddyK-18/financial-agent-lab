"""
infrastructure/database/orm/outbox.py

SQLAlchemy ORM model for transactional recovery action outbox events.

ARCHITECTURAL PRINCIPLES (Block 7, Requirements 3 & 4):
- Atomic Outbox: Outbox records are committed in the SAME database transaction
  as the corresponding RecoveryActionORM record.
- Idempotent Dispatch: Unique constraint on idempotency_key prevents duplicate
  dispatches for the same logical event/action.
- Bounded Retries: Tracks attempt_count, max_attempts, next_attempt_at, and error_message.
- PostgreSQL remains the authoritative transactional source of truth (no Redis/Kafka/Celery).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from infrastructure.database.base import Base


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


class RecoveryOutboxEventORM(Base):
    """
    Persistence model for transactional recovery action outbox events.
    """

    __tablename__ = "recovery_outbox_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_recovery_outbox_idempotency_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    recovery_action_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recovery_actions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recovery_case_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("recovery_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="RECOVERY_ACTION_DISPATCH"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING", index=True
    )
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_utcnow
    )
    processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    action: Mapped["RecoveryActionORM"] = relationship(  # noqa: F821
        "RecoveryActionORM", foreign_keys=[recovery_action_id]
    )
    case: Mapped["RecoveryCaseORM"] = relationship(  # noqa: F821
        "RecoveryCaseORM", foreign_keys=[recovery_case_id]
    )

    def __repr__(self) -> str:
        return (
            f"<RecoveryOutboxEventORM id={self.id} action_id={self.recovery_action_id} "
            f"status={self.status!r} attempts={self.attempt_count}/{self.max_attempts}>"
        )
