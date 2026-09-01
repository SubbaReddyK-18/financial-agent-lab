"""
domain/intelligence/simulation/runner.py

High-performance batch evaluator for running simulation experiments.

ARCHITECTURAL PRINCIPLES (Block 3, Step 10 & 16):
- Fast local analytical evaluation (10,000+ scenarios in < 2 seconds).
- Compares:
  1. No-Intervention Baseline (Always WAIT)
  2. Deterministic Heuristic Baseline
  3. Ground-Truth Oracle
- Computes comprehensive comparative financial and operational metrics.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.interfaces import RecoveryDecisionProvider
from domain.intelligence.models.action_economics import (
    ActionEvaluation,
    RecoveryDecisionRecommendation,
)
from domain.intelligence.oracle import SimulationOracleDecisionProvider
from domain.intelligence.simulation.counterfactual import (
    CounterfactualOutcomeSimulator,
    RealizedCounterfactualOutcome,
)
from domain.intelligence.simulation.generator import (
    SyntheticScenario,
    SyntheticScenarioGenerator,
)
from domain.shared.enums import RecoveryActionType


@dataclass(frozen=True)
class PolicyProviderSummary:
    """Aggregated performance metrics for a specific decision strategy over a batch."""

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


@dataclass(frozen=True)
class SimulationBatchResult:
    """Complete results of an analytical simulation run across multiple strategies."""

    run_id: uuid.UUID
    run_name: str
    scenario_count: int
    seed: int
    version: str
    duration_ms: float
    no_intervention_metrics: PolicyProviderSummary
    baseline_metrics: PolicyProviderSummary
    oracle_metrics: PolicyProviderSummary
    completed_at: datetime


class AlwaysWaitDecisionProvider(RecoveryDecisionProvider):
    """Reference provider that strictly chooses WAIT (0 interventions)."""

    @property
    def provider_name(self) -> str:
        return "AlwaysWait"

    def evaluate_decision(
        self,
        context: Any,
        scenario_id: Optional[str] = None,
    ) -> RecoveryDecisionRecommendation:
        from domain.intelligence.economic_engine import evaluate_all_candidate_actions

        recommendation = evaluate_all_candidate_actions(
            context=context,
            candidate_economics={},
            natural_recovery_probability=0.20,
            scenario_id=scenario_id,
        )
        return recommendation


class ScenarioBatchRunner:
    """
    Executes and aggregates comparative simulation runs.
    """

    def __init__(self, seed: int = 42, version: str = "v1.0"):
        self.seed = seed
        self.version = version

    def run_benchmark(
        self,
        scenario_count: int = 10_000,
        run_name: str = "benchmark_run",
    ) -> SimulationBatchResult:
        """
        Run high-performance comparative evaluation over synthetic scenarios.
        """
        start_time = time.perf_counter()
        run_id = uuid.uuid4()

        generator = SyntheticScenarioGenerator(seed=self.seed, version=self.version)
        scenarios = generator.generate_batch(scenario_count)

        # Setup providers
        baseline_provider = DeterministicBaselineDecisionProvider()
        oracle_provider = SimulationOracleDecisionProvider()
        wait_provider = AlwaysWaitDecisionProvider()

        # Outcome simulators (using synchronized seed for fair counterfactual realization)
        sim_wait = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_baseline = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_oracle = CounterfactualOutcomeSimulator(seed=self.seed)

        wait_decisions: list[tuple[RecoveryDecisionRecommendation, RealizedCounterfactualOutcome]] = []
        base_decisions: list[tuple[RecoveryDecisionRecommendation, RealizedCounterfactualOutcome]] = []
        oracle_decisions: list[tuple[RecoveryDecisionRecommendation, RealizedCounterfactualOutcome]] = []

        for scn in scenarios:
            # 1. Always Wait
            dec_wait = wait_provider.evaluate_decision(scn.context, scn.scenario_id)
            out_wait = sim_wait.simulate_outcome(scn, dec_wait)
            wait_decisions.append((dec_wait, out_wait))

            # 2. Deterministic Baseline
            dec_base = baseline_provider.evaluate_decision(scn.context, scn.scenario_id)
            out_base = sim_baseline.simulate_outcome(scn, dec_base)
            base_decisions.append((dec_base, out_base))

            # 3. Simulation Oracle
            dec_oracle = oracle_provider.evaluate_decision_with_ground_truth(
                context=scn.context,
                candidate_economics=scn.ground_truth_candidate_economics,
                natural_recovery_probability=scn.ground_truth_natural_recovery_prob,
                scenario_id=scn.scenario_id,
            )
            out_oracle = sim_oracle.simulate_outcome(scn, dec_oracle)
            oracle_decisions.append((dec_oracle, out_oracle))

        wait_summary = self._aggregate_summary(wait_provider.provider_name, scenarios, wait_decisions)
        base_summary = self._aggregate_summary(baseline_provider.provider_name, scenarios, base_decisions)
        oracle_summary = self._aggregate_summary(oracle_provider.provider_name, scenarios, oracle_decisions)

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return SimulationBatchResult(
            run_id=run_id,
            run_name=run_name,
            scenario_count=scenario_count,
            seed=self.seed,
            version=self.version,
            duration_ms=duration_ms,
            no_intervention_metrics=wait_summary,
            baseline_metrics=base_summary,
            oracle_metrics=oracle_summary,
            completed_at=datetime.now(tz=timezone.utc),
        )

    def _aggregate_summary(
        self,
        provider_name: str,
        scenarios: list[SyntheticScenario],
        decisions: list[tuple[RecoveryDecisionRecommendation, RealizedCounterfactualOutcome]],
    ) -> PolicyProviderSummary:
        count = len(scenarios)
        total_amount = sum(s.context.amount_minor for s in scenarios)

        exp_gross = sum(d.get_evaluation(d.recommended_action).expected_gross_revenue_minor if d.get_evaluation(d.recommended_action) else 0 for d, _ in decisions)
        exp_natural = sum(d.get_evaluation(d.recommended_action).expected_natural_revenue_minor if d.get_evaluation(d.recommended_action) else 0 for d, _ in decisions)
        exp_incremental = sum(d.get_evaluation(d.recommended_action).expected_incremental_revenue_minor if d.get_evaluation(d.recommended_action) else 0 for d, _ in decisions)
        exp_net = sum(d.expected_net_incremental_revenue_minor for d, _ in decisions)

        rel_gross = sum(o.realized_gross_revenue_minor for _, o in decisions)
        rel_natural = sum(o.realized_natural_revenue_minor for _, o in decisions)
        rel_incremental = sum(o.realized_incremental_revenue_minor for _, o in decisions)
        rel_net = sum(o.realized_net_incremental_revenue_minor for _, o in decisions)

        interventions = sum(1 for d, _ in decisions if d.recommended_action != RecoveryActionType.WAIT)
        unnecessary = sum(1 for _, o in decisions if o.is_unnecessary_intervention)
        missed = sum(1 for _, o in decisions if o.is_missed_opportunity)
        policy_overrides = sum(1 for d, _ in decisions if d.is_policy_override)

        action_dist: dict[str, int] = {}
        for d, _ in decisions:
            act_name = d.recommended_action.value
            action_dist[act_name] = action_dist.get(act_name, 0) + 1

        return PolicyProviderSummary(
            provider_name=provider_name,
            scenario_count=count,
            total_amount_at_risk_minor=total_amount,
            expected_gross_revenue_minor=exp_gross,
            expected_natural_revenue_minor=exp_natural,
            expected_incremental_revenue_minor=exp_incremental,
            expected_net_incremental_revenue_minor=exp_net,
            realized_gross_revenue_minor=rel_gross,
            realized_natural_revenue_minor=rel_natural,
            realized_incremental_revenue_minor=rel_incremental,
            realized_net_incremental_revenue_minor=rel_net,
            total_interventions=interventions,
            intervention_rate=round(interventions / count, 4) if count else 0.0,
            unnecessary_interventions=unnecessary,
            unnecessary_intervention_rate=round(unnecessary / count, 4) if count else 0.0,
            missed_opportunities=missed,
            missed_opportunity_rate=round(missed / count, 4) if count else 0.0,
            policy_overrides_count=policy_overrides,
            action_distribution=action_dist,
        )
