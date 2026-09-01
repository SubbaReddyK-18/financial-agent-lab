"""
infrastructure/database/orm/ai.py

SQLAlchemy ORM model for persisting AI recovery decision audit records.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.base import Base


class AIDecisionRecordORM(Base):
    """
    Persisted audit record of an AI recovery decision.
    """

    __tablename__ = "ai_decision_records"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    scenario_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    # Block 9 audit-chain references.  Legacy/simulation decisions may omit
    # these while recovery orchestration supplies all applicable identities.
    recovery_case_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recovery_cases.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    decision_request_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recovery_decision_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    recovery_action_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("recovery_actions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    financial_event_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_events.id", ondelete="SET NULL"), nullable=True
    )
    correlation_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    audit_schema_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    agent_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    recommended_action: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning_codes: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    uncertainty: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    requires_human_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_llm_cost_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    final_action: Mapped[str] = mapped_column(String(32), nullable=False)
    expected_net_incremental_revenue_minor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Sanitized, structured snapshots. These are audit evidence only; current
    # payment state and execution state remain authoritative in their tables.
    context_snapshot_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proposal_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    proposal_validation_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    policy_result_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    authorization_result_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    economic_candidates_json: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")
    selection_result_json: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
