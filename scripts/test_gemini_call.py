import asyncio
import os
import uuid
from datetime import datetime, timezone
from apps.api.settings import get_settings
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType
from infrastructure.ai.client import GeminiRESTClient

async def test_real_gemini_decision():
    settings = get_settings()
    gemini_client = GeminiRESTClient(
        api_key=settings.ai_api_key,
        model="gemini-flash-latest",
        timeout_seconds=15.0
    )
    provider = AIDecisionProvider(client=gemini_client, settings=settings)
    
    policy = MerchantRecoveryPolicy(
        merchant_id=uuid.uuid4(),
        maximum_interventions=3,
        cooldown_hours=2,
        high_value_threshold_minor=1000000, # ₹10,000
        maximum_discount_percent=10,
        high_value_requires_approval=True
    )
    
    payment = PaymentFailureDetails(
        payment_id=uuid.uuid4(),
        amount_minor=2500000, # ₹25,000
        currency="INR",
        payment_method=PaymentMethod.CARD,
        attempt_count=1,
        failure_code="CUSTOMER_AUTHENTICATION_FAILED",
        failure_reason="OTP expired during 3DS verification",
        failed_at=datetime.now(tz=timezone.utc),
    )
    
    customer = CustomerProfile(
        customer_id=uuid.uuid4(),
        historical_payment_count=42,
        historical_success_rate=0.92,
        historical_failure_rate=0.08,
        prior_interventions_count=0,
        customer_segment="VIP"
    )
    
    temporal = TemporalContext(
        current_time=datetime.now(tz=timezone.utc),
        hour_of_day=14,
        day_of_week=4,
        time_since_failure_seconds=30,
        is_cooldown_active=False,
    )
    
    context = RecoveryContext(
        payment=payment,
        customer=customer,
        policy=policy,
        temporal=temporal,
        completed_interventions=0,
        last_action_at=None,
    )
    
    print("Evaluating recovery decision with REAL GEMINI...")
    rec = await provider.evaluate_decision_async(context, scenario_id="63f5c724-61b7-4679-91ae-d9862eca9deb")
    record = provider.last_decision_record
    
    print("=== DECISION RESULT ===")
    print("Recommended Action:", rec.recommended_action.value)
    print("Economically Optimal Action:", rec.economically_optimal_action.value)
    print("Policy Permitted Action:", rec.policy_permitted_action.value)
    print("Expected Net Incremental (Paise):", rec.expected_net_incremental_revenue_minor)
    print("Is Policy Override:", rec.is_policy_override)
    print("\n=== AI AUDIT RECORD ===")
    print("Provider:", record.provider)
    print("Model:", record.model)
    print("Confidence:", record.confidence)
    print("Uncertainty:", record.uncertainty)
    print("Fallback Used:", record.fallback_used)
    print("Fallback Reason:", record.fallback_reason)
    print("Latency (ms):", record.latency_ms)
    print("Input Tokens:", record.input_tokens)
    print("Output Tokens:", record.output_tokens)
    print("Estimated LLM Cost (Paise):", record.estimated_llm_cost_minor)
    print("Raw Proposal:", record.raw_proposal)

if __name__ == "__main__":
    asyncio.run(test_real_gemini_decision())
