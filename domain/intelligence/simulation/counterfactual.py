"""
domain/intelligence/simulation/counterfactual.py

Counterfactual outcome simulator for World A (No Intervention) vs. World B (Selected Action).

ARCHITECTURAL PRINCIPLES (Block 3, Step 3 & 5):
- Evaluates realization of both World A and World B for every scenario.
- Calculates exact realized Gross, Natural, Incremental, and Net Incremental Revenue in paise.
- Detects unnecessary interventions and missed recovery opportunities.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Optional

from domain.intelligence.models.action_economics import (
    ActionEconomicParameters,
    ActionEvaluation,
    RecoveryDecisionRecommendation,
)
from domain.intelligence.simulation.generator import SyntheticScenario
from domain.shared.enums import RecoveryActionType


@dataclass(frozen=True)
class RealizedCounterfactualOutcome:
    """
    Realized empirical outcome of a decision executed within the synthetic laboratory.
    """

    scenario_id: str
    action_taken: RecoveryActionType
    discount_percent_offered: int
    intervention_cost_minor: int
    natural_recovery_occurred: bool
    action_recovery_occurred: bool
    realized_gross_revenue_minor: int
    realized_natural_revenue_minor: int
    realized_incremental_revenue_minor: int
    realized_net_incremental_revenue_minor: int
    is_unnecessary_intervention: bool
    is_missed_opportunity: bool


class CounterfactualOutcomeSimulator:
    """
    Simulates realized counterfactuals in World A vs World B.
    """

    def __init__(self, seed: int = 42):
        self._rng = random.Random(seed)

    def reseed(self, seed: int) -> None:
        self._rng = random.Random(seed)

    def simulate_outcome(
        self,
        scenario: SyntheticScenario,
        decision: RecoveryDecisionRecommendation,
    ) -> RealizedCounterfactualOutcome:
        """
        Simulate realized World A and World B for the chosen action in a scenario.
        """
        action = decision.recommended_action
        amount_minor = scenario.context.amount_minor
        params: ActionEconomicParameters = scenario.ground_truth_candidate_economics[action]
        discount_pct = decision.recommended_discount_percent
        cost_minor = params.intervention_cost_minor

        # 1. World A Realization (Natural Recovery)
        p_natural = scenario.ground_truth_natural_recovery_prob
        natural_recovery_occurred = (self._rng.random() < p_natural)

        # 2. World B Realization (Action Recovery)
        if action == RecoveryActionType.WAIT:
            action_recovery_occurred = natural_recovery_occurred
            cost_minor = 0
        else:
            p_action = params.estimated_success_probability
            action_recovery_occurred = (self._rng.random() < p_action)

        # 3. Realized Monetary Amounts in Minor Units (paise)
        if action_recovery_occurred:
            discount_multiplier = 1.0 - (discount_pct / 100.0)
            realized_gross_revenue_minor = int(round(amount_minor * discount_multiplier))
        else:
            realized_gross_revenue_minor = 0

        realized_natural_revenue_minor = amount_minor if natural_recovery_occurred else 0
        realized_incremental_revenue_minor = realized_gross_revenue_minor - realized_natural_revenue_minor
        realized_net_incremental_revenue_minor = realized_incremental_revenue_minor - cost_minor

        # 4. Diagnostic Metrics
        # Unnecessary intervention: Merchant intervened, but customer would have naturally paid anyway
        is_unnecessary_intervention = (
            action != RecoveryActionType.WAIT
            and natural_recovery_occurred
            and action_recovery_occurred
        )

        # Missed opportunity: Merchant chose WAIT, customer failed naturally, but an alternative had positive EV
        is_missed_opportunity = (
            action == RecoveryActionType.WAIT
            and not natural_recovery_occurred
            and decision.economically_optimal_net_revenue_minor > 0
        )

        return RealizedCounterfactualOutcome(
            scenario_id=scenario.scenario_id,
            action_taken=action,
            discount_percent_offered=discount_pct,
            intervention_cost_minor=cost_minor,
            natural_recovery_occurred=natural_recovery_occurred,
            action_recovery_occurred=action_recovery_occurred,
            realized_gross_revenue_minor=realized_gross_revenue_minor,
            realized_natural_revenue_minor=realized_natural_revenue_minor,
            realized_incremental_revenue_minor=realized_incremental_revenue_minor,
            realized_net_incremental_revenue_minor=realized_net_incremental_revenue_minor,
            is_unnecessary_intervention=is_unnecessary_intervention,
            is_missed_opportunity=is_missed_opportunity,
        )
