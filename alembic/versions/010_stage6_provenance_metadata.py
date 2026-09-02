"""Add prompt provenance and agent-bundle version metadata for Stage 6.

Adds:
- ai_decision_records.prompt_hash    — SHA-256 of the system prompt at inference time
- ai_decision_records.agent_version  — agent-bundle version identifier
- simulation_runs.prompt_hash        — prompt hash for reproducible evaluation provenance
- simulation_runs.agent_bundle_version — agent bundle version for reproducible evaluation

Revision ID: 010
Revises: 009
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -------------------------------------------------------------------------
    # ai_decision_records: prompt provenance columns
    # -------------------------------------------------------------------------
    # prompt_hash: SHA-256 hex digest of the system prompt text used at inference.
    # Allows forensic verification that a decision was made with a known prompt version.
    op.add_column(
        "ai_decision_records",
        sa.Column("prompt_hash", sa.String(64), nullable=True),
    )
    # agent_version: composite identifier of the agent-bundle deployed at inference time.
    # E.g. "recovery-decision-agent/v1". Enables per-version performance tracking.
    op.add_column(
        "ai_decision_records",
        sa.Column("agent_version", sa.String(64), nullable=True),
    )

    # -------------------------------------------------------------------------
    # simulation_runs: provenance columns for reproducible evaluation
    # -------------------------------------------------------------------------
    # Records which prompt/agent-bundle was active when a simulation batch ran,
    # enabling meaningful before/after version comparisons.
    op.add_column(
        "simulation_runs",
        sa.Column("prompt_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "simulation_runs",
        sa.Column("agent_bundle_version", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("simulation_runs", "agent_bundle_version")
    op.drop_column("simulation_runs", "prompt_hash")
    op.drop_column("ai_decision_records", "agent_version")
    op.drop_column("ai_decision_records", "prompt_hash")
