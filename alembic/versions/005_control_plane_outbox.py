"""Control plane and transactional outbox schema — Block 7.

Adds idempotency, retry, and superseded fields to recovery_actions table
and creates recovery_outbox_events table for reliable dispatch.

Revision ID: 005
Revises: 004
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add control plane columns to recovery_actions
    op.add_column(
        "recovery_actions",
        sa.Column("idempotency_key", sa.String(128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_recovery_action_idempotency_key",
        "recovery_actions",
        ["idempotency_key"],
    )
    op.add_column(
        "recovery_actions",
        sa.Column("execution_attempt", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "recovery_actions",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "recovery_actions",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "recovery_actions",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "recovery_actions",
        sa.Column("failure_reason", sa.String(512), nullable=True),
    )
    op.add_column(
        "recovery_actions",
        sa.Column("superseded_by_action_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # 2. Create recovery_outbox_events table
    op.create_table(
        "recovery_outbox_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "recovery_action_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recovery_actions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recovery_case_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("recovery_cases.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(64), nullable=False, server_default="RECOVERY_ACTION_DISPATCH"),
        sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_recovery_outbox_idempotency_key"),
    )
    op.create_index("ix_recovery_outbox_action_id", "recovery_outbox_events", ["recovery_action_id"])
    op.create_index("ix_recovery_outbox_case_id", "recovery_outbox_events", ["recovery_case_id"])
    op.create_index("ix_recovery_outbox_status", "recovery_outbox_events", ["status"])
    op.create_index("ix_recovery_outbox_next_attempt_at", "recovery_outbox_events", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_table("recovery_outbox_events")
    op.drop_constraint("uq_recovery_action_idempotency_key", "recovery_actions", type_="unique")
    op.drop_column("recovery_actions", "superseded_by_action_id")
    op.drop_column("recovery_actions", "failure_reason")
    op.drop_column("recovery_actions", "next_retry_at")
    op.drop_column("recovery_actions", "retry_count")
    op.drop_column("recovery_actions", "max_retries")
    op.drop_column("recovery_actions", "execution_attempt")
    op.drop_column("recovery_actions", "idempotency_key")
