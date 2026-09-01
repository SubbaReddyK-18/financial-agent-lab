"""
domain/intelligence/economic_engine.py

Deterministic economic calculation engine for evaluating recovery actions.

ARCHITECTURAL PRINCIPLES (P-01, P-02, P-03, Block 3, Step 5 & 6):
1. Pure, deterministic economic engine (zero LLM, zero randomness, zero I/O).
2. Authoritative money arithmetic strictly uses integer minor units (paise).
3. Evaluates and separates:
   - Gross Recovered Value vs. Natural Recovered Value
   - Incremental Recovered Value vs. Net Incremental Revenue
4. Compares unconstrained economic optimality against merchant policy boundaries.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Mapping, Optional

from domain.intelligence.models.action_economics import (
    ActionEconomicParameters,
    ActionEvaluation,
    RecoveryDecisionRecommendation,
)
from domain.intelligence.models.context import RecoveryContext
from domain.policies.validator import validate_action_against_policy
from domain.shared.enums import RecoveryActionType


def calculate_action_economic_evaluation(
    *,
    context: RecoveryContext,
    action_params: ActionEconomicParameters,
    natural_recovery_probability: float,
    now: Optional[datetime] = None,
) -> ActionEvaluation:
    """
    Deterministically evaluate a single recovery action candidate against a RecoveryContext.

    Args:
        context: Full RecoveryContext.
        action_params: Cost and success probability assumptions for this action.
        natural_recovery_probability: Baseline probability that customer recovers without intervention (0.0 to 1.0).
        now: Evaluation timestamp.

    Returns:
        ActionEvaluation with exact integer monetary amounts.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    amount_minor = context.amount_minor
    p_action = action_params.estimated_success_probability
    p_natural = natural_recovery_probability
    discount_pct = action_params.discount_percent_offered
    cost_minor = action_params.intervention_cost_minor

    # 1. Gross expected recovery amount (discount-adjusted)
    discount_multiplier = 1.0 - (discount_pct / 100.0)
    expected_gross_revenue_minor = int(round(amount_minor * p_action * discount_multiplier))

    # 2. Natural recovery expected amount (counterfactual without intervention)
    expected_natural_revenue_minor = int(round(amount_minor * p_natural))

    # 3. Incremental recovery amount over natural recovery
    expected_incremental_revenue_minor = expected_gross_revenue_minor - expected_natural_revenue_minor

    # 4. Net incremental revenue after accounting for intervention cost
    expected_net_incremental_revenue_minor = expected_incremental_revenue_minor - cost_minor

    incremental_prob = p_action - p_natural

    # Special handling for WAIT action (guaranteed 0 cost, 0 incremental revenue)
    if action_params.action_type == RecoveryActionType.WAIT:
        expected_gross_revenue_minor = expected_natural_revenue_minor
        expected_incremental_revenue_minor = 0
        expected_net_incremental_revenue_minor = 0
        incremental_prob = 0.0
        cost_minor = 0

    # 5. Evaluate policy compliance using Block 1 deterministic policy gate (P-03)
    policy_result = validate_action_against_policy(
        policy=context.policy,
        action_type=action_params.action_type,
        payment_amount_minor=amount_minor,
        completed_interventions=context.completed_interventions,
        last_action_at=context.last_action_at,
        requested_discount_percent=discount_pct if discount_pct > 0 else None,
        now=now,
    )

    return ActionEvaluation(
        action_type=action_params.action_type,
        estimated_success_probability=p_action,
        natural_recovery_probability=p_natural,
        incremental_recovery_probability=incremental_prob,
        expected_gross_revenue_minor=expected_gross_revenue_minor,
        expected_natural_revenue_minor=expected_natural_revenue_minor,
        expected_incremental_revenue_minor=expected_incremental_revenue_minor,
        intervention_cost_minor=cost_minor,
        expected_net_incremental_revenue_minor=expected_net_incremental_revenue_minor,
        is_policy_compliant=policy_result.is_valid,
        policy_violations=policy_result.violations,
        requires_human_approval=policy_result.requires_approval,
        discount_percent_offered=discount_pct,
    )


