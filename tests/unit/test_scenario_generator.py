"""
tests/unit/test_scenario_generator.py

Unit tests for SyntheticScenarioGenerator.

Validates:
- Seed reproducibility (deterministic output across runs).
- Scenario diversity with varying seeds.
- Valid amount bounds and integer types.
- Correct taxonomy and failure distribution.
"""

from domain.intelligence.simulation.generator import (
    FAILURE_TAXONOMY,
    SyntheticScenarioGenerator,
)


class TestSyntheticScenarioGenerator:
    def test_seed_reproducibility(self):
        gen1 = SyntheticScenarioGenerator(seed=12345)
        batch1 = gen1.generate_batch(50)

        gen2 = SyntheticScenarioGenerator(seed=12345)
        batch2 = gen2.generate_batch(50)

        for s1, s2 in zip(batch1, batch2):
            assert s1.scenario_id == s2.scenario_id
            assert s1.context.amount_minor == s2.context.amount_minor
            assert s1.context.payment.failure_code == s2.context.payment.failure_code
            assert s1.ground_truth_natural_recovery_prob == s2.ground_truth_natural_recovery_prob
            assert s1.failure_category == s2.failure_category

    def test_different_seeds_produce_different_scenarios(self):
        gen1 = SyntheticScenarioGenerator(seed=111)
        gen2 = SyntheticScenarioGenerator(seed=222)

        s1 = gen1.generate_scenario(0)
        s2 = gen2.generate_scenario(0)

        assert s1.scenario_id != s2.scenario_id

    def test_amounts_are_positive_integers(self):
        gen = SyntheticScenarioGenerator(seed=999)
        scenarios = gen.generate_batch(100)

        for s in scenarios:
            assert isinstance(s.context.amount_minor, int)
            assert s.context.amount_minor >= 50_00  # >= ₹50
            assert s.context.amount_minor <= 50000_00  # <= ₹50,000

    def test_failure_taxonomy_coverage(self):
        gen = SyntheticScenarioGenerator(seed=42)
        scenarios = gen.generate_batch(300)

        categories = {s.failure_category for s in scenarios}
        assert "TECHNICAL_TRANSIENT" in categories
        assert "CUSTOMER_ACTIONABLE" in categories
        assert "TERMINAL_BALANCE" in categories
