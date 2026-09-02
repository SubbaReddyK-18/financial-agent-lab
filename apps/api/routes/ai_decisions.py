"""
apps/api/routes/ai_decisions.py

API endpoints for AI-assisted recovery decisions and comparative AI benchmarks.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.middleware.correlation import get_correlation_id
from domain.intelligence.ai.audit_snapshot import build_decision_audit_snapshots
from domain.intelligence.ai.evaluator import AIBenchmarkRunner, AIEvaluationSummary
from domain.intelligence.ai.models import AIRecoveryContext
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType
from infrastructure.database.connection import get_db_session
from infrastructure.database.orm.ai import AIDecisionRecordORM

router = APIRouter(prefix="/ai", tags=["AI Recovery Agent"])


class SingleDecisionRequest(BaseModel):
    amount_minor: int = Field(..., gt=0, description="Payment amount in paise (minor units)")
    currency: str = Field(default="INR")
    payment_method: PaymentMethod = Field(default=PaymentMethod.UPI)
    failure_code: str = Field(default="GATEWAY_TIMEOUT")
    attempt_count: int = Field(default=1, ge=1)
    customer_historical_success_rate: float = Field(default=0.85, ge=0.0, le=1.0)
    customer_segment: str = Field(default="RETURNING")
    scenario_id: Optional[str] = None


class DecisionResponse(BaseModel):
    decision_id: uuid.UUID
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
    estimated_llm_cost_minor: int
    expected_net_incremental_revenue_minor: int


class AIBenchmarkRequest(BaseModel):
    scenario_count: int = Field(default=100, ge=1, le=5000)
    seed: int = Field(default=42)


class AIBenchmarkResponse(BaseModel):
    run_id: uuid.UUID
    scenario_count: int
    seed: int
    duration_ms: float
    ai_oracle_agreement_rate: float
    ai_baseline_agreement_rate: float
    fallback_rate: float
    fallback_count: int
    economic_value_capture_ratio: float
    baseline_value_capture_ratio: float
    ai_vs_baseline_net_lift_minor: int
    total_input_tokens: int
    total_output_tokens: int
    total_llm_inference_cost_minor: int
    net_ai_economic_value_minor: int
    average_ai_latency_ms: float


@router.post(
    "/decide",
    status_code=status.HTTP_200_OK,
    response_model=DecisionResponse,
    summary="Evaluate a failed payment using the AI Decision Agent with deterministic fallback.",
)
async def evaluate_single_decision(
    req: SingleDecisionRequest,
    db: AsyncSession = Depends(get_db_session),
) -> Any:
    # Construct domain context
    merchant_id = uuid.uuid4()
    policy = MerchantRecoveryPolicy(
        merchant_id=merchant_id,
        maximum_discount_percent=10,
        maximum_interventions=3,
        cooldown_hours=2,
        high_value_threshold_minor=10000_00,
    )
    context = RecoveryContext(
        payment=PaymentFailureDetails(
            payment_id=uuid.uuid4(),
            amount_minor=req.amount_minor,
            currency=req.currency,
            payment_method=req.payment_method,
            attempt_count=req.attempt_count,
            failure_code=req.failure_code,
        ),
        customer=CustomerProfile(
            customer_id=uuid.uuid4(),
            historical_success_rate=req.customer_historical_success_rate,
            customer_segment=req.customer_segment,
        ),
        policy=policy,
        completed_interventions=0,
    )

    provider = AIDecisionProvider()
    rec = await provider.evaluate_decision_async(context, scenario_id=req.scenario_id)
    audit = provider.last_decision_record

    if audit:
        snapshots = build_decision_audit_snapshots(audit, rec)
        # Persist audit record to database
        orm_record = AIDecisionRecordORM(
            id=audit.decision_id,
            scenario_id=audit.scenario_id,
            correlation_id=get_correlation_id(),
            audit_schema_version=snapshots["audit_schema_version"],
            provider=audit.provider,
            model=audit.model,
            prompt_version=audit.prompt_version,
            prompt_hash=audit.prompt_hash,
            agent_version=audit.agent_version,
            recommended_action=audit.recommended_action.value,
            confidence=audit.confidence,
            reasoning_codes=audit.reasoning_codes,
            uncertainty=audit.uncertainty,
            requires_human_review=audit.requires_human_review,
            fallback_used=audit.fallback_used,
            fallback_reason=audit.fallback_reason,
            latency_ms=audit.latency_ms,
            input_tokens=audit.input_tokens,
            output_tokens=audit.output_tokens,
            estimated_llm_cost_minor=audit.estimated_llm_cost_minor,
            final_action=audit.recommended_action.value,
            expected_net_incremental_revenue_minor=rec.expected_net_incremental_revenue_minor,
            context_snapshot_json=snapshots["context_snapshot_json"],
            proposal_json=snapshots["proposal_json"],
            proposal_validation_json=snapshots["proposal_validation_json"],
            policy_result_json=snapshots["policy_result_json"],
            authorization_result_json=snapshots["authorization_result_json"],
            economic_candidates_json=snapshots["economic_candidates_json"],
            selection_result_json=snapshots["selection_result_json"],
            created_at=audit.created_at,
        )
        db.add(orm_record)
        await db.flush()

        return DecisionResponse(
            decision_id=audit.decision_id,
            recommended_action=audit.recommended_action,
            confidence=audit.confidence,
            reasoning_codes=audit.reasoning_codes,
            uncertainty=audit.uncertainty,
            requires_human_review=audit.requires_human_review,
            fallback_used=audit.fallback_used,
            fallback_reason=audit.fallback_reason,
            latency_ms=audit.latency_ms,
            input_tokens=audit.input_tokens,
            output_tokens=audit.output_tokens,
            estimated_llm_cost_minor=audit.estimated_llm_cost_minor,
            expected_net_incremental_revenue_minor=rec.expected_net_incremental_revenue_minor,
        )

    raise HTTPException(status_code=500, detail="Failed to produce decision record.")


@router.post(
    "/benchmark",
    status_code=status.HTTP_200_OK,
    response_model=AIBenchmarkResponse,
    summary="Run comparative benchmark evaluating AI vs Baseline vs Oracle over N scenarios.",
)
async def run_ai_benchmark(
    req: AIBenchmarkRequest,
) -> Any:
    provider = AIDecisionProvider()
    runner = AIBenchmarkRunner(seed=req.seed)
    summary: AIEvaluationSummary = await runner.run_benchmark_async(
        ai_provider=provider,
        scenario_count=req.scenario_count,
    )

    return AIBenchmarkResponse(
        run_id=summary.run_id,
        scenario_count=summary.scenario_count,
        seed=summary.seed,
        duration_ms=summary.duration_ms,
        ai_oracle_agreement_rate=summary.ai_oracle_agreement_rate,
        ai_baseline_agreement_rate=summary.ai_baseline_agreement_rate,
        fallback_rate=summary.fallback_rate,
        fallback_count=summary.fallback_count,
        economic_value_capture_ratio=summary.economic_value_capture_ratio,
        baseline_value_capture_ratio=summary.baseline_value_capture_ratio,
        ai_vs_baseline_net_lift_minor=summary.ai_vs_baseline_net_lift_minor,
        total_input_tokens=summary.total_input_tokens,
        total_output_tokens=summary.total_output_tokens,
        total_llm_inference_cost_minor=summary.total_llm_inference_cost_minor,
        net_ai_economic_value_minor=summary.net_ai_economic_value_minor,
        average_ai_latency_ms=summary.average_ai_latency_ms,
    )
