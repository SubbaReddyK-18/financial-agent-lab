"""
domain/intelligence/ai/prompt.py

Versioned system prompts and prompt builders for AI Recovery Decision Agent.

ARCHITECTURAL PRINCIPLES (Block 4, Part 11 & Part 27):
- Prompts force reasoning over observable features without hallucinating hidden information.
- Zero oracle information, true success probabilities, or future outcomes are exposed.
- System prompt is strictly versioned.
"""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict

from domain.intelligence.ai.models import AIRecoveryContext

PROMPT_VERSION = "v1.0"
AGENT_BUNDLE_VERSION = "recovery-decision-agent/v1"

SYSTEM_PROMPT = """You are an AI Recovery Decision Assistant for Financial Agent Lab.
Your task is to analyze a failed payment's observable context and propose the single most appropriate recovery action from the permitted set.

Permitted Actions:
- WAIT: Take no immediate action. Use when natural recovery is likely, cooldown is active, max interventions reached, or the failure indicates permanent customer abandonment/terminal block.
- RETRY: Automatically re-attempt processing with the gateway. Use for transient network/technical glitches on low attempt counts.
- PAYMENT_LINK: Generate and send a fresh payment link (optionally with a policy-bounded discount). Use for customer-actionable drop-offs (e.g. OTP timeout, app drop) where a fresh checkout is appropriate.
- NOTIFY: Send an informational push notification/SMS to the customer. Use for high-value payments or reminder-sensitive situations.
- ESCALATE: Route the case to human operations/support. Use for high-value or VIP customers requiring manual review.

CRITICAL OPERATIONAL RULES:
1. Do NOT assume hidden information exists.
2. Do NOT invent merchant policies or exceed the stated merchant limits.
3. If cooldown is active or merchant maximum interventions have been reached, you MUST choose WAIT.
4. Do NOT calculate authoritative monetary numbers; focus on economic reasoning and probability inference.
5. Return ONLY a valid JSON object strictly conforming to the required schema.

Required JSON Output Schema:
{
  "recommended_action": "WAIT" | "RETRY" | "PAYMENT_LINK" | "NOTIFY" | "ESCALATE",
  "confidence": 0.0 to 1.0,
  "estimated_action_success_probability": 0.0 to 1.0 (optional float),
  "estimated_natural_recovery_probability": 0.0 to 1.0 (optional float),
  "reasoning_codes": ["STRING_CODE_1", "STRING_CODE_2"],
  "uncertainty": "LOW" | "MEDIUM" | "HIGH",
  "requires_human_review": true | false,
  "concise_rationale": "Short 1-2 sentence explanation.",
  "recommended_discount_percent": 0 to 100 (integer)
}
"""
PROMPT_SHA256 = hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()


class RecoveryPromptBuilder:
    """
    Constructs versioned prompts for AI recovery decision inference.
    """

    version: str = PROMPT_VERSION
    bundle_version: str = AGENT_BUNDLE_VERSION
    content_hash: str = PROMPT_SHA256

    @classmethod
    def get_system_prompt(cls) -> str:
        return SYSTEM_PROMPT

    @classmethod
    def build_user_prompt(cls, context: AIRecoveryContext) -> str:
        """
        Render observable context into a structured JSON string for the model.
        """
        payload = {
            "payment": {
                "amount_inr": context.amount_inr,
                "amount_paise": context.amount_minor,
                "currency": context.currency,
                "payment_method": context.payment_method,
                "attempt_count": context.attempt_count,
                "failure_code": context.failure_code,
                "failure_reason": context.failure_reason,
                "time_since_failure_seconds": context.time_since_failure_seconds,
            },
            "customer_profile": {
                "historical_success_rate": context.customer_historical_success_rate,
                "historical_failure_rate": context.customer_historical_failure_rate,
                "prior_interventions_count": context.customer_prior_interventions,
                "customer_segment": context.customer_segment,
            },
            "merchant_policy": {
                "max_interventions": context.merchant_max_interventions,
                "max_discount_percent": context.merchant_max_discount_percent,
                "cooldown_hours": context.merchant_cooldown_hours,
                "is_high_value_payment": context.is_high_value_payment,
            },
            "temporal_context": {
                "hour_of_day": context.hour_of_day,
                "day_of_week": context.day_of_week,
                "is_cooldown_active": context.is_cooldown_active,
            },
        }
        return f"Evaluate this failed payment context and propose the optimal recovery action:\n\n{json.dumps(payload, indent=2)}"
