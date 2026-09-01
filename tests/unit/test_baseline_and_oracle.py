"""
tests/unit/test_baseline_and_oracle.py

Unit tests for DeterministicBaselineDecisionProvider and SimulationOracleDecisionProvider.
"""

import uuid
import pytest

from domain.intelligence.baseline import DeterministicBaselineDecisionProvider
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.intelligence.oracle import SimulationOracleDecisionProvider
from domain.intelligence.simulation.generator import SyntheticScenarioGenerator
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType


@pytest.fixture
def policy() -> MerchantRecoveryPolicy:
    return MerchantRecoveryPolicy(
        merchant_id=uuid.uuid4(),
        maximum_discount_percent=10,
        maximum_interventions=3,
        cooldown_hours=2,
        high_value_threshold_minor=10000_00,
    )


class TestBaselineProvider:
    def test_retryable_technical_error_selects_retry(self, policy: MerchantRecoveryPolicy):
        context = RecoveryContext(
            payment=PaymentFailureDetails(
                payment_id=uuid.uuid4(),
                amount_minor=1500_00,
                payment_method=PaymentMethod.UPI,
                attempt_count=1,
                failure_code="GATEWAY_TIMEOUT",
            ),
            customer=CustomerProfile(customer_id=uuid.uuid4()),
            policy=policy,
            completed_interventions=0,
        )

        provider = DeterministicBaselineDecisionProvider()
        decision = provider.evaluate_decision(context)

        assert decision.recommended_action == RecoveryActionType.RETRY

    def test_customer_actionable_code_selects_link_or_notify(self, policy: MerchantRecoveryPolicy):
        context = RecoveryContext(
            payment=PaymentFailureDetails(
                payment_id=uuid.uuid4(),
                amount_minor=2000_00,
                payment_method=PaymentMethod.CARD,
                attempt_count=1,
                failure_code="OTP_TIMEOUT",
            ),
            customer=CustomerProfile(customer_id=uuid.uuid4(), customer_segment="VIP"),
            policy=policy,
            completed_interventions=0,
        )

        provider = DeterministicBaselineDecisionProvider()
        decision = provider.evaluate_decision(context)

        assert decision.recommended_action == RecoveryActionType.PAYMENT_LINK
        assert decision.recommended_discount_percent == 5

    def test_cooldown_active_forces_wait(self, policy: MerchantRecoveryPolicy):
        from datetime import datetime, timezone

        context = RecoveryContext(
            payment=PaymentFailureDetails(
                payment_id=uuid.uuid4(),
                amount_minor=1500_00,
                failure_code="GATEWAY_TIMEOUT",
            ),
            customer=CustomerProfile(customer_id=uuid.uuid4()),
            policy=policy,
            completed_interventions=1,
            temporal=TemporalContext(
                current_time=datetime.now(tz=timezone.utc),
                is_cooldown_active=True,
            ),
        )

        provider = DeterministicBaselineDecisionProvider()
        decision = provider.evaluate_decision(context)

        assert decision.recommended_action == RecoveryActionType.WAIT

    def test_max_interventions_exhausted_forces_wait(self, policy: MerchantRecoveryPolicy):
        context = RecoveryContext(
            payment=PaymentFailureDetails(
                payment_id=uuid.uuid4(),
                amount_minor=1500_00,
                failure_code="GATEWAY_TIMEOUT",
            ),
            customer=CustomerProfile(customer_id=uuid.uuid4()),
            policy=policy,
            completed_interventions=3,  # Reached max 3
        )

        provider = DeterministicBaselineDecisionProvider()
        decision = provider.evaluate_decision(context)

        assert decision.recommended_action == RecoveryActionType.WAIT


class TestOracleProvider:
    def test_oracle_selects_strictly_highest_net_revenue_action(self):
        generator = SyntheticScenarioGenerator(seed=42)
        scenario = generator.generate_scenario(0)

        oracle = SimulationOracleDecisionProvider()
        decision = oracle.evaluate_decision_with_ground_truth(
            context=scenario.context,
            candidate_economics=scenario.ground_truth_candidate_economics,
            natural_recovery_probability=scenario.ground_truth_natural_recovery_prob,
        )

        # Oracle recommendation must have the highest expected net incremental revenue among candidates
        evals = decision.candidate_evaluations
        max_net = max(e.expected_net_incremental_revenue_minor for e in evals if e.is_policy_compliant)
        assert decision.expected_net_incremental_revenue_minor == max_net
