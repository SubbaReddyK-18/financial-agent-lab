"""
tests/unit/test_counterfactual.py

Unit tests for CounterfactualOutcomeSimulator.
"""

from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.simulation.counterfactual import (
    CounterfactualOutcomeSimulator,
)
from domain.intelligence.simulation.generator import SyntheticScenarioGenerator
from domain.shared.enums import RecoveryActionType


class TestCounterfactualSimulator:
    def test_simulation_reproducibility(self):
        generator = SyntheticScenarioGenerator(seed=777)
        scenario = generator.generate_scenario(0)

        provider = DeterministicBaselineDecisionProvider()
        decision = provider.evaluate_decision(scenario.context)

        sim1 = CounterfactualOutcomeSimulator(seed=100)
        out1 = sim1.simulate_outcome(scenario, decision)

        sim2 = CounterfactualOutcomeSimulator(seed=100)
        out2 = sim2.simulate_outcome(scenario, decision)

        assert out1.natural_recovery_occurred == out2.natural_recovery_occurred
        assert out1.action_recovery_occurred == out2.action_recovery_occurred
        assert out1.realized_net_incremental_revenue_minor == out2.realized_net_incremental_revenue_minor

    def test_wait_action_has_identical_gross_and_natural_realization(self):
        generator = SyntheticScenarioGenerator(seed=888)
        scenario = generator.generate_scenario(0)

        provider = DeterministicBaselineDecisionProvider()
        decision = provider.evaluate_decision(scenario.context)

        sim = CounterfactualOutcomeSimulator(seed=555)
        out = sim.simulate_outcome(scenario, decision)

        if decision.recommended_action == RecoveryActionType.WAIT:
            assert out.action_recovery_occurred == out.natural_recovery_occurred
            assert out.realized_incremental_revenue_minor == 0
            assert out.realized_net_incremental_revenue_minor == 0
            assert out.is_unnecessary_intervention is False
