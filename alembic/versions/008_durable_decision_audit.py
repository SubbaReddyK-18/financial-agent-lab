"""Expand durable recovery decision audit snapshots and references."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ai_decision_records", sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_decision_records", sa.Column("payment_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_decision_records", sa.Column("decision_request_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_decision_records", sa.Column("recovery_action_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_decision_records", sa.Column("financial_event_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("ai_decision_records", sa.Column("correlation_id", sa.String(128), nullable=True))
    op.add_column("ai_decision_records", sa.Column("audit_schema_version", sa.String(16), nullable=False, server_default="1"))
    op.add_column("ai_decision_records", sa.Column("context_snapshot_json", postgresql.JSONB(), nullable=True))
    op.add_column("ai_decision_records", sa.Column("proposal_json", postgresql.JSONB(), nullable=True))
    op.add_column("ai_decision_records", sa.Column("proposal_validation_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("ai_decision_records", sa.Column("policy_result_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("ai_decision_records", sa.Column("authorization_result_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.add_column("ai_decision_records", sa.Column("economic_candidates_json", postgresql.JSONB(), nullable=False, server_default="[]"))
    op.add_column("ai_decision_records", sa.Column("selection_result_json", postgresql.JSONB(), nullable=False, server_default="{}"))
    op.create_foreign_key("fk_ai_decision_recovery_case", "ai_decision_records", "recovery_cases", ["recovery_case_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_ai_decision_payment", "ai_decision_records", "payments", ["payment_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_ai_decision_request", "ai_decision_records", "recovery_decision_requests", ["decision_request_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_ai_decision_action", "ai_decision_records", "recovery_actions", ["recovery_action_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_ai_decision_financial_event", "ai_decision_records", "financial_events", ["financial_event_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_ai_decision_records_recovery_case_id", "ai_decision_records", ["recovery_case_id"])
    op.create_index("ix_ai_decision_records_payment_id", "ai_decision_records", ["payment_id"])
    op.create_index("ix_ai_decision_records_decision_request_id", "ai_decision_records", ["decision_request_id"])
    op.create_index("ix_ai_decision_records_recovery_action_id", "ai_decision_records", ["recovery_action_id"])
    op.create_index("ix_ai_decision_records_correlation_id", "ai_decision_records", ["correlation_id"])


def downgrade():
    for index in ("ix_ai_decision_records_correlation_id", "ix_ai_decision_records_recovery_action_id", "ix_ai_decision_records_decision_request_id", "ix_ai_decision_records_payment_id", "ix_ai_decision_records_recovery_case_id"):
        op.drop_index(index, table_name="ai_decision_records")
    for constraint in ("fk_ai_decision_financial_event", "fk_ai_decision_action", "fk_ai_decision_request", "fk_ai_decision_payment", "fk_ai_decision_recovery_case"):
        op.drop_constraint(constraint, "ai_decision_records", type_="foreignkey")
    for column in ("selection_result_json", "economic_candidates_json", "authorization_result_json", "policy_result_json", "proposal_validation_json", "proposal_json", "context_snapshot_json", "audit_schema_version", "correlation_id", "financial_event_id", "recovery_action_id", "decision_request_id", "payment_id", "recovery_case_id"):
        op.drop_column("ai_decision_records", column)
