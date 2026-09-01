"""
domain/observability/version_comparison.py

Model & prompt version comparison evaluator.

ARCHITECTURAL PRINCIPLES (Block 6, Requirement 6):
1. Enables evaluating whether Model X / Prompt Y performs better than Model A / Prompt B.
2. Compares value capture, regret, fallback rates, latency, token costs, and net value.
3. Completely provider-agnostic without hard-coded assumptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.intelligence.ai.provider import AIDecisionProvider
from domain.observability.simulation_evaluator import (
    AdvancedSimulationEvaluator,
    SimulationEvaluationReport,
)


@dataclass(frozen=True)
class ModelVersionCandidate:
    """Configuration for an evaluation candidate."""

    name: str  # e.g. "Gemini 2.5 Flash (v1.2 prompt)"
    provider: AIDecisionProvider
    version_tag: str = "v1.0"


@dataclass(frozen=True)
class VersionComparisonDelta:
    """Comparative differential between Candidate B (Challenger) and Candidate A (Baseline/Champion)."""

    champion_name: str
    challenger_name: str
    value_capture_ratio_delta: float
    mean_regret_delta_minor: int
    fallback_rate_delta: float
    avg_latency_ms_delta: float
    total_cost_delta_minor: int
    net_economic_value_delta_minor: int
    is_challenger_superior: bool


@dataclass(frozen=True)
class MultiVersionComparisonReport:
    """Full comparative report across multiple model/prompt versions."""

    scenario_count: int
    seed: int
    candidates: list[SimulationEvaluationReport]
    deltas: list[VersionComparisonDelta]


class ModelVersionComparator:
    """Runs identical synthetic benchmark batches across multiple model candidates to assess relative performance."""

    def __init__(self, seed: int = 42, version: str = "v1.0"):
        self.seed = seed
        self.version = version

    async def compare_candidates_async(
        self,
        candidates: list[ModelVersionCandidate],
        scenario_count: int = 100,
    ) -> MultiVersionComparisonReport:
        """Run identical evaluation across all model candidates."""
        evaluator = AdvancedSimulationEvaluator(seed=self.seed, version=self.version)
        reports: list[SimulationEvaluationReport] = []

        for cand in candidates:
            report = await evaluator.evaluate_async(
                ai_provider=cand.provider,
                scenario_count=scenario_count,
            )
            reports.append(report)

        deltas: list[VersionComparisonDelta] = []
        if len(reports) >= 2:
            champion = reports[0]
            for challenger in reports[1:]:
                v_delta = round(challenger.economic_value_capture_ratio - champion.economic_value_capture_ratio, 4)
                r_delta = challenger.regret.mean_regret_minor - champion.regret.mean_regret_minor
                f_delta = round(challenger.fallback_rate - champion.fallback_rate, 4)
                lat_delta = round(challenger.average_ai_latency_ms - champion.average_ai_latency_ms, 2)
                cost_delta = challenger.total_llm_inference_cost_minor - champion.total_llm_inference_cost_minor
                net_val_delta = (
                    challenger.ai_metrics.realized_net_incremental_revenue_minor
                    - champion.ai_metrics.realized_net_incremental_revenue_minor
                )

                # Superior if higher value capture AND lower or equal regret
                superior = (v_delta > 0.0) or (net_val_delta > 0 and r_delta <= 0)

                deltas.append(
                    VersionComparisonDelta(
                        champion_name=candidates[0].name,
                        challenger_name=candidates[len(deltas) + 1].name,
                        value_capture_ratio_delta=v_delta,
                        mean_regret_delta_minor=r_delta,
                        fallback_rate_delta=f_delta,
                        avg_latency_ms_delta=lat_delta,
                        total_cost_delta_minor=cost_delta,
                        net_economic_value_delta_minor=net_val_delta,
                        is_challenger_superior=superior,
                    )
                )

        return MultiVersionComparisonReport(
            scenario_count=scenario_count,
            seed=self.seed,
            candidates=reports,
            deltas=deltas,
        )
