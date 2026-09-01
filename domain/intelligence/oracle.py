"""
domain/intelligence/oracle.py

Simulation Oracle decision provider.

ARCHITECTURAL PRINCIPLE (Block 3, Step 8 & 9):
The Oracle possesses full access to the synthetic ground-truth parameters of the simulation.
It identifies the action that maximizes expected net incremental revenue within the synthetic laboratory.
"""

from __future__ import annotations

from typing import Mapping, Optional

from domain.intelligence.economic_engine import evaluate_all_candidate_actions
from domain.intelligence.interfaces import RecoveryDecisionProvider
from domain.intelligence.models.action_economics import (
    ActionEconomicParameters,
    RecoveryDecisionRecommendation,
)
from domain.intelligence.models.context import RecoveryContext
from domain.shared.enums import RecoveryActionType


class SimulationOracleDecisionProvider(RecoveryDecisionProvider):
    """
    Ground-truth optimizer using full simulation parameter visibility.
    """

    @property
    def provider_name(self) -> str:
        return "SimulationOracle"

    def evaluate_decision_with_ground_truth(
        self,
        context: RecoveryContext,
        candidate_economics: Mapping[RecoveryActionType, ActionEconomicParameters],
        natural_recovery_probability: float,
        scenario_id: Optional[str] = None,
    ) -> RecoveryDecisionRecommendation:
        """
        Evaluate candidate actions against exact ground-truth scenario parameters.
        """
        return evaluate_all_candidate_actions(
            context=context,
            candidate_economics=candidate_economics,
            natural_recovery_probability=natural_recovery_probability,
            scenario_id=scenario_id,
        )

    def evaluate_decision(
        self,
        context: RecoveryContext,
        scenario_id: Optional[str] = None,
    ) -> RecoveryDecisionRecommendation:
        """
        Fallback evaluation using standardized laboratory ground truth assumptions.
        """
        # Standardized lab parameters
        candidate_economics = {
            RecoveryActionType.WAIT: ActionEconomicParameters(
                action_type=RecoveryActionType.WAIT,
                intervention_cost_minor=0,
                estimated_success_probability=0.25,
            ),
            RecoveryActionType.RETRY: ActionEconomicParameters(
                action_type=RecoveryActionType.RETRY,
                intervention_cost_minor=20,
                estimated_success_probability=0.60,
            ),
            RecoveryActionType.PAYMENT_LINK: ActionEconomicParameters(
                action_type=RecoveryActionType.PAYMENT_LINK,
                intervention_cost_minor=50,
                estimated_success_probability=0.50,
            ),
            RecoveryActionType.NOTIFY: ActionEconomicParameters(
                action_type=RecoveryActionType.NOTIFY,
                intervention_cost_minor=15,
                estimated_success_probability=0.40,
            ),
            RecoveryActionType.ESCALATE: ActionEconomicParameters(
                action_type=RecoveryActionType.ESCALATE,
                intervention_cost_minor=500,
                estimated_success_probability=0.75,
            ),
        }
        return self.evaluate_decision_with_ground_truth(
            context=context,
            candidate_economics=candidate_economics,
            natural_recovery_probability=0.25,
            scenario_id=scenario_id,
        )
