"""Durable requests for asynchronous recovery decisioning."""
import uuid
from datetime import datetime, timezone
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from infrastructure.database.base import Base

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)

class RecoveryDecisionRequestORM(Base):
    __tablename__ = "recovery_decision_requests"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_recovery_decision_request_idempotency_key"),
        UniqueConstraint("recovery_case_id", name="uq_recovery_decision_request_case"),
        CheckConstraint("attempt_count >= 0", name="ck_decision_request_attempt_count_nonnegative"),
        CheckConstraint("max_attempts >= 1", name="ck_decision_request_max_attempts_positive"),
        CheckConstraint("attempt_count <= max_attempts", name="ck_decision_request_attempt_count_bounded"),
    )
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    recovery_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("recovery_cases.id", ondelete="CASCADE"), nullable=False, index=True)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
