"""
domain/intelligence/ai/evaluator.py

Comparative benchmark evaluator running scenarios across:
No Intervention vs. Deterministic Baseline vs. AI Decision Agent vs. Simulation Oracle.

ARCHITECTURAL PRINCIPLES (Block 4, Part 14, 15, 16, 17):
- Measures Economic Value Capture (AI Net Revenue / Oracle Net Revenue).
- Computes Net AI Economic Value accounting for inference token costs.
- Tracks agreement, precision, fallback rate, and latency.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.intelligence.ai.models import AIDecisionRecord
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.oracle import SimulationOracleDecisionProvider
from domain.intelligence.simulation.counterfactual import (
    CounterfactualOutcomeSimulator,
    RealizedCounterfactualOutcome,
)
from domain.intelligence.simulation.generator import SyntheticScenarioGenerator
from domain.intelligence.simulation.runner import AlwaysWaitDecisionProvider, PolicyProviderSummary
from domain.shared.enums import RecoveryActionType


@dataclass(frozen=True)
class AIEvaluationSummary:
    """Comprehensive comparative evaluation summary including AI metrics and cost accounting."""

    run_id: uuid.UUID
    scenario_count: int
    seed: int
    duration_ms: float

    # Comparative Provider Metrics
    no_intervention_metrics: PolicyProviderSummary
    baseline_metrics: PolicyProviderSummary
    ai_metrics: PolicyProviderSummary
    oracle_metrics: PolicyProviderSummary

    # AI Decision Quality
    ai_oracle_agreement_rate: float
    ai_baseline_agreement_rate: float
    fallback_rate: float
    fallback_count: int

    # Economic Value Capture Metrics
    economic_value_capture_ratio: float  # AI Net / Oracle Net
    baseline_value_capture_ratio: float  # Baseline Net / Oracle Net
    ai_vs_baseline_net_lift_minor: int   # AI Net - Baseline Net

    # Operational & Token Cost Accounting
    total_input_tokens: int
    total_output_tokens: int
    total_llm_inference_cost_minor: int  # in paise
    net_ai_economic_value_minor: int     # AI Incremental - LLM Cost - Intervention Cost
    average_ai_latency_ms: float
    completed_at: datetime


class AIBenchmarkRunner:
    """
    Executes comparative benchmarks evaluating AI performance against Baseline and Oracle.
    """

    def __init__(self, seed: int = 42, version: str = "v1.0"):
        self.seed = seed
        self.version = version

    async def run_benchmark_async(
        self,
        ai_provider: AIDecisionProvider,
        scenario_count: int = 100,
    ) -> AIEvaluationSummary:
        """Execute benchmark comparing Baseline vs AI vs Oracle."""
        start_time = time.perf_counter()
        run_id = uuid.uuid4()

        generator = SyntheticScenarioGenerator(seed=self.seed, version=self.version)
        scenarios = generator.generate_batch(scenario_count)

        baseline_provider = DeterministicBaselineDecisionProvider()
        oracle_provider = SimulationOracleDecisionProvider()
        wait_provider = AlwaysWaitDecisionProvider()

        # Synchronized simulators for identical counterfactual outcome realization
        sim_wait = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_base = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_ai = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_oracle = CounterfactualOutcomeSimulator(seed=self.seed)

        wait_results = []
        base_results = []
        ai_results = []
        ai_records: list[AIDecisionRecord] = []
        oracle_results = []

        for scn in scenarios:
            # 1. Wait
            dec_wait = wait_provider.evaluate_decision(scn.context, scn.scenario_id)
            out_wait = sim_wait.simulate_outcome(scn, dec_wait)
            wait_results.append((dec_wait, out_wait))

            # 2. Baseline
            dec_base = baseline_provider.evaluate_decision(scn.context, scn.scenario_id)
            out_base = sim_base.simulate_outcome(scn, dec_base)
            base_results.append((dec_base, out_base))

            # 3. AI Provider
            dec_ai = await ai_provider.evaluate_decision_async(scn.context, scn.scenario_id)
            out_ai = sim_ai.simulate_outcome(scn, dec_ai)
            ai_results.append((dec_ai, out_ai))
            if ai_provider.last_decision_record:
                ai_records.append(ai_provider.last_decision_record)

            # 4. Oracle
            dec_oracle = oracle_provider.evaluate_decision_with_ground_truth(
                context=scn.context,
                candidate_economics=scn.ground_truth_candidate_economics,
                natural_recovery_probability=scn.ground_truth_natural_recovery_prob,
                scenario_id=scn.scenario_id,
            )
            out_oracle = sim_oracle.simulate_outcome(scn, dec_oracle)
            oracle_results.append((dec_oracle, out_oracle))

        # Aggregate Provider Summaries
        from domain.intelligence.simulation.runner import ScenarioBatchRunner
        aggregator = ScenarioBatchRunner(seed=self.seed)
        sum_wait = aggregator._aggregate_summary(wait_provider.provider_name, scenarios, wait_results)
        sum_base = aggregator._aggregate_summary(baseline_provider.provider_name, scenarios, base_results)
        sum_ai = aggregator._aggregate_summary(ai_provider.provider_name, scenarios, ai_results)
        sum_oracle = aggregator._aggregate_summary(oracle_provider.provider_name, scenarios, oracle_results)

        # AI-specific Metrics
        agreed_oracle = sum(
            1 for (d_ai, _), (d_or, _) in zip(ai_results, oracle_results)
            if d_ai.recommended_action == d_or.recommended_action
        )
        agreed_base = sum(
            1 for (d_ai, _), (d_ba, _) in zip(ai_results, base_results)
            if d_ai.recommended_action == d_ba.recommended_action
        )
        fallbacks = sum(1 for r in ai_records if r.fallback_used)

        oracle_net = sum_oracle.realized_net_incremental_revenue_minor
        base_net = sum_base.realized_net_incremental_revenue_minor
        ai_net = sum_ai.realized_net_incremental_revenue_minor

        ai_capture = round(ai_net / oracle_net, 4) if oracle_net > 0 else 0.0
        base_capture = round(base_net / oracle_net, 4) if oracle_net > 0 else 0.0
        ai_lift = ai_net - base_net

        total_input_tok = sum(r.input_tokens for r in ai_records)
        total_output_tok = sum(r.output_tokens for r in ai_records)
        total_llm_cost = sum(r.estimated_llm_cost_minor for r in ai_records)
        avg_latency = (
            round(sum(r.latency_ms for r in ai_records) / len(ai_records), 2)
            if ai_records else 0.0
        )

        net_ai_economic_value = ai_net - total_llm_cost
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return AIEvaluationSummary(
            run_id=run_id,
            scenario_count=scenario_count,
            seed=self.seed,
            duration_ms=duration_ms,
            no_intervention_metrics=sum_wait,
            baseline_metrics=sum_base,
            ai_metrics=sum_ai,
            oracle_metrics=sum_oracle,
            ai_oracle_agreement_rate=round(agreed_oracle / scenario_count, 4) if scenario_count else 0.0,
            ai_baseline_agreement_rate=round(agreed_base / scenario_count, 4) if scenario_count else 0.0,
            fallback_rate=round(fallbacks / scenario_count, 4) if scenario_count else 0.0,
            fallback_count=fallbacks,
            economic_value_capture_ratio=ai_capture,
            baseline_value_capture_ratio=base_capture,
            ai_vs_baseline_net_lift_minor=ai_lift,
            total_input_tokens=total_input_tok,
            total_output_tokens=total_output_tok,
            total_llm_inference_cost_minor=total_llm_cost,
            net_ai_economic_value_minor=net_ai_economic_value,
            average_ai_latency_ms=avg_latency,
            completed_at=datetime.now(tz=timezone.utc),
        )

    def run_benchmark(
        self,
        ai_provider: AIDecisionProvider,
        scenario_count: int = 100,
    ) -> AIEvaluationSummary:
        """Synchronous wrapper for run_benchmark_async."""
        import asyncio
        return asyncio.run(self.run_benchmark_async(ai_provider, scenario_count))