def evaluate_all_candidate_actions(
    *,
    context: RecoveryContext,
    candidate_economics: Mapping[RecoveryActionType, ActionEconomicParameters],
    natural_recovery_probability: float,
    scenario_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> RecoveryDecisionRecommendation:
    """
    Evaluate all candidate recovery actions, ranking them by expected net incremental revenue
    and determining both the unconstrained economic optimal and the policy-permitted optimal.

    Args:
        context: Full RecoveryContext.
        candidate_economics: Mapping of RecoveryActionType to ActionEconomicParameters.
        natural_recovery_probability: Probability of natural recovery (World A).
        scenario_id: Optional tracking ID of the scenario.
        now: Timestamp.

    Returns:
        RecoveryDecisionRecommendation containing comprehensive evaluations and decisions.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    # Ensure WAIT is always present as a candidate
    evaluations: list[ActionEvaluation] = []
    for action_type in RecoveryActionType:
        if action_type in candidate_economics:
            params = candidate_economics[action_type]
        else:
            # Default fallback for unconfigured action types
            params = ActionEconomicParameters(
                action_type=action_type,
                intervention_cost_minor=0 if action_type == RecoveryActionType.WAIT else 100,
                estimated_success_probability=natural_recovery_probability if action_type == RecoveryActionType.WAIT else 0.0,
            )

        eval = calculate_action_economic_evaluation(
            context=context,
            action_params=params,
            natural_recovery_probability=natural_recovery_probability,
            now=now,
        )
        evaluations.append(eval)

    # 1. Unconstrained Economically Optimal Action
    # Rank primarily by expected_net_incremental_revenue_minor descending.
    # Tie-breaking: lower intervention_cost_minor, then WAIT preferred.
    sorted_by_economic_value = sorted(
        evaluations,
        key=lambda e: (
            e.expected_net_incremental_revenue_minor,
            -e.intervention_cost_minor,
            1 if e.action_type == RecoveryActionType.WAIT else 0,
        ),
        reverse=True,
    )
    economic_optimal = sorted_by_economic_value[0]

    # 2. Policy-Permitted Optimal Action
    # Filter for is_policy_compliant == True.
    compliant_evaluations = [e for e in sorted_by_economic_value if e.is_policy_compliant]

    if not compliant_evaluations:
        # Fallback to WAIT if no action is compliant (WAIT is always structurally allowed)
        wait_eval = next((e for e in evaluations if e.action_type == RecoveryActionType.WAIT), economic_optimal)
        policy_permitted = wait_eval
    else:
        # If the highest compliant action has net value <= 0, prefer WAIT (do not spend money for negative return)
        best_compliant = compliant_evaluations[0]
        if best_compliant.expected_net_incremental_revenue_minor <= 0:
            wait_eval = next((e for e in evaluations if e.action_type == RecoveryActionType.WAIT), best_compliant)
            policy_permitted = wait_eval
        else:
            policy_permitted = best_compliant

    is_policy_override = (economic_optimal.action_type != policy_permitted.action_type)

    return RecoveryDecisionRecommendation(
        decision_id=uuid.uuid4(),
        scenario_id=scenario_id,
        context=context,
        candidate_evaluations=evaluations,
        economically_optimal_action=economic_optimal.action_type,
        economically_optimal_net_revenue_minor=economic_optimal.expected_net_incremental_revenue_minor,
        policy_permitted_action=policy_permitted.action_type,
        policy_permitted_net_revenue_minor=policy_permitted.expected_net_incremental_revenue_minor,
        recommended_action=policy_permitted.action_type,
        recommended_discount_percent=policy_permitted.discount_percent_offered,
        expected_net_incremental_revenue_minor=policy_permitted.expected_net_incremental_revenue_minor,
        is_policy_override=is_policy_override,
        evaluation_timestamp=now,
    )
