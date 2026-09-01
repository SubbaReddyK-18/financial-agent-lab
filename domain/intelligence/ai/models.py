"""
domain/intelligence/ai/models.py

Domain models for AI-assisted recovery decision evaluation.

ARCHITECTURAL PRINCIPLES (P-01, P-02, Block 4):
1. Strict Observability Boundary: `AIRecoveryContext` contains only observable attributes.
2. Strict Schema Validation: `AIDecisionProposal` validates structured JSON proposals.
3. Decoupled Persistence & Audit: `AIDecisionRecord` captures proposal + fallback + economics.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from domain.intelligence.models.action_economics import ActionEvaluation, RecoveryDecisionRecommendation
from domain.intelligence.models.context import RecoveryContext
from domain.policies.validator import PolicyValidationResult
from domain.shared.enums import RecoveryActionType


@dataclass(frozen=True)
class AIRecoveryContext:
    """
    Sanitized, AI-safe representation of the recovery decision context.

    Contains STRICTLY observable attributes. Contains ZERO hidden ground truth.
    """

    amount_minor: int
    amount_inr: float
    currency: str
    payment_method: str
    attempt_count: int
    failure_code: str
    failure_reason: Optional[str]
    time_since_failure_seconds: int

    # Customer behavioral observables
    customer_historical_success_rate: float
    customer_historical_failure_rate: float
    customer_prior_interventions: int
    customer_segment: str

    # Merchant policy observables
    merchant_max_interventions: int
    merchant_max_discount_percent: int
    merchant_cooldown_hours: int
    is_high_value_payment: bool

    # Temporal observables
    hour_of_day: int
    day_of_week: int
    is_cooldown_active: bool

    @classmethod
    def from_recovery_context(cls, ctx: RecoveryContext) -> AIRecoveryContext:
        """Create sanitized AI context from domain RecoveryContext."""
        time_elapsed = ctx.temporal.time_since_failure_seconds if ctx.temporal else 60
        is_cooldown = ctx.temporal.is_cooldown_active if ctx.temporal else False
        hour = ctx.temporal.hour_of_day if ctx.temporal else 12
        day = ctx.temporal.day_of_week if ctx.temporal else 0

        return cls(
            amount_minor=ctx.payment.amount_minor,
            amount_inr=round(ctx.payment.amount_minor / 100.0, 2),
            currency=ctx.payment.currency,
            payment_method=ctx.payment.payment_method.value,
            attempt_count=ctx.payment.attempt_count,
            failure_code=ctx.payment.failure_code,
            failure_reason=ctx.payment.failure_reason,
            time_since_failure_seconds=time_elapsed,
            customer_historical_success_rate=ctx.customer.historical_success_rate,
            customer_historical_failure_rate=ctx.customer.historical_failure_rate,
            customer_prior_interventions=ctx.completed_interventions,
            customer_segment=ctx.customer.customer_segment,
            merchant_max_interventions=ctx.policy.maximum_interventions,
            merchant_max_discount_percent=ctx.policy.maximum_discount_percent,
            merchant_cooldown_hours=ctx.policy.cooldown_hours,
            is_high_value_payment=ctx.is_high_value,
            hour_of_day=hour,
            day_of_week=day,
            is_cooldown_active=is_cooldown,
        )


class AIDecisionProposal(BaseModel):
    """
    Strict Pydantic schema for structured output from the LLM.
    """

    recommended_action: RecoveryActionType
    confidence: float = Field(..., ge=0.0, le=1.0, description="Model confidence score between 0.0 and 1.0")
    estimated_action_success_probability: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Optional subjective probability estimate of recovery with action"
    )
    estimated_natural_recovery_probability: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Optional subjective probability estimate of natural recovery"
    )
    reasoning_codes: list[str] = Field(
        default_factory=list, description="Standardized categorization reason codes"
    )
    uncertainty: str = Field(
        default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH)$", description="Self-assessed uncertainty level"
    )
    requires_human_review: bool = Field(
        default=False, description="Flag indicating human intervention is advised"
    )
    concise_rationale: str = Field(
        default="", max_length=500, description="Short 1-2 sentence non-authoritative summary explanation"
    )
    recommended_discount_percent: int = Field(
        default=0, ge=0, le=100, description="Discount percentage recommended for payment link (0-100)"
    )

    @field_validator("reasoning_codes", mode="after")
    @classmethod
    def _validate_reasoning_codes(cls, codes: list[str]) -> list[str]:
        return [c.strip().upper() for c in codes if c and c.strip()]


@dataclass(frozen=True)
class AIDecisionRecord:
    """
    Authoritative audit record of an AI-assisted recovery decision.
    """

    decision_id: uuid.UUID
    scenario_id: Optional[str]
    provider: str
    model: str
    prompt_version: str
    prompt_hash: str
    agent_version: str
    raw_proposal: Optional[AIDecisionProposal]
    proposal_policy_result: Optional[PolicyValidationResult]
    recommended_action: RecoveryActionType
    confidence: float
    reasoning_codes: list[str]
    uncertainty: str
    requires_human_review: bool
    fallback_used: bool
    fallback_reason: Optional[str]
    latency_ms: float
    input_tokens: int
    output_tokens: int
    estimated_llm_cost_minor: int  # in paise
    final_recommendation: RecoveryDecisionRecommendation
    created_at: datetime
