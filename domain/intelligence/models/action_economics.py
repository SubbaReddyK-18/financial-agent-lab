"""
domain/intelligence/models/action_economics.py

Economic evaluation models for recovery candidate actions.

ARCHITECTURAL PRINCIPLES (P-01, P-03, Block 3, Step 4 & 5):
- Explicitly separates Gross Recovery, Natural Recovery, Incremental Recovery, and Net Incremental Revenue.
- All monetary fields use integer minor units (paise). Floats are strictly limited to probabilities.
- Separates unconstrained economic optimality from merchant policy compliance.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.intelligence.models.context import RecoveryContext
from domain.shared.enums import RecoveryActionType


@dataclass(frozen=True)
class ActionEconomicParameters:
    """
    Operational and economic assumptions for a specific recovery action candidate.

    Attributes:
        action_type: Type of action (WAIT, RETRY, PAYMENT_LINK, NOTIFY, ESCALATE).
        intervention_cost_minor: Direct operational/communication cost in minor units (paise).
        estimated_success_probability: Model/Simulation estimate of success if this action is executed.
        discount_percent_offered: Discount percentage offered (0 to 100).
    """

    action_type: RecoveryActionType
    intervention_cost_minor: int
    estimated_success_probability: float
    discount_percent_offered: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.intervention_cost_minor, int):
            raise TypeError("intervention_cost_minor must be an integer (FS-01).")
        if self.intervention_cost_minor < 0:
            raise ValueError("intervention_cost_minor cannot be negative.")
        if not (0.0 <= self.estimated_success_probability <= 1.0):
            raise ValueError(
                f"estimated_success_probability must be between 0.0 and 1.0, got {self.estimated_success_probability}"
            )
        if not (0 <= self.discount_percent_offered <= 100):
            raise ValueError("discount_percent_offered must be between 0 and 100.")


@dataclass(frozen=True)
class ActionEvaluation:
    """
    Detailed economic and policy evaluation for a single candidate action.

    Formula Definitions:
    - Expected Gross Revenue = Amount * P(Action Recovery) * (1 - Discount)
    - Expected Natural Revenue = Amount * P(Natural Recovery)
    - Expected Incremental Revenue = Expected Gross Revenue - Expected Natural Revenue
    - Expected Net Incremental Revenue = Expected Incremental Revenue - Intervention Cost
    """

    action_type: RecoveryActionType
    estimated_success_probability: float
    natural_recovery_probability: float
    incremental_recovery_probability: float
    expected_gross_revenue_minor: int
    expected_natural_revenue_minor: int
    expected_incremental_revenue_minor: int
    intervention_cost_minor: int
    expected_net_incremental_revenue_minor: int
    is_policy_compliant: bool
    policy_violations: list[str] = field(default_factory=list)
    requires_human_approval: bool = False
    discount_percent_offered: int = 0

    @property
    def is_economically_positive(self) -> bool:
        """True if the action creates positive net incremental value over doing nothing."""
        return self.expected_net_incremental_revenue_minor > 0


@dataclass(frozen=True)
class RecoveryDecisionRecommendation:
    """
    Authoritative decision recommendation produced by the Economic Engine / Decision Provider.
    """

    decision_id: uuid.UUID
    scenario_id: Optional[str]
    context: RecoveryContext
    candidate_evaluations: list[ActionEvaluation]
    economically_optimal_action: RecoveryActionType
    economically_optimal_net_revenue_minor: int
    policy_permitted_action: RecoveryActionType
    policy_permitted_net_revenue_minor: int
    recommended_action: RecoveryActionType
    recommended_discount_percent: int
    expected_net_incremental_revenue_minor: int
    is_policy_override: bool
    evaluation_timestamp: datetime

    def get_evaluation(self, action_type: RecoveryActionType) -> Optional[ActionEvaluation]:
        for ev in self.candidate_evaluations:
            if ev.action_type == action_type:
                return ev
        return None
