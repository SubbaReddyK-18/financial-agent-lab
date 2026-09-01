"""
tests/unit/test_ai_context_and_schema.py

Unit tests for AI Observability Boundary sanitization and Pydantic schema validation.

Validates:
- AIRecoveryContext contains ONLY observable features.
- Zero ground truth simulation variables exist in the AI context.
- AIDecisionProposal strictly enforces bounds and schema constraints.
"""

import uuid
import pytest
from pydantic import ValidationError

from domain.intelligence.ai.models import AIDecisionProposal, AIRecoveryContext
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType


@pytest.fixture
def sample_context() -> RecoveryContext:
    policy = MerchantRecoveryPolicy(
        merchant_id=uuid.uuid4(),
        maximum_discount_percent=10,
        maximum_interventions=3,
        cooldown_hours=2,
        high_value_threshold_minor=10000_00,
    )
    payment = PaymentFailureDetails(
        payment_id=uuid.uuid4(),
        amount_minor=1500_00,
        currency="INR",
        payment_method=PaymentMethod.UPI,
        attempt_count=1,
        failure_code="GATEWAY_TIMEOUT",
        failure_reason="Network timeout on bank switch",
    )
    customer = CustomerProfile(
        customer_id=uuid.uuid4(),
        historical_success_rate=0.90,
        historical_failure_rate=0.10,
        customer_segment="VIP",
    )
    return RecoveryContext(
        payment=payment,
        customer=customer,
        policy=policy,
        completed_interventions=0,
    )


class TestAIObservabilityBoundary:
    def test_context_sanitization_contains_only_observables(self, sample_context: RecoveryContext):
        ai_ctx = AIRecoveryContext.from_recovery_context(sample_context)

        # Observable attributes present
        assert ai_ctx.amount_minor == 1500_00
        assert ai_ctx.amount_inr == 1500.00
        assert ai_ctx.failure_code == "GATEWAY_TIMEOUT"
        assert ai_ctx.customer_segment == "VIP"
        assert ai_ctx.merchant_max_discount_percent == 10

        # Verify hidden ground truth attributes are completely absent
        assert not hasattr(ai_ctx, "ground_truth_natural_recovery_prob")
        assert not hasattr(ai_ctx, "ground_truth_candidate_economics")
        assert not hasattr(ai_ctx, "oracle_action")
        assert not hasattr(ai_ctx, "future_outcome")


class TestAIDecisionProposalSchema:
    def test_valid_proposal_parsed_successfully(self):
        json_data = {
            "recommended_action": "RETRY",
            "confidence": 0.85,
            "estimated_action_success_probability": 0.65,
            "estimated_natural_recovery_probability": 0.25,
            "reasoning_codes": ["transient_error", "low_attempts"],
            "uncertainty": "LOW",
            "requires_human_review": False,
            "concise_rationale": "Transient technical failure on first attempt.",
            "recommended_discount_percent": 0,
        }

        proposal = AIDecisionProposal.model_validate(json_data)
        assert proposal.recommended_action == RecoveryActionType.RETRY
        assert proposal.confidence == 0.85
        assert proposal.reasoning_codes == ["TRANSIENT_ERROR", "LOW_ATTEMPTS"]
        assert proposal.uncertainty == "LOW"

    def test_invalid_action_name_rejected(self):
        with pytest.raises(ValidationError):
            AIDecisionProposal.model_validate({
                "recommended_action": "INVALID_ACTION_NAME",
                "confidence": 0.80,
            })

    def test_confidence_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            AIDecisionProposal.model_validate({
                "recommended_action": "WAIT",
                "confidence": 1.5,  # > 1.0
            })

        with pytest.raises(ValidationError):
            AIDecisionProposal.model_validate({
                "recommended_action": "WAIT",
                "confidence": -0.1,  # < 0.0
            })

    def test_probability_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            AIDecisionProposal.model_validate({
                "recommended_action": "WAIT",
                "confidence": 0.5,
                "estimated_action_success_probability": 1.2,
            })

    def test_discount_out_of_bounds_rejected(self):
        with pytest.raises(ValidationError):
            AIDecisionProposal.model_validate({
                "recommended_action": "PAYMENT_LINK",
                "confidence": 0.5,
                "recommended_discount_percent": 150,  # > 100
            })
