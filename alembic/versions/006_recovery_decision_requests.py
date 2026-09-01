"""Add durable recovery decision requests."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None
def upgrade():
    op.create_table("recovery_decision_requests", sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True), sa.Column("recovery_case_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("recovery_cases.id", ondelete="CASCADE"), nullable=False), sa.Column("payment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payments.id", ondelete="RESTRICT"), nullable=False), sa.Column("status", sa.String(32), nullable=False, server_default="PENDING"), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"), sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"), sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.Column("processed_at", sa.DateTime(timezone=True)), sa.Column("error_message", sa.String(512)), sa.Column("correlation_id", sa.String(128)), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()), sa.UniqueConstraint("idempotency_key", name="uq_recovery_decision_request_idempotency_key"))
    op.create_index("ix_recovery_decision_requests_status", "recovery_decision_requests", ["status"])
    op.create_index("ix_recovery_decision_requests_case", "recovery_decision_requests", ["recovery_case_id"])
def downgrade():
    op.drop_table("recovery_decision_requests")
