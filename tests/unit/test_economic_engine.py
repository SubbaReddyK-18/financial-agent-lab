"""
tests/unit/test_economic_engine.py

Unit tests for the Deterministic Economic Value Engine.

Validates:
- Exact integer monetary calculations (FS-01, minor units / paise).
- Separation of Gross, Natural, Incremental, and Net Incremental Revenue.
- Invariants (zero incremental probability, negative expected value, scaling).
- WAIT winning over expensive interventions.
- Policy vs. Economics decoupling (unconstrained economic optimal vs policy permitted).
"""

import uuid
from datetime import datetime, timezone

import pytest

from domain.intelligence.economic_engine import (
    calculate_action_economic_evaluation,
    evaluate_all_candidate_actions,
)
from domain.intelligence.models.action_economics import ActionEconomicParameters
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType


@pytest.fixture
def base_context() -> RecoveryContext:
    merchant_id = uuid.uuid4()
    policy = MerchantRecoveryPolicy(
        merchant_id=merchant_id,
        maximum_discount_percent=10,
        maximum_interventions=3,
        cooldown_hours=2,
        high_value_threshold_minor=10000_00,  # ₹10,000
    )
    payment = PaymentFailureDetails(
        payment_id=uuid.uuid4(),
        amount_minor=1000_00,  # ₹1,000.00
        currency="INR",
        payment_method=PaymentMethod.UPI,
        attempt_count=1,
        failure_code="GATEWAY_TIMEOUT",
    )
    customer = CustomerProfile(
        customer_id=uuid.uuid4(),
        historical_success_rate=0.85,
        historical_failure_rate=0.15,
    )
    return RecoveryContext(
        payment=payment,
        customer=customer,
        policy=policy,
        completed_interventions=0,
    )


class TestEconomicFormulas:
    def test_exact_incremental_and_net_revenue_calculation(self, base_context: RecoveryContext):
        """
        Amount = ₹1,000 (100,000 paise)
        P(Natural) = 0.30 -> Expected Natural = ₹300 (30,000 paise)
        P(Action) = 0.55 -> Expected Gross = ₹550 (55,000 paise)
        Intervention Cost = ₹20 (2,000 paise)
        Expected Incremental = ₹550 - ₹300 = ₹250 (25,000 paise)
        Expected Net Incremental Revenue = ₹250 - ₹20 = ₹230 (23,000 paise)
        """
        params = ActionEconomicParameters(
            action_type=RecoveryActionType.RETRY,
            intervention_cost_minor=20_00,  # ₹20.00
            estimated_success_probability=0.55,
        )

        eval = calculate_action_economic_evaluation(
            context=base_context,
            action_params=params,
            natural_recovery_probability=0.30,
        )

        assert eval.expected_gross_revenue_minor == 550_00
        assert eval.expected_natural_revenue_minor == 300_00
        assert eval.expected_incremental_revenue_minor == 250_00
        assert eval.intervention_cost_minor == 20_00
        assert eval.expected_net_incremental_revenue_minor == 230_00
        assert eval.is_policy_compliant is True

    def test_discount_adjustment_reduces_gross_recovery(self, base_context: RecoveryContext):
        """
        Amount = ₹1,000 (100,000 paise)
        P(Natural) = 0.20 -> Expected Natural = ₹200
        P(Action) = 0.60, Discount = 10%
        Gross = 100,000 * 0.60 * 0.90 = 54,000 paise (₹540)
        Incremental = 54,000 - 20,000 = 34,000 paise (₹340)
        Cost = ₹50 (5,000 paise)
        Net = 34,000 - 5,000 = 29,000 paise (₹290)
        """
        params = ActionEconomicParameters(
            action_type=RecoveryActionType.PAYMENT_LINK,
            intervention_cost_minor=50_00,
            estimated_success_probability=0.60,
            discount_percent_offered=10,
        )

        eval = calculate_action_economic_evaluation(
            context=base_context,
            action_params=params,
            natural_recovery_probability=0.20,
        )

        assert eval.expected_gross_revenue_minor == 540_00
        assert eval.expected_natural_revenue_minor == 200_00
        assert eval.expected_incremental_revenue_minor == 340_00
        assert eval.expected_net_incremental_revenue_minor == 290_00

    def test_wait_always_has_zero_incremental_revenue_and_zero_cost(self, base_context: RecoveryContext):
        params = ActionEconomicParameters(
            action_type=RecoveryActionType.WAIT,
            intervention_cost_minor=0,
            estimated_success_probability=0.35,
        )

        eval = calculate_action_economic_evaluation(
            context=base_context,
            action_params=params,
            natural_recovery_probability=0.35,
        )

        assert eval.expected_gross_revenue_minor == 350_00
        assert eval.expected_natural_revenue_minor == 350_00
        assert eval.expected_incremental_revenue_minor == 0
        assert eval.intervention_cost_minor == 0
        assert eval.expected_net_incremental_revenue_minor == 0


