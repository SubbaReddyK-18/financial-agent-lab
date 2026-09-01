"""
tests/unit/test_ai_provider_and_fallback.py

Unit tests for AIDecisionProvider, policy gate enforcement, and deterministic baseline fallback.
"""

import uuid
import pytest

from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType
from infrastructure.ai.client import MockLLMClient


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
        amount_minor=2000_00,
        currency="INR",
        payment_method=PaymentMethod.UPI,
        attempt_count=1,
        failure_code="GATEWAY_TIMEOUT",
    )
    customer = CustomerProfile(
        customer_id=uuid.uuid4(),
        historical_success_rate=0.85,
    )
    return RecoveryContext(
        payment=payment,
        customer=customer,
        policy=policy,
        completed_interventions=0,
    )


class TestAIProviderAndFallback:
    def test_normal_successful_proposal(self, sample_context: RecoveryContext):
        canned_json = """{
            "recommended_action": "RETRY",
            "confidence": 0.88,
            "estimated_action_success_probability": 0.70,
            "estimated_natural_recovery_probability": 0.25,
            "reasoning_codes": ["TRANSIENT_FAILURE"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "concise_rationale": "Clear transient network error.",
            "recommended_discount_percent": 0
        }"""
        client = MockLLMClient(canned_response=canned_json)
        provider = AIDecisionProvider(client=client)

        rec = provider.evaluate_decision(sample_context)
        audit = provider.last_decision_record

        assert rec.recommended_action == RecoveryActionType.RETRY
        assert audit is not None
        assert audit.fallback_used is False
        assert audit.confidence == 0.88

    def test_provider_network_failure_triggers_deterministic_fallback(self, sample_context: RecoveryContext):
        client = MockLLMClient(should_fail=True, failure_error=TimeoutError("Connection timed out"))
        provider = AIDecisionProvider(client=client)

        rec = provider.evaluate_decision(sample_context)
        audit = provider.last_decision_record

        # Must fall back gracefully to Deterministic Baseline
        assert audit is not None
        assert audit.fallback_used is True
        assert "Connection timed out" in str(audit.fallback_reason)
        # Baseline chooses RETRY for GATEWAY_TIMEOUT attempt 1
        assert rec.recommended_action == RecoveryActionType.RETRY

    def test_malformed_json_triggers_deterministic_fallback(self, sample_context: RecoveryContext):
        client = MockLLMClient(canned_response="{malformed_json_response...")
        provider = AIDecisionProvider(client=client)

        rec = provider.evaluate_decision(sample_context)
        audit = provider.last_decision_record

        assert audit is not None
        assert audit.fallback_used is True
        assert "validation error" in str(audit.fallback_reason).lower() or "json" in str(audit.fallback_reason).lower()

    def test_policy_violating_ai_action_rejected_by_policy_gate(self, sample_context: RecoveryContext):
        """
        AI proposes a 25% discount, but merchant policy caps discount at 10%.
        The policy gate must reject the proposal and trigger fallback.
        """
        canned_json = """{
            "recommended_action": "PAYMENT_LINK",
            "confidence": 0.90,
            "reasoning_codes": ["EXCESSIVE_DISCOUNT"],
            "uncertainty": "LOW",
            "requires_human_review": false,
            "concise_rationale": "Offering generous discount.",
            "recommended_discount_percent": 25
        }"""
        client = MockLLMClient(canned_response=canned_json)
        provider = AIDecisionProvider(client=client)

        rec = provider.evaluate_decision(sample_context)
        audit = provider.last_decision_record

        assert audit is not None
        assert audit.fallback_used is True
        assert "Policy violation" in str(audit.fallback_reason)
