"""
infrastructure/database/orm/simulation.py

SQLAlchemy ORM model for persisting simulation run benchmarks and aggregate metrics.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from infrastructure.database.base import Base


class SimulationRunORM(Base):
    """
    Persisted record of an analytical simulation batch run.
    """

    __tablename__ = "simulation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=func.gen_random_uuid(),
    )
    run_name: Mapped[str] = mapped_column(String(128), nullable=False)
    scenario_count: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False, default="v1.0")
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False)

    no_intervention_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    baseline_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    oracle_metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