class TestEconomicInvariants:
    def test_zero_incremental_probability_with_cost_yields_negative_net_revenue(
        self, base_context: RecoveryContext
    ):
        """Invariant: If P(action) == P(natural) and Cost > 0, Net Incremental Revenue = -Cost < 0."""
        params = ActionEconomicParameters(
            action_type=RecoveryActionType.RETRY,
            intervention_cost_minor=20_00,
            estimated_success_probability=0.40,
        )

        eval = calculate_action_economic_evaluation(
            context=base_context,
            action_params=params,
            natural_recovery_probability=0.40,
        )

        assert eval.expected_incremental_revenue_minor == 0
        assert eval.expected_net_incremental_revenue_minor == -20_00
        assert eval.is_economically_positive is False

    def test_sub_natural_action_yields_strongly_negative_net_revenue(
        self, base_context: RecoveryContext
    ):
        """If action success is worse than natural recovery, net revenue is negative."""
        params = ActionEconomicParameters(
            action_type=RecoveryActionType.RETRY,
            intervention_cost_minor=10_00,
            estimated_success_probability=0.20,
        )

        eval = calculate_action_economic_evaluation(
            context=base_context,
            action_params=params,
            natural_recovery_probability=0.30,
        )

        assert eval.expected_incremental_revenue_minor == -100_00
        assert eval.expected_net_incremental_revenue_minor == -110_00

    def test_wait_wins_when_all_interventions_have_negative_expected_return(
        self, base_context: RecoveryContext
    ):
        """When cost exceeds incremental value, WAIT must be chosen as optimal."""
        economics = {
            RecoveryActionType.WAIT: ActionEconomicParameters(
                action_type=RecoveryActionType.WAIT,
                intervention_cost_minor=0,
                estimated_success_probability=0.30,
            ),
            RecoveryActionType.RETRY: ActionEconomicParameters(
                action_type=RecoveryActionType.RETRY,
                intervention_cost_minor=50_00,  # ₹50 cost
                estimated_success_probability=0.32,  # ₹20 gain -> -₹30 net
            ),
            RecoveryActionType.ESCALATE: ActionEconomicParameters(
                action_type=RecoveryActionType.ESCALATE,
                intervention_cost_minor=500_00,  # ₹500 cost
                estimated_success_probability=0.40,  # ₹100 gain -> -₹400 net
            ),
        }

        rec = evaluate_all_candidate_actions(
            context=base_context,
            candidate_economics=economics,
            natural_recovery_probability=0.30,
        )

        assert rec.economically_optimal_action == RecoveryActionType.WAIT
        assert rec.recommended_action == RecoveryActionType.WAIT
        assert rec.expected_net_incremental_revenue_minor == 0


class TestPolicyVsEconomicsSeparation:
    def test_policy_prohibits_economically_optimal_action(self, base_context: RecoveryContext):
        """
        Scenario:
        - PAYMENT_LINK has highest expected net revenue (+₹400), but merchant policy limits discount to 10% and link requested 20%.
        - RETRY is second highest (+₹200) and fully policy compliant.
        - Result:
          - economically_optimal_action = PAYMENT_LINK
          - policy_permitted_action = RETRY
          - recommended_action = RETRY
          - is_policy_override = True
        """
        economics = {
            RecoveryActionType.WAIT: ActionEconomicParameters(
                action_type=RecoveryActionType.WAIT,
                intervention_cost_minor=0,
                estimated_success_probability=0.20,
            ),
            RecoveryActionType.RETRY: ActionEconomicParameters(
                action_type=RecoveryActionType.RETRY,
                intervention_cost_minor=20_00,
                estimated_success_probability=0.50,  # +₹280 net
            ),
            RecoveryActionType.PAYMENT_LINK: ActionEconomicParameters(
                action_type=RecoveryActionType.PAYMENT_LINK,
                intervention_cost_minor=10_00,
                estimated_success_probability=0.80,
                discount_percent_offered=25,  # Exceeds policy max of 10%!
            ),
        }

        rec = evaluate_all_candidate_actions(
            context=base_context,
            candidate_economics=economics,
            natural_recovery_probability=0.20,
        )

        assert rec.economically_optimal_action == RecoveryActionType.PAYMENT_LINK
        assert rec.policy_permitted_action == RecoveryActionType.RETRY
        assert rec.recommended_action == RecoveryActionType.RETRY
        assert rec.is_policy_override is True
