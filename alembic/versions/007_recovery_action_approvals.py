"""Add attributable recovery action approvals."""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
revision="007"; down_revision="006"; branch_labels=None; depends_on=None
def upgrade():
 op.create_table("recovery_action_approvals",sa.Column("id",postgresql.UUID(as_uuid=True),primary_key=True),sa.Column("recovery_action_id",postgresql.UUID(as_uuid=True),sa.ForeignKey("recovery_actions.id",ondelete="CASCADE"),nullable=False),sa.Column("actor_id",sa.String(128),nullable=False),sa.Column("decision",sa.String(16),nullable=False),sa.Column("reason",sa.String(512)),sa.Column("correlation_id",sa.String(128)),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),sa.UniqueConstraint("recovery_action_id",name="uq_recovery_action_approval_action"))
def downgrade(): op.drop_table("recovery_action_approvals")
