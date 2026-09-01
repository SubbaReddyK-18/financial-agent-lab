"""
domain/observability/simulation_evaluator.py

Simulation-only offline evaluator computing Economic Regret, Value Capture,
Action Agreement, and Probability Calibration metrics.

CRITICAL ARCHITECTURAL BOUNDARY (Block 3 & Block 6, Requirement 4):
- Simulator hidden ground truth is strictly quarantined in this offline module.
- It NEVER enters RecoveryContext, AIRecoveryContext, production prompts, or database records.
- All evaluation outputs are labeled source_type = "SYNTHETIC_SIMULATION".
"""

from __future__ import annotations

import math
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.oracle import SimulationOracleDecisionProvider
from domain.intelligence.simulation.counterfactual import (
    CounterfactualOutcomeSimulator,
    RealizedCounterfactualOutcome,
)
from domain.intelligence.simulation.generator import (
    SyntheticScenario,
    SyntheticScenarioGenerator,
)
from domain.intelligence.simulation.runner import (
    AlwaysWaitDecisionProvider,
    PolicyProviderSummary,
)
from domain.observability.metrics import compute_percentile
from domain.shared.enums import RecoveryActionType


@dataclass(frozen=True)
class CalibrationBucket:
    """A probability calibration bin with predicted vs observed frequencies."""

    bucket_range: str  # e.g. "0.00-0.20"
    count: int
    mean_predicted_prob: float
    observed_positive_rate: float


@dataclass(frozen=True)
class CalibrationReport:
    """Probability calibration and reliability assessment against hidden ground truth."""

    natural_recovery_prob_mae: float
    action_recovery_prob_mae: float
    brier_score: float
    buckets: list[CalibrationBucket] = field(default_factory=list)


@dataclass(frozen=True)
class RegretSummary:
    """Distribution of economic regret (Oracle Net - AI Net) across synthetic scenarios."""

    mean_regret_minor: int
    median_regret_minor: int
    p90_regret_minor: int
    within_1_pct_rate: float
    within_5_pct_rate: float
    within_10_pct_rate: float


@dataclass(frozen=True)
class SimulationEvaluationReport:
    """Full offline evaluation comparing AI, Baseline, and Oracle."""

    run_id: uuid.UUID
    scenario_count: int
    seed: int
    duration_ms: float

    # Provider Performance Summaries
    no_intervention_metrics: PolicyProviderSummary
    baseline_metrics: PolicyProviderSummary
    ai_metrics: PolicyProviderSummary
    oracle_metrics: PolicyProviderSummary

    # Economic Comparison
    economic_value_capture_ratio: float  # AI Net / Oracle Net
    baseline_value_capture_ratio: float  # Baseline Net / Oracle Net
    net_economic_lift_over_baseline_minor: int  # in paise
    regret: RegretSummary

    # Action Agreement vs Economic Quality Separation
    exact_oracle_action_agreement_rate: float
    exact_baseline_action_agreement_rate: float

    # Operational Telemetry
    fallback_count: int
    fallback_rate: float
    policy_rejection_count: int
    policy_rejection_rate: float
    average_ai_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int
    total_llm_inference_cost_minor: int

    # Probability Calibration
    calibration: CalibrationReport
    source_type: str = "SYNTHETIC_SIMULATION"
    disclaimer: str = (
        "OFFLINE SYNTHETIC EVALUATION ONLY. Simulation Oracle reflects synthetic "
        "probabilistic assumptions and must not be construed as real customer behavior."
    )
    completed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))


