"""
scripts/run_gemini_100_benchmark.py

Executes the real 100-scenario comparative benchmark for Google Gemini 2.5 Flash
against Deterministic Baseline and Simulation Oracle using AIBenchmarkRunner.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from datetime import datetime, timezone

from apps.api.settings import get_settings
from domain.intelligence.ai.evaluator import AIBenchmarkRunner, AIEvaluationSummary
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.oracle import SimulationOracleDecisionProvider
from domain.intelligence.simulation.counterfactual import CounterfactualOutcomeSimulator
from domain.intelligence.simulation.generator import SyntheticScenarioGenerator
from domain.intelligence.simulation.runner import AlwaysWaitDecisionProvider, ScenarioBatchRunner


async def run_benchmark():
    settings = get_settings()
    print("=" * 80)
    print("FINANCIAL AGENT LAB — REAL GEMINI 2.5 FLASH 100-SCENARIO BENCHMARK")
    print("=" * 80)
    print(f"Provider:        {settings.ai_provider}")
    print(f"Model:           {settings.ai_model}")
    print(f"Base URL:        {settings.ai_base_url}")
    print(f"Seed:            42")
    print(f"Scenario Count:  100")
    print(f"Started At:      {datetime.now(tz=timezone.utc).isoformat()}")
    print("-" * 80)

    ai_provider = AIDecisionProvider()
    generator = SyntheticScenarioGenerator(seed=42, version="v1.0")
    scenarios = generator.generate_batch(100)

    baseline_provider = DeterministicBaselineDecisionProvider()
    oracle_provider = SimulationOracleDecisionProvider()
    wait_provider = AlwaysWaitDecisionProvider()

    sim_wait = CounterfactualOutcomeSimulator(seed=42)
    sim_base = CounterfactualOutcomeSimulator(seed=42)
    sim_ai = CounterfactualOutcomeSimulator(seed=42)
    sim_oracle = CounterfactualOutcomeSimulator(seed=42)

    wait_results = []
    base_results = []
    ai_results = []
    oracle_results = []

    ai_records = []
    regrets = []
    oracle_expected_net_list = []
    ai_expected_net_list = []
    api_errors = []

    start_time = time.perf_counter()

    for idx, scn in enumerate(scenarios, 1):
        # 1. No Intervention (Wait)
        dec_wait = wait_provider.evaluate_decision(scn.context, scn.scenario_id)
        out_wait = sim_wait.simulate_outcome(scn, dec_wait)
        wait_results.append((dec_wait, out_wait))

        # 2. Deterministic Baseline
        dec_base = baseline_provider.evaluate_decision(scn.context, scn.scenario_id)
        out_base = sim_base.simulate_outcome(scn, dec_base)
        base_results.append((dec_base, out_base))

        # 3. Real Gemini 2.5 Flash
        try:
            dec_ai = await ai_provider.evaluate_decision_async(scn.context, scn.scenario_id)
        except Exception as e:
            api_errors.append((scn.scenario_id, str(e)))
            dec_ai = baseline_provider.evaluate_decision(scn.context, scn.scenario_id)

        out_ai = sim_ai.simulate_outcome(scn, dec_ai)
        ai_results.append((dec_ai, out_ai))
        rec = ai_provider.last_decision_record
        if rec:
            ai_records.append(rec)

        # 4. Simulation Oracle (Ground Truth Bound)
        dec_oracle = oracle_provider.evaluate_decision_with_ground_truth(
            context=scn.context,
            candidate_economics=scn.ground_truth_candidate_economics,
            natural_recovery_probability=scn.ground_truth_natural_recovery_prob,
            scenario_id=scn.scenario_id,
        )
        out_oracle = sim_oracle.simulate_outcome(scn, dec_oracle)
        oracle_results.append((dec_oracle, out_oracle))

        # Regret Calculation
        ev_or = dec_oracle.expected_net_incremental_revenue_minor / 100.0
        ev_ai = dec_ai.expected_net_incremental_revenue_minor / 100.0
        regret = max(0.0, ev_or - ev_ai)
        regrets.append(regret)
        oracle_expected_net_list.append(ev_or)
        ai_expected_net_list.append(ev_ai)

        if idx % 10 == 0 or idx == 100:
            elapsed = time.perf_counter() - start_time
            avg_lat = sum(r.latency_ms for r in ai_records) / len(ai_records) if ai_records else 0
            print(f"[{idx:>3}/100] Processed ({elapsed:.1f}s elapsed) | Avg Latency: {avg_lat:.0f}ms | Fallbacks: {sum(1 for r in ai_records if r.fallback_used)}")

    total_duration = time.perf_counter() - start_time

    # Aggregations
    aggregator = ScenarioBatchRunner(seed=42)
    sum_wait = aggregator._aggregate_summary("AlwaysWait", scenarios, wait_results)
    sum_base = aggregator._aggregate_summary("DeterministicBaseline", scenarios, base_results)
    sum_ai = aggregator._aggregate_summary("Gemini2.5Flash", scenarios, ai_results)
    sum_oracle = aggregator._aggregate_summary("SimulationOracle", scenarios, oracle_results)

    # Regret Statistics
    regrets_sorted = sorted(regrets)
    n = len(regrets)
    mean_regret = statistics.mean(regrets)
    median_regret = statistics.median(regrets)
    p90_regret = regrets_sorted[int(n * 0.90)]

    # Proximity to Oracle
    within_1 = sum(1 for ai, o in zip(ai_expected_net_list, oracle_expected_net_list) if o == 0 or (ai / o) >= 0.99) / n * 100
    within_5 = sum(1 for ai, o in zip(ai_expected_net_list, oracle_expected_net_list) if o == 0 or (ai / o) >= 0.95) / n * 100
    within_10 = sum(1 for ai, o in zip(ai_expected_net_list, oracle_expected_net_list) if o == 0 or (ai / o) >= 0.90) / n * 100

    # Latencies
    latencies = [r.latency_ms for r in ai_records]
    lat_sorted = sorted(latencies)
    avg_lat = statistics.mean(latencies) if latencies else 0.0
    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
    p50_lat = statistics.median(latencies) if latencies else 0.0
    p90_lat = lat_sorted[int(len(lat_sorted) * 0.90)] if lat_sorted else 0.0

    # Tokens & Costs
    total_input_tok = sum(r.input_tokens for r in ai_records)
    total_output_tok = sum(r.output_tokens for r in ai_records)
    total_cost_minor = sum(r.estimated_llm_cost_minor for r in ai_records)

    # Agreement Rates
    agreed_oracle = sum(
        1 for (d_ai, _), (d_or, _) in zip(ai_results, oracle_results)
        if d_ai.recommended_action == d_or.recommended_action
    )
    agreed_base = sum(
        1 for (d_ai, _), (d_ba, _) in zip(ai_results, base_results)
        if d_ai.recommended_action == d_ba.recommended_action
    )

    fallbacks = [r for r in ai_records if r.fallback_used]

    # Action Distributions
    ai_actions = {}
    base_actions = {}
    oracle_actions = {}
    for (d, _) in ai_results:
        ai_actions[d.recommended_action.value] = ai_actions.get(d.recommended_action.value, 0) + 1
    for (d, _) in base_results:
        base_actions[d.recommended_action.value] = base_actions.get(d.recommended_action.value, 0) + 1
    for (d, _) in oracle_results:
        oracle_actions[d.recommended_action.value] = oracle_actions.get(d.recommended_action.value, 0) + 1

    print("\n" + "=" * 80)
    print("FINAL 100-SCENARIO GEMINI 2.5 FLASH BENCHMARK RESULTS")
    print("=" * 80)

    print("\n1. FINANCIAL & ECONOMIC PERFORMANCE:")
    print(f"  Simulation Oracle Realized Net:      INR {sum_oracle.realized_net_incremental_revenue_minor / 100:>12,.2f}  (100.0%)")
    print(f"  Gemini 2.5 Flash Realized Net:       INR {sum_ai.realized_net_incremental_revenue_minor / 100:>12,.2f}  ({sum_ai.realized_net_incremental_revenue_minor / sum_oracle.realized_net_incremental_revenue_minor * 100:.2f}% Value Capture)")
    print(f"  Deterministic Baseline Realized Net: INR {sum_base.realized_net_incremental_revenue_minor / 100:>12,.2f}  ({sum_base.realized_net_incremental_revenue_minor / sum_oracle.realized_net_incremental_revenue_minor * 100:.2f}% Value Capture)")
    print(f"  No Intervention (Always Wait) Net:   INR {sum_wait.realized_net_incremental_revenue_minor / 100:>12,.2f}  (0.0%)")
    print(f"  Net AI Lift over Baseline:           INR {(sum_ai.realized_net_incremental_revenue_minor - sum_base.realized_net_incremental_revenue_minor) / 100:>12,.2f}")

    print("\n2. TOKEN CONSUMPTION & INFERENCE COST:")
    print(f"  Total Input Tokens:                  {total_input_tok:>12,}")
    print(f"  Total Output Tokens:                 {total_output_tok:>12,}")
    print(f"  Total LLM Inference Cost:            INR {total_cost_minor / 100:>12,.2f}  ({total_cost_minor} paise)")
    print(f"  Net AI Economic Value (Net - LLM):   INR {(sum_ai.realized_net_incremental_revenue_minor - total_cost_minor) / 100:>12,.2f}")

    print("\n3. ECONOMIC REGRET DISTRIBUTION:")
    print(f"  Average Economic Regret:             INR {mean_regret:>12,.2f}")
    print(f"  Median Economic Regret:              INR {median_regret:>12,.2f}")
    print(f"  90th Percentile Economic Regret:     INR {p90_regret:>12,.2f}")
    print(f"  Decisions within 1% of Oracle EV:    {within_1:>11.1f}%")
    print(f"  Decisions within 5% of Oracle EV:    {within_5:>11.1f}%")
    print(f"  Decisions within 10% of Oracle EV:   {within_10:>11.1f}%")

    print("\n4. DECISION ALIGNMENT & AGREEMENT:")
    print(f"  Exact Action Agreement with Oracle:  {agreed_oracle / n * 100:>11.1f}% ({agreed_oracle}/{n})")
    print(f"  Exact Agreement with Baseline:       {agreed_base / n * 100:>11.1f}% ({agreed_base}/{n})")

    print("\n5. ACTION DISTRIBUTIONS:")
    print(f"  Gemini 2.5 Flash:     {json.dumps(ai_actions)}")
    print(f"  Deterministic Baseline:{json.dumps(base_actions)}")
    print(f"  Simulation Oracle:    {json.dumps(oracle_actions)}")

    print("\n6. OPERATIONAL LATENCY (REAL GEMINI 2.5 FLASH):")
    print(f"  Average Latency:                     {avg_lat:>11.1f} ms")
    print(f"  Median (P50) Latency:                {p50_lat:>11.1f} ms")
    print(f"  90th Percentile (P90) Latency:       {p90_lat:>11.1f} ms")
    print(f"  Min / Max Latency:                   {min_lat:.1f} ms / {max_lat:.1f} ms")
    print(f"  Total Benchmark Execution Time:      {total_duration:>11.1f} s")

    print("\n7. FALLBACK & API HEALTH:")
    print(f"  Total API Errors:                    {len(api_errors)}")
    print(f"  Total Fallback Decisions:            {len(fallbacks)} ({len(fallbacks) / n * 100:.1f}%)")
    if fallbacks:
        for fb in fallbacks[:5]:
            print(f"    - Scenario {fb.scenario_id}: {fb.fallback_reason}")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
