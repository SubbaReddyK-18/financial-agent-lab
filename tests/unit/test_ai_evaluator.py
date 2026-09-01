"""
tests/unit/test_ai_evaluator.py

Unit tests for AIBenchmarkRunner evaluating AI comparative performance.
"""

from domain.intelligence.ai.evaluator import AIBenchmarkRunner
from domain.intelligence.ai.provider import AIDecisionProvider
from infrastructure.ai.client import MockLLMClient


class TestAIEvaluator:
    def test_benchmark_runner_computes_all_comparative_metrics(self):
        client = MockLLMClient()
        provider = AIDecisionProvider(client=client)
        runner = AIBenchmarkRunner(seed=42)

        summary = runner.run_benchmark(ai_provider=provider, scenario_count=30)

        assert summary.scenario_count == 30
        assert summary.ai_oracle_agreement_rate >= 0.0
        assert summary.ai_baseline_agreement_rate >= 0.0
        assert summary.economic_value_capture_ratio >= 0.0
        assert summary.total_input_tokens > 0
        assert summary.total_output_tokens > 0
        assert summary.total_llm_inference_cost_minor >= 0
        assert summary.net_ai_economic_value_minor is not None
