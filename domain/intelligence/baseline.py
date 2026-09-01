"""
domain/intelligence/baseline.py

Deterministic rule-based baseline decision provider.

ARCHITECTURAL PRINCIPLE (Block 3, Step 7):
Provides a credible, non-AI rule-based benchmark to measure future AI added-value against.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from domain.intelligence.economic_engine import evaluate_all_candidate_actions
from domain.intelligence.interfaces import RecoveryDecisionProvider
from domain.intelligence.models.action_economics import (
    ActionEconomicParameters,
    RecoveryDecisionRecommendation,
)
from domain.intelligence.models.context import RecoveryContext
from domain.shared.enums import PaymentMethod, RecoveryActionType

# Standard retryable technical failure codes
RETRYABLE_FAILURE_CODES = frozenset({
    "GATEWAY_TIMEOUT",
    "NETWORK_ERROR",
    "ISSUER_DOWN",
    "PROCESSING_ERROR",
    "INTERNAL_SYSTEM_ERROR",
    "BANK_UNAVAILABLE",
})

# Customer-actionable failure codes (recoverable via link or notification)
CUSTOMER_ACTIONABLE_CODES = frozenset({
    "MPIN_EXPIRED",
    "OTP_TIMEOUT",
    "AUTHENTICATION_FAILED",
    "CUSTOMER_CANCELLED",
    "USER_DROPPED",
})


class DeterministicBaselineDecisionProvider(RecoveryDecisionProvider):
    """
    Standard rule-based heuristic recovery decision provider.
    """

    @property
    def provider_name(self) -> str:
        return "DeterministicBaseline"

    def _select_heuristic_action(
        self,
        context: RecoveryContext,
    ) -> tuple[RecoveryActionType, int]:
        """
        Determine candidate action and discount using standard fintech recovery heuristics.

        Returns:
            Tuple of (RecoveryActionType, discount_percent).
        """
        code = context.payment.failure_code.upper()
        attempts = context.payment.attempt_count
        max_interventions = context.policy.maximum_interventions
        is_cooldown = context.temporal.is_cooldown_active if context.temporal else False

        # Rule 1: Respect cooldown and intervention limits (fallback to WAIT)
        if is_cooldown or context.completed_interventions >= max_interventions:
            return RecoveryActionType.WAIT, 0

        # Rule 2: High-value payment with high customer history -> NOTIFY or ESCALATE
        if context.is_high_value:
            if context.customer.historical_success_rate >= 0.70:
                return RecoveryActionType.NOTIFY, 0
            return RecoveryActionType.WAIT, 0

        # Rule 3: Retryable technical failure -> RETRY
        if code in RETRYABLE_FAILURE_CODES:
            if attempts <= 2:
                return RecoveryActionType.RETRY, 0
            return RecoveryActionType.WAIT, 0

        # Rule 4: Customer actionable authentication drop -> PAYMENT_LINK with mild discount if VIP
        if code in CUSTOMER_ACTIONABLE_CODES:
            discount = 5 if context.customer.customer_segment == "VIP" and context.policy.maximum_discount_percent >= 5 else 0
            return RecoveryActionType.PAYMENT_LINK, discount

        # Rule 5: Default to WAIT
        return RecoveryActionType.WAIT, 0

    def evaluate_decision(
        self,
        context: RecoveryContext,
        scenario_id: Optional[str] = None,
    ) -> RecoveryDecisionRecommendation:
        """
        Execute deterministic baseline heuristic and wrap into a formal recommendation.
        """
        heuristic_action, discount = self._select_heuristic_action(context)

        # Baseline estimates for candidate actions
        candidate_economics = {
            RecoveryActionType.WAIT: ActionEconomicParameters(
                action_type=RecoveryActionType.WAIT,
                intervention_cost_minor=0,
                estimated_success_probability=0.20,
            ),
            RecoveryActionType.RETRY: ActionEconomicParameters(
                action_type=RecoveryActionType.RETRY,
                intervention_cost_minor=20,  # 20 paise
                estimated_success_probability=0.55,
            ),
            RecoveryActionType.PAYMENT_LINK: ActionEconomicParameters(
                action_type=RecoveryActionType.PAYMENT_LINK,
                intervention_cost_minor=50,  # 50 paise
                estimated_success_probability=0.45,
                discount_percent_offered=discount if heuristic_action == RecoveryActionType.PAYMENT_LINK else 0,
            ),
            RecoveryActionType.NOTIFY: ActionEconomicParameters(
                action_type=RecoveryActionType.NOTIFY,
                intervention_cost_minor=15,  # 15 paise
                estimated_success_probability=0.35,
            ),
            RecoveryActionType.ESCALATE: ActionEconomicParameters(
                action_type=RecoveryActionType.ESCALATE,
                intervention_cost_minor=500,  # ₹5.00
                estimated_success_probability=0.60,
            ),
        }

        # Calculate formal economic evaluations across all candidates
        recommendation = evaluate_all_candidate_actions(
            context=context,
            candidate_economics=candidate_economics,
            natural_recovery_probability=0.20,
            scenario_id=scenario_id,
        )

        # Re-target recommended action to the baseline's chosen heuristic (if policy compliant)
        heuristic_eval = recommendation.get_evaluation(heuristic_action)
        if heuristic_eval and heuristic_eval.is_policy_compliant:
            chosen_action = heuristic_action
            chosen_net = heuristic_eval.expected_net_incremental_revenue_minor
            chosen_discount = heuristic_eval.discount_percent_offered
        else:
            chosen_action = recommendation.policy_permitted_action
            chosen_net = recommendation.policy_permitted_net_revenue_minor
            chosen_discount = recommendation.recommended_discount_percent

        return RecoveryDecisionRecommendation(
            decision_id=recommendation.decision_id,
            scenario_id=scenario_id,
            context=context,
            candidate_evaluations=recommendation.candidate_evaluations,
            economically_optimal_action=recommendation.economically_optimal_action,
            economically_optimal_net_revenue_minor=recommendation.economically_optimal_net_revenue_minor,
            policy_permitted_action=recommendation.policy_permitted_action,
            policy_permitted_net_revenue_minor=recommendation.policy_permitted_net_revenue_minor,
            recommended_action=chosen_action,
            recommended_discount_percent=chosen_discount,
            expected_net_incremental_revenue_minor=chosen_net,
            is_policy_override=(chosen_action != recommendation.economically_optimal_action),
            evaluation_timestamp=recommendation.evaluation_timestamp,
        )