class AdvancedSimulationEvaluator:
    """
    Executes offline comparative benchmarks and computes fine-grained calibration metrics.
    """

    def __init__(self, seed: int = 42, version: str = "v1.0"):
        self.seed = seed
        self.version = version

    async def evaluate_async(
        self,
        ai_provider: AIDecisionProvider,
        scenario_count: int = 100,
    ) -> SimulationEvaluationReport:
        """Run full evaluation suite on synthetic scenarios."""
        start_time = time.perf_counter()
        run_id = uuid.uuid4()

        generator = SyntheticScenarioGenerator(seed=self.seed, version=self.version)
        scenarios: list[SyntheticScenario] = generator.generate_batch(scenario_count)

        baseline_provider = DeterministicBaselineDecisionProvider()
        oracle_provider = SimulationOracleDecisionProvider()
        wait_provider = AlwaysWaitDecisionProvider()

        # Synchronized simulators for identical counterfactual outcomes
        sim_wait = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_base = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_ai = CounterfactualOutcomeSimulator(seed=self.seed)
        sim_oracle = CounterfactualOutcomeSimulator(seed=self.seed)

        wait_results = []
        base_results = []
        ai_results = []
        oracle_results = []

        oracle_agreements = 0
        baseline_agreements = 0
        regrets_minor: list[int] = []
        within_1_pct = 0
        within_5_pct = 0
        within_10_pct = 0

        # Calibration tracking
        natural_prob_diffs: list[float] = []
        action_prob_diffs: list[float] = []
        brier_diffs: list[float] = []
        pred_probabilities: list[float] = []
        observed_outcomes: list[int] = []

        fallbacks = 0
        policy_rejections = 0
        total_in_tokens = 0
        total_out_tokens = 0
        total_llm_cost_minor = 0
        latencies_ms: list[float] = []

        for scenario in scenarios:
            # 1. Evaluate decisions across providers
            rec_wait = wait_provider.evaluate_decision(scenario.context, scenario.scenario_id)
            rec_base = baseline_provider.evaluate_decision(scenario.context, scenario.scenario_id)
            rec_oracle = oracle_provider.evaluate_decision_with_ground_truth(
                context=scenario.context,
                candidate_economics=scenario.ground_truth_candidate_economics,
                natural_recovery_probability=scenario.ground_truth_natural_recovery_prob,
                scenario_id=scenario.scenario_id,
            )
            rec_ai = await ai_provider.evaluate_decision_async(
                context=scenario.context,
                scenario_id=scenario.scenario_id,
            )

            # 2. Track AI operational telemetry
            audit = ai_provider.last_decision_record
            if audit:
                latencies_ms.append(audit.latency_ms)
                total_in_tokens += audit.input_tokens
                total_out_tokens += audit.output_tokens
                total_llm_cost_minor += audit.estimated_llm_cost_minor
                if audit.fallback_used:
                    fallbacks += 1
                    if "policy" in str(audit.fallback_reason).lower():
                        policy_rejections += 1

            # 3. Simulate counterfactual outcomes
            out_wait = sim_wait.simulate_outcome(scenario, rec_wait)
            out_base = sim_base.simulate_outcome(scenario, rec_base)
            out_oracle = sim_oracle.simulate_outcome(scenario, rec_oracle)
            out_ai = sim_ai.simulate_outcome(scenario, rec_ai)

            wait_results.append((rec_wait, out_wait))
            base_results.append((rec_base, out_base))
            oracle_results.append((rec_oracle, out_oracle))
            ai_results.append((rec_ai, out_ai))

            # 4. Regret & Agreement
            if rec_ai.recommended_action == rec_oracle.recommended_action:
                oracle_agreements += 1
            if rec_ai.recommended_action == rec_base.recommended_action:
                baseline_agreements += 1

            # Expected Net Regret (in minor units)
            oracle_net = rec_oracle.expected_net_incremental_revenue_minor
            ai_net = rec_ai.expected_net_incremental_revenue_minor
            regret = max(0, oracle_net - ai_net)
            regrets_minor.append(regret)

            # Near-optimality checks
            if oracle_net > 0:
                rel_diff = (oracle_net - ai_net) / oracle_net
                if rel_diff <= 0.01:
                    within_1_pct += 1
                if rel_diff <= 0.05:
                    within_5_pct += 1
                if rel_diff <= 0.10:
                    within_10_pct += 1
            else:
                if regret == 0:
                    within_1_pct += 1
                    within_5_pct += 1
                    within_10_pct += 1

            # 5. Probability Calibration tracking (against ground truth)
            true_nat_p = scenario.ground_truth_natural_recovery_prob
            ev = rec_ai.get_evaluation(rec_ai.recommended_action)
            pred_nat_p = ev.natural_recovery_probability if ev else 0.25
            natural_prob_diffs.append(abs(pred_nat_p - true_nat_p))

            cand_econ = scenario.ground_truth_candidate_economics.get(rec_ai.recommended_action)
            true_act_p = cand_econ.estimated_success_probability if cand_econ else true_nat_p
            pred_act_p = ev.estimated_success_probability if ev else 0.50
            action_prob_diffs.append(abs(pred_act_p - true_act_p))

            # Brier Score tracking against actual realized outcome
            outcome_val = 1 if out_ai.action_recovery_occurred else 0
            brier_diffs.append((pred_act_p - outcome_val) ** 2)
            pred_probabilities.append(pred_act_p)
            observed_outcomes.append(outcome_val)

        # 6. Aggregate Summaries using ScenarioBatchRunner
        from domain.intelligence.simulation.runner import ScenarioBatchRunner
        aggregator = ScenarioBatchRunner(seed=self.seed)
        summary_wait = aggregator._aggregate_summary("AlwaysWait", scenarios, wait_results)
        summary_base = aggregator._aggregate_summary("DeterministicBaseline", scenarios, base_results)
        summary_ai = aggregator._aggregate_summary("AIDecisionProvider", scenarios, ai_results)
        summary_oracle = aggregator._aggregate_summary("SimulationOracle", scenarios, oracle_results)

        # Economic Ratios
        oracle_net_total = summary_oracle.realized_net_incremental_revenue_minor
        ai_net_total = summary_ai.realized_net_incremental_revenue_minor
        base_net_total = summary_base.realized_net_incremental_revenue_minor

        ai_capture_ratio = (
            round(ai_net_total / oracle_net_total, 4) if oracle_net_total > 0 else 0.0
        )
        base_capture_ratio = (
            round(base_net_total / oracle_net_total, 4) if oracle_net_total > 0 else 0.0
        )
        net_lift = ai_net_total - base_net_total

        # Regret Metrics
        mean_regret = round(sum(regrets_minor) / len(regrets_minor)) if regrets_minor else 0
        sorted_regrets = sorted(regrets_minor)
        med_regret = sorted_regrets[len(sorted_regrets) // 2] if sorted_regrets else 0
        p90_regret = int(compute_percentile([float(r) for r in regrets_minor], 0.90))

        regret_summary = RegretSummary(
            mean_regret_minor=mean_regret,
            median_regret_minor=med_regret,
            p90_regret_minor=p90_regret,
            within_1_pct_rate=round(within_1_pct / scenario_count, 4),
            within_5_pct_rate=round(within_5_pct / scenario_count, 4),
            within_10_pct_rate=round(within_10_pct / scenario_count, 4),
        )

        # Calibration Buckets (5 bins: 0-0.2, 0.2-0.4, 0.4-0.6, 0.6-0.8, 0.8-1.0)
        bins = [(0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.01)]
        buckets: list[CalibrationBucket] = []
        for low, high in bins:
            bin_preds = [
                p for p, o in zip(pred_probabilities, observed_outcomes)
                if low <= p < high
            ]
            bin_obs = [
                o for p, o in zip(pred_probabilities, observed_outcomes)
                if low <= p < high
            ]
            if bin_preds:
                mean_pred = round(sum(bin_preds) / len(bin_preds), 4)
                obs_rate = round(sum(bin_obs) / len(bin_obs), 4)
            else:
                mean_pred = 0.0
                obs_rate = 0.0
            buckets.append(
                CalibrationBucket(
                    bucket_range=f"{low:.2f}-{min(high, 1.0):.2f}",
                    count=len(bin_preds),
                    mean_predicted_prob=mean_pred,
                    observed_positive_rate=obs_rate,
                )
            )

        calibration_report = CalibrationReport(
            natural_recovery_prob_mae=round(sum(natural_prob_diffs) / len(natural_prob_diffs), 4),
            action_recovery_prob_mae=round(sum(action_prob_diffs) / len(action_prob_diffs), 4),
            brier_score=round(sum(brier_diffs) / len(brier_diffs), 4),
            buckets=buckets,
        )

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        avg_latency = round(sum(latencies_ms) / len(latencies_ms), 2) if latencies_ms else 0.0

        return SimulationEvaluationReport(
            run_id=run_id,
            scenario_count=scenario_count,
            seed=self.seed,
            duration_ms=duration_ms,
            source_type="SYNTHETIC_SIMULATION",
            no_intervention_metrics=summary_wait,
            baseline_metrics=summary_base,
            ai_metrics=summary_ai,
            oracle_metrics=summary_oracle,
            economic_value_capture_ratio=ai_capture_ratio,
            baseline_value_capture_ratio=base_capture_ratio,
            net_economic_lift_over_baseline_minor=net_lift,
            regret=regret_summary,
            exact_oracle_action_agreement_rate=round(oracle_agreements / scenario_count, 4),
            exact_baseline_action_agreement_rate=round(baseline_agreements / scenario_count, 4),
            fallback_count=fallbacks,
            fallback_rate=round(fallbacks / scenario_count, 4),
            policy_rejection_count=policy_rejections,
            policy_rejection_rate=round(policy_rejections / scenario_count, 4),
            average_ai_latency_ms=avg_latency,
            total_input_tokens=total_in_tokens,
            total_output_tokens=total_out_tokens,
            total_llm_inference_cost_minor=total_llm_cost_minor,
            calibration=calibration_report,
        )
