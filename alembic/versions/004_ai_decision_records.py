"""AI decision records schema — Block 4.

Creates the ai_decision_records table for storing AI recovery decision audits.

Revision ID: 004
Revises: 003
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ai_decision_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("scenario_id", sa.String(64), nullable=True),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_version", sa.String(32), nullable=False),
        sa.Column("recommended_action", sa.String(32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasoning_codes", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("uncertainty", sa.String(16), nullable=False, server_default="MEDIUM"),
        sa.Column("requires_human_review", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("fallback_reason", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Float(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimated_llm_cost_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("final_action", sa.String(32), nullable=False),
        sa.Column("expected_net_incremental_revenue_minor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_ai_decision_records_scenario_id", "ai_decision_records", ["scenario_id"])
    op.create_index("ix_ai_decision_records_recommended_action", "ai_decision_records", ["recommended_action"])


def downgrade() -> None:
    op.drop_index("ix_ai_decision_records_recommended_action", table_name="ai_decision_records")
    op.drop_index("ix_ai_decision_records_scenario_id", table_name="ai_decision_records")
    op.drop_table("ai_decision_records")
