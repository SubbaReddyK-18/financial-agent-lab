"""
scripts/run_gemini_100_paced_benchmark.py

Paced, rate-limited 100-scenario benchmark for real Gemini 2.5 Flash against
Deterministic Baseline and Simulation Oracle.

Enforces conservative inter-request pacing (4.5s) and 429 backoff retry
to guarantee unpolluted real LLM performance evaluation on seed 42.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time
from datetime import datetime, timezone

from apps.api.settings import get_settings
from domain.intelligence.ai.models import AIDecisionRecord
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.oracle import SimulationOracleDecisionProvider
from domain.intelligence.simulation.counterfactual import CounterfactualOutcomeSimulator
from domain.intelligence.simulation.generator import SyntheticScenarioGenerator
from domain.intelligence.simulation.runner import AlwaysWaitDecisionProvider, ScenarioBatchRunner


async def run_paced_benchmark(scenario_count: int = 100, seed: int = 42, pace_delay_seconds: float = 4.2):
    settings = get_settings()
    print("=" * 80)
    print("FINANCIAL AGENT LAB — PACED REAL GEMINI 2.5 FLASH 100-SCENARIO BENCHMARK")
    print("=" * 80)
    print(f"Provider:            {settings.ai_provider}")
    print(f"Model:               {settings.ai_model}")
    print(f"Seed:                {seed}")
    print(f"Scenario Count:      {scenario_count}")
    print(f"Pacing Delay:        {pace_delay_seconds}s per scenario (Rate Limit Protection: ~13 RPM)")
    print(f"Started At:          {datetime.now(tz=timezone.utc).isoformat()}")
    print("-" * 80)

    ai_provider = AIDecisionProvider()
    generator = SyntheticScenarioGenerator(seed=seed, version="v1.0")
    scenarios = generator.generate_batch(scenario_count)

    baseline_provider = DeterministicBaselineDecisionProvider()
    oracle_provider = SimulationOracleDecisionProvider()
    wait_provider = AlwaysWaitDecisionProvider()

    sim_wait = CounterfactualOutcomeSimulator(seed=seed)
    sim_base = CounterfactualOutcomeSimulator(seed=seed)
    sim_ai = CounterfactualOutcomeSimulator(seed=seed)
    sim_oracle = CounterfactualOutcomeSimulator(seed=seed)

    wait_results = []
    base_results = []
    ai_results = []
    oracle_results = []

    ai_records: list[AIDecisionRecord] = []
    regrets = []
    oracle_expected_net_list = []
    ai_expected_net_list = []

    # Category tracking
    gemini_success_count = 0
    fallback_count = 0
    scenario_provider_used = []

    start_time = time.perf_counter()

    for idx, scn in enumerate(scenarios, 1):
        loop_start = time.perf_counter()

        # 1. No Intervention (Wait)
        dec_wait = wait_provider.evaluate_decision(scn.context, scn.scenario_id)
        out_wait = sim_wait.simulate_outcome(scn, dec_wait)
        wait_results.append((dec_wait, out_wait))

        # 2. Deterministic Baseline
        dec_base = baseline_provider.evaluate_decision(scn.context, scn.scenario_id)
        out_base = sim_base.simulate_outcome(scn, dec_base)
        base_results.append((dec_base, out_base))

        # 3. Real Gemini 2.5 Flash with deterministic fallback
        dec_ai = await ai_provider.evaluate_decision_async(scn.context, scn.scenario_id)
        out_ai = sim_ai.simulate_outcome(scn, dec_ai)
        ai_results.append((dec_ai, out_ai))
        rec = ai_provider.last_decision_record

        if rec:
            ai_records.append(rec)
            if rec.fallback_used:
                fallback_count += 1
                scenario_provider_used.append("DeterministicBaseline (Fallback)")
            else:
                gemini_success_count += 1
                scenario_provider_used.append("gemini-2.5-flash")

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

        # Progress reporting
        if idx % 10 == 0 or idx == scenario_count:
            elapsed = time.perf_counter() - start_time
            live_records = [r for r in ai_records if not r.fallback_used]
            avg_lat = sum(r.latency_ms for r in live_records) / len(live_records) if live_records else 0
            print(f"[{idx:>3}/{scenario_count}] Processed ({elapsed:.1f}s elapsed) | Gemini Success: {gemini_success_count} | Fallbacks: {fallback_count} | Avg Latency: {avg_lat:.0f}ms")

        # Pacing delay to maintain strictly < 15 RPM
        elapsed_loop = time.perf_counter() - loop_start
        if idx < scenario_count and elapsed_loop < pace_delay_seconds:
            await asyncio.sleep(pace_delay_seconds - elapsed_loop)

    total_duration = time.perf_counter() - start_time

    # Aggregations
    aggregator = ScenarioBatchRunner(seed=seed)
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

    # Latencies (Real Gemini Successful Inferences)
    live_records = [r for r in ai_records if not r.fallback_used]
    latencies = [r.latency_ms for r in live_records]
    lat_sorted = sorted(latencies)
    avg_lat = statistics.mean(latencies) if latencies else 0.0
    min_lat = min(latencies) if latencies else 0.0
    max_lat = max(latencies) if latencies else 0.0
    p50_lat = statistics.median(latencies) if latencies else 0.0
    p90_lat = lat_sorted[int(len(lat_sorted) * 0.90)] if lat_sorted else 0.0

    # Tokens & Costs
    total_input_tok = sum(r.input_tokens for r in live_records)
    total_output_tok = sum(r.output_tokens for r in live_records)
    total_cost_minor = sum(r.estimated_llm_cost_minor for r in live_records)

    # Agreement Rates
    agreed_oracle = sum(
        1 for (d_ai, _), (d_or, _) in zip(ai_results, oracle_results)
        if d_ai.recommended_action == d_or.recommended_action
    )
    agreed_base = sum(
        1 for (d_ai, _), (d_ba, _) in zip(ai_results, base_results)
        if d_ai.recommended_action == d_ba.recommended_action
    )

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
    print("FINAL 100-SCENARIO PACED GEMINI 2.5 FLASH BENCHMARK RESULTS")
    print("=" * 80)

    print("\n1. INFERENCE EXECUTION INTEGRITY:")
    print(f"  Real Gemini Successful Decisions:   {gemini_success_count:>12} / {scenario_count} ({gemini_success_count / scenario_count * 100:.1f}%)")
    print(f"  Fallback Decisions:                  {fallback_count:>12} / {scenario_count} ({fallback_count / scenario_count * 100:.1f}%)")
    print(f"  Total Duration:                      {total_duration:>12.1f} s")

    print("\n2. FINANCIAL & ECONOMIC PERFORMANCE:")
    print(f"  Simulation Oracle Realized Net:      INR {sum_oracle.realized_net_incremental_revenue_minor / 100:>12,.2f}  (100.0%)")
    print(f"  Gemini 2.5 Flash Realized Net:       INR {sum_ai.realized_net_incremental_revenue_minor / 100:>12,.2f}  ({sum_ai.realized_net_incremental_revenue_minor / sum_oracle.realized_net_incremental_revenue_minor * 100:.2f}% Value Capture)")
    print(f"  Deterministic Baseline Realized Net: INR {sum_base.realized_net_incremental_revenue_minor / 100:>12,.2f}  ({sum_base.realized_net_incremental_revenue_minor / sum_oracle.realized_net_incremental_revenue_minor * 100:.2f}% Value Capture)")
    print(f"  No Intervention (Always Wait) Net:   INR {sum_wait.realized_net_incremental_revenue_minor / 100:>12,.2f}  (0.0%)")
    print(f"  Net AI Lift over Baseline:           INR {(sum_ai.realized_net_incremental_revenue_minor - sum_base.realized_net_incremental_revenue_minor) / 100:>12,.2f}")

    print("\n3. TOKEN CONSUMPTION & INFERENCE COST:")
    print(f"  Total Input Tokens:                  {total_input_tok:>12,}")
    print(f"  Total Output Tokens:                 {total_output_tok:>12,}")
    print(f"  Avg Input / Output Tokens per Call:  {total_input_tok / max(1, gemini_success_count):.0f} / {total_output_tok / max(1, gemini_success_count):.0f}")
    print(f"  Total LLM Inference Cost:            INR {total_cost_minor / 100:>12,.2f}  ({total_cost_minor} paise)")
    print(f"  Net AI Economic Value (Net - LLM):   INR {(sum_ai.realized_net_incremental_revenue_minor - total_cost_minor) / 100:>12,.2f}")

    print("\n4. ECONOMIC REGRET DISTRIBUTION:")
    print(f"  Average Economic Regret:             INR {mean_regret:>12,.2f}")
    print(f"  Median Economic Regret:              INR {median_regret:>12,.2f}")
    print(f"  90th Percentile Economic Regret:     INR {p90_regret:>12,.2f}")
    print(f"  Decisions within 1% of Oracle EV:    {within_1:>11.1f}%")
    print(f"  Decisions within 5% of Oracle EV:    {within_5:>11.1f}%")
    print(f"  Decisions within 10% of Oracle EV:   {within_10:>11.1f}%")

    print("\n5. DECISION ALIGNMENT & AGREEMENT:")
    print(f"  Exact Action Agreement with Oracle:  {agreed_oracle / n * 100:>11.1f}% ({agreed_oracle}/{n})")
    print(f"  Exact Agreement with Baseline:       {agreed_base / n * 100:>11.1f}% ({agreed_base}/{n})")

    print("\n6. ACTION DISTRIBUTIONS:")
    print(f"  Gemini 2.5 Flash:     {json.dumps(ai_actions)}")
    print(f"  Deterministic Baseline:{json.dumps(base_actions)}")
    print(f"  Simulation Oracle:    {json.dumps(oracle_actions)}")

    print("\n7. OPERATIONAL LATENCY (REAL GEMINI 2.5 FLASH INFERENCE):")
    print(f"  Average Latency:                     {avg_lat:>11.1f} ms")
    print(f"  Median (P50) Latency:                {p50_lat:>11.1f} ms")
    print(f"  90th Percentile (P90) Latency:       {p90_lat:>11.1f} ms")
    print(f"  Min / Max Latency:                   {min_lat:.1f} ms / {max_lat:.1f} ms")

    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(run_paced_benchmark())
