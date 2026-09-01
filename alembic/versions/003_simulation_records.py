"""Simulation records schema — Block 3.

Creates the simulation_runs table for storing analytical simulation batches.

Revision ID: 003
Revises: 002
Create Date: 2026-08-31
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "simulation_runs",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("run_name", sa.String(128), nullable=False),
        sa.Column("scenario_count", sa.Integer(), nullable=False),
        sa.Column("seed", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(32), nullable=False, server_default="v1.0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("no_intervention_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("baseline_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("oracle_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_simulation_runs_run_name", "simulation_runs", ["run_name"])
    op.create_index("ix_simulation_runs_seed", "simulation_runs", ["seed"])


def downgrade() -> None:
    op.drop_index("ix_simulation_runs_seed", table_name="simulation_runs")
    op.drop_index("ix_simulation_runs_run_name", table_name="simulation_runs")
    op.drop_table("simulation_runs")
