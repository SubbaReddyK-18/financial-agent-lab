"""
apps/api/routes/simulation.py

Analytical API endpoints for running simulation experiments and retrieving results.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.intelligence.simulation.runner import ScenarioBatchRunner
from infrastructure.database.connection import get_db_session
from infrastructure.database.orm.simulation import SimulationRunORM

router = APIRouter(prefix="/simulation", tags=["Simulation"])


class RunSimulationRequest(BaseModel):
    scenario_count: int = Field(default=1000, ge=1, le=50000, description="Number of synthetic scenarios to evaluate.")
    seed: int = Field(default=42, description="Random seed for reproducibility.")
    run_name: str = Field(default="lab_simulation_experiment", max_length=128)


class PolicySummaryResponse(BaseModel):
    provider_name: str
    scenario_count: int
    total_amount_at_risk_minor: int
    expected_gross_revenue_minor: int
    expected_natural_revenue_minor: int
    expected_incremental_revenue_minor: int
    expected_net_incremental_revenue_minor: int
    realized_gross_revenue_minor: int
    realized_natural_revenue_minor: int
    realized_incremental_revenue_minor: int
    realized_net_incremental_revenue_minor: int
    total_interventions: int
    intervention_rate: float
    unnecessary_interventions: int
    unnecessary_intervention_rate: float
    missed_opportunities: int
    missed_opportunity_rate: float
    policy_overrides_count: int
    action_distribution: dict[str, int]


class SimulationRunResponse(BaseModel):
    run_id: uuid.UUID
    run_name: str
    scenario_count: int
    seed: int
    version: str
    duration_ms: float
    no_intervention_metrics: PolicySummaryResponse
    baseline_metrics: PolicySummaryResponse
    oracle_metrics: PolicySummaryResponse


@router.post(
    "/run",
    status_code=status.HTTP_201_CREATED,
    response_model=SimulationRunResponse,
    summary="Execute a batch simulation experiment comparing Baseline vs Oracle.",
)
async def run_simulation_experiment(
    req: RunSimulationRequest,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    runner = ScenarioBatchRunner(seed=req.seed)
    result = runner.run_benchmark(scenario_count=req.scenario_count, run_name=req.run_name)

    # Persist simulation run to database
    orm_record = SimulationRunORM(
        id=result.run_id,
        run_name=result.run_name,
        scenario_count=result.scenario_count,
        seed=result.seed,
        version=result.version,
        duration_ms=int(result.duration_ms),
        no_intervention_metrics=asdict(result.no_intervention_metrics),
        baseline_metrics=asdict(result.baseline_metrics),
        oracle_metrics=asdict(result.oracle_metrics),
        completed_at=result.completed_at,
    )
    db.add(orm_record)
    await db.flush()

    return SimulationRunResponse(
        run_id=result.run_id,
        run_name=result.run_name,
        scenario_count=result.scenario_count,
        seed=result.seed,
        version=result.version,
        duration_ms=result.duration_ms,
        no_intervention_metrics=PolicySummaryResponse(**asdict(result.no_intervention_metrics)),
        baseline_metrics=PolicySummaryResponse(**asdict(result.baseline_metrics)),
        oracle_metrics=PolicySummaryResponse(**asdict(result.oracle_metrics)),
    )


@router.get(
    "/runs/{run_id}",
    response_model=SimulationRunResponse,
    summary="Retrieve full results for a previously executed simulation run.",
)
async def get_simulation_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    record = await db.get(SimulationRunORM, run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation run '{run_id}' not found.",
        )

    return SimulationRunResponse(
        run_id=record.id,
        run_name=record.run_name,
        scenario_count=record.scenario_count,
        seed=record.seed,
        version=record.version,
        duration_ms=float(record.duration_ms),
        no_intervention_metrics=PolicySummaryResponse(**record.no_intervention_metrics),
        baseline_metrics=PolicySummaryResponse(**record.baseline_metrics),
        oracle_metrics=PolicySummaryResponse(**record.oracle_metrics),
    )


@router.get(
    "/runs/{run_id}/summary",
    summary="Retrieve a high-level comparative executive summary of a simulation run.",
)
async def get_simulation_run_summary(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    record = await db.get(SimulationRunORM, run_id)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation run '{run_id}' not found.",
        )

    base = record.baseline_metrics
    oracle = record.oracle_metrics
    wait = record.no_intervention_metrics

    return {
        "run_id": record.id,
        "run_name": record.run_name,
        "scenario_count": record.scenario_count,
        "duration_ms": record.duration_ms,
        "total_amount_at_risk_inr": record.baseline_metrics["total_amount_at_risk_minor"] / 100.0,
        "comparisons": {
            "no_intervention": {
                "realized_net_incremental_revenue_inr": wait["realized_net_incremental_revenue_minor"] / 100.0,
                "intervention_rate": wait["intervention_rate"],
            },
            "deterministic_baseline": {
                "realized_net_incremental_revenue_inr": base["realized_net_incremental_revenue_minor"] / 100.0,
                "intervention_rate": base["intervention_rate"],
                "unnecessary_intervention_rate": base["unnecessary_intervention_rate"],
                "missed_opportunity_rate": base["missed_opportunity_rate"],
            },
            "simulation_oracle": {
                "realized_net_incremental_revenue_inr": oracle["realized_net_incremental_revenue_minor"] / 100.0,
                "intervention_rate": oracle["intervention_rate"],
                "unnecessary_intervention_rate": oracle["unnecessary_intervention_rate"],
                "missed_opportunity_rate": oracle["missed_opportunity_rate"],
            },
        },
    }
