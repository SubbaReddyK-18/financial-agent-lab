"""
scripts/smoke_test_ai.py

Smoke test script to evaluate 5-10 synthetic scenarios against the configured AI provider.

Usage:
  python scripts/smoke_test_ai.py [--scenarios 5] [--seed 42]
"""

import argparse
import asyncio
import time

from apps.api.settings import get_settings
from domain.intelligence.ai.evaluator import AIBenchmarkRunner
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.simulation.generator import SyntheticScenarioGenerator


async def run_smoke_test(scenario_count: int = 5, seed: int = 42) -> None:
    settings = get_settings()
    print("=" * 60)
    print("FINANCIAL AGENT LAB — BLOCK 4 AI SMOKE TEST")
    print("=" * 60)
    print(f"Provider Configured: {settings.ai_provider}")
    print(f"Model:               {settings.ai_model}")
    print(f"Base URL:            {settings.ai_base_url}")
    print(f"API Key Present:     {'YES' if settings.ai_api_key else 'NO (Using Mock/Offline)'}")
    print(f"Scenario Count:      {scenario_count}")
    print(f"Seed:                {seed}")
    print("-" * 60)

    provider = AIDecisionProvider()
    generator = SyntheticScenarioGenerator(seed=seed)
    scenarios = generator.generate_batch(scenario_count)

    print(f"{'#':<3} | {'Failure Code':<22} | {'Amount (INR)':<12} | {'AI Action':<12} | {'Conf':<5} | {'Fallback':<8} | {'Latency':<7}")
    print("-" * 80)

    for i, scn in enumerate(scenarios, 1):
        rec = await provider.evaluate_decision_async(scn.context, scn.scenario_id)
        audit = provider.last_decision_record
        amt_inr = scn.context.amount_minor / 100.0
        code = scn.context.payment.failure_code
        action = rec.recommended_action.value
        conf = f"{audit.confidence:.2f}" if audit else "N/A"
        fallback = "YES" if (audit and audit.fallback_used) else "NO"
        latency = f"{audit.latency_ms:.0f}ms" if audit else "N/A"

        print(f"{i:<3} | {code:<22} | INR {amt_inr:<7,.2f} | {action:<12} | {conf:<5} | {fallback:<8} | {latency:<7}")

    print("=" * 80)
    print("Smoke test completed successfully.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run AI recovery decision smoke test.")
    parser.add_argument("--scenarios", type=int, default=5, help="Number of scenarios to test")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    args = parser.parse_args()

    asyncio.run(run_smoke_test(scenario_count=args.scenarios, seed=args.seed))
