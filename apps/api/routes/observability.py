"""
apps/api/routes/observability.py

Read-only FastAPI endpoints for decision observability, audit inspection,
and offline simulation evaluation.

ARCHITECTURAL PRINCIPLES (Block 6, Requirement 8 & 12):
1. READ/EVALUATE ONLY: Endpoints cannot mutate payment state, issue refunds, or move funds.
2. Serves authoritative operational and economic metrics derived from DB records.
3. Explicitly flags simulation metrics as synthetic offline evaluation.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from domain.observability.service import ObservabilityService
from infrastructure.database.connection import get_db_session

router = APIRouter(prefix="/observability", tags=["Observability & Evaluation"])
_observability_service = ObservabilityService()

# In-memory store for simulation evaluation runs
_simulation_runs_cache: dict[uuid.UUID, dict[str, Any]] = {}


class SimulationEvaluateRequest(BaseModel):
    """Payload for requesting an offline simulation evaluation."""

    scenario_count: int = Field(default=100, ge=1, le=1000, description="Number of synthetic scenarios.")
    seed: int = Field(default=42, description="Random seed for reproducibility.")


@router.get("/summary")
async def get_observability_summary(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Retrieve operational decision health and aggregate economic performance."""
    summary = await _observability_service.get_observability_summary(session)
    return {
        "source_type": summary.source_type,
        "generated_at": summary.generated_at.isoformat(),
        "decision_metrics": {
            "total_decisions": summary.decision_metrics.total_decisions,
            "ai_proposals_attempted": summary.decision_metrics.ai_proposals_attempted,
            "successful_ai_proposals": summary.decision_metrics.successful_ai_proposals,
            "fallback_count": summary.decision_metrics.fallback_count,
            "fallback_rate": summary.decision_metrics.fallback_rate,
            "policy_rejection_count": summary.decision_metrics.policy_rejection_count,
            "policy_rejection_rate": summary.decision_metrics.policy_rejection_rate,
            "final_action_distribution": summary.decision_metrics.final_action_distribution,
            "ai_proposed_action_distribution": summary.decision_metrics.ai_proposed_action_distribution,
            "fallback_action_distribution": summary.decision_metrics.fallback_action_distribution,
            "execution_success_count": summary.decision_metrics.execution_success_count,
            "execution_failure_count": summary.decision_metrics.execution_failure_count,
            "human_review_required_count": summary.decision_metrics.human_review_required_count,
            "actions_proposed": summary.decision_metrics.actions_proposed,
            "actions_approved": summary.decision_metrics.actions_approved,
            "actions_executing": summary.decision_metrics.actions_executing,
            "actions_completed": summary.decision_metrics.actions_completed,
            "actions_failed": summary.decision_metrics.actions_failed,
            "actions_cancelled": summary.decision_metrics.actions_cancelled,
            "actions_expired": summary.decision_metrics.actions_expired,
            "actions_superseded": summary.decision_metrics.actions_superseded,
            "total_retries": summary.decision_metrics.total_retries,
            "pending_outbox_count": summary.decision_metrics.pending_outbox_count,
            "outbox_processing_count": summary.decision_metrics.outbox_processing_count,
            "outbox_failed_count": summary.decision_metrics.outbox_failed_count,
            "avg_latency_ms": summary.decision_metrics.avg_latency_ms,
            "p50_latency_ms": summary.decision_metrics.p50_latency_ms,
            "p95_latency_ms": summary.decision_metrics.p95_latency_ms,
            "p99_latency_ms": summary.decision_metrics.p99_latency_ms,
            "avg_input_tokens": summary.decision_metrics.avg_input_tokens,
            "avg_output_tokens": summary.decision_metrics.avg_output_tokens,
            "total_input_tokens": summary.decision_metrics.total_input_tokens,
            "total_output_tokens": summary.decision_metrics.total_output_tokens,
            "total_inference_cost_minor": summary.decision_metrics.total_inference_cost_minor,
        },
        "economic_metrics": {
            "expected_gross_recovery_minor": summary.economic_metrics.expected_gross_recovery_minor,
            "expected_natural_recovery_minor": summary.economic_metrics.expected_natural_recovery_minor,
            "expected_incremental_recovery_minor": summary.economic_metrics.expected_incremental_recovery_minor,
            "intervention_cost_minor": summary.economic_metrics.intervention_cost_minor,
            "ai_inference_cost_minor": summary.economic_metrics.ai_inference_cost_minor,
            "expected_net_incremental_revenue_minor": summary.economic_metrics.expected_net_incremental_revenue_minor,
            "realized_captured_revenue_minor": summary.economic_metrics.realized_captured_revenue_minor,
            "total_economic_value_minor": summary.economic_metrics.total_economic_value_minor,
            "avg_economic_value_minor": summary.economic_metrics.avg_economic_value_minor,
            "positive_value_decision_rate": summary.economic_metrics.positive_value_decision_rate,
            "negative_value_decision_rate": summary.economic_metrics.negative_value_decision_rate,
        },
    }


@router.get("/decisions/{decision_id}")
async def get_decision_audit(
    decision_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Retrieve full structured audit record for a single recovery decision."""
    audit = await _observability_service.get_decision_audit(decision_id, session)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision audit record {decision_id} not found.",
        )
    return _serialize_audit_detail(audit)


@router.get("/recovery/{recovery_case_id}")
async def get_recovery_case_audit(
    recovery_case_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Retrieve decision audit associated with a RecoveryCase."""
    audit = await _observability_service.get_recovery_case_audit(recovery_case_id, session)
    if audit is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decision audit record for recovery case {recovery_case_id} not found.",
        )
    return _serialize_audit_detail(audit)


@router.post("/simulation/evaluate")
async def evaluate_simulation(
    req: SimulationEvaluateRequest,
) -> dict[str, Any]:
    """Execute synthetic offline evaluation comparing AI, Baseline, and Oracle."""
    report = await _observability_service.run_simulation_evaluation(
        scenario_count=req.scenario_count,
        seed=req.seed,
    )
    res_dict = {
        "run_id": str(report.run_id),
        "scenario_count": report.scenario_count,
        "seed": report.seed,
        "duration_ms": report.duration_ms,
        "source_type": report.source_type,
        "disclaimer": report.disclaimer,
        "economic_value_capture_ratio": report.economic_value_capture_ratio,
        "baseline_value_capture_ratio": report.baseline_value_capture_ratio,
        "net_economic_lift_over_baseline_minor": report.net_economic_lift_over_baseline_minor,
        "regret": {
            "mean_regret_minor": report.regret.mean_regret_minor,
            "median_regret_minor": report.regret.median_regret_minor,
            "p90_regret_minor": report.regret.p90_regret_minor,
            "within_1_pct_rate": report.regret.within_1_pct_rate,
            "within_5_pct_rate": report.regret.within_5_pct_rate,
            "within_10_pct_rate": report.regret.within_10_pct_rate,
        },
        "exact_oracle_action_agreement_rate": report.exact_oracle_action_agreement_rate,
        "exact_baseline_action_agreement_rate": report.exact_baseline_action_agreement_rate,
        "fallback_count": report.fallback_count,
        "fallback_rate": report.fallback_rate,
        "policy_rejection_count": report.policy_rejection_count,
        "policy_rejection_rate": report.policy_rejection_rate,
        "average_ai_latency_ms": report.average_ai_latency_ms,
        "total_input_tokens": report.total_input_tokens,
        "total_output_tokens": report.total_output_tokens,
        "total_llm_inference_cost_minor": report.total_llm_inference_cost_minor,
        "calibration": {
            "natural_recovery_prob_mae": report.calibration.natural_recovery_prob_mae,
            "action_recovery_prob_mae": report.calibration.action_recovery_prob_mae,
            "brier_score": report.calibration.brier_score,
            "buckets": [
                {
                    "bucket_range": b.bucket_range,
                    "count": b.count,
                    "mean_predicted_prob": b.mean_predicted_prob,
                    "observed_positive_rate": b.observed_positive_rate,
                }
                for b in report.calibration.buckets
            ],
        },
        "completed_at": report.completed_at.isoformat(),
    }
    _simulation_runs_cache[report.run_id] = res_dict
    return res_dict


@router.get("/simulation/{run_id}")
async def get_simulation_run(run_id: uuid.UUID) -> dict[str, Any]:
    """Retrieve results of a past simulation evaluation run by run_id."""
    if run_id not in _simulation_runs_cache:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Simulation evaluation run {run_id} not found in active session cache.",
        )
    return _simulation_runs_cache[run_id]


def _serialize_audit_detail(audit: Any) -> dict[str, Any]:
    return {
        "decision_id": str(audit.decision_id),
        "scenario_id": audit.scenario_id,
        "recovery_case_id": str(audit.recovery_case_id) if audit.recovery_case_id else None,
        "payment_id": str(audit.payment_id) if audit.payment_id else None,
        "correlation_id": audit.correlation_id,
        "decision_request_id": str(audit.decision_request_id) if audit.decision_request_id else None,
        "audit_schema_version": audit.audit_schema_version,
        "created_at": audit.created_at.isoformat(),
        "provider": audit.provider,
        "model": audit.model,
        "prompt_version": audit.prompt_version,
        "observable_context": {
            "payment_id": str(audit.observable_context.payment_id),
            "amount_minor": audit.observable_context.amount_minor,
            "currency": audit.observable_context.currency,
            "payment_method": audit.observable_context.payment_method,
            "failure_code": audit.observable_context.failure_code,
            "attempt_count": audit.observable_context.attempt_count,
            "customer_segment": audit.observable_context.customer_segment,
            "customer_historical_success_rate": audit.observable_context.customer_historical_success_rate,
            "is_cooldown_active": audit.observable_context.is_cooldown_active,
            "is_business_hours": audit.observable_context.is_business_hours,
        }
        if audit.observable_context
        else None,
        "proposed_action": audit.proposed_action,
        "confidence": audit.confidence,
        "uncertainty": audit.uncertainty,
        "reasoning_codes": audit.reasoning_codes,
        "policy_approved": audit.policy_approved,
        "requires_human_review": audit.requires_human_review,
        "fallback_used": audit.fallback_used,
        "fallback_reason": audit.fallback_reason,
        "final_action": audit.final_action,
        "discount_percent_offered": audit.discount_percent_offered,
        "economic_evaluation": {
            "expected_gross_revenue_minor": audit.economic_evaluation.expected_gross_revenue_minor,
            "expected_natural_revenue_minor": audit.economic_evaluation.expected_natural_revenue_minor,
            "expected_incremental_revenue_minor": audit.economic_evaluation.expected_incremental_revenue_minor,
            "intervention_cost_minor": audit.economic_evaluation.intervention_cost_minor,
            "expected_net_incremental_revenue_minor": audit.economic_evaluation.expected_net_incremental_revenue_minor,
            "estimated_llm_cost_minor": audit.economic_evaluation.estimated_llm_cost_minor,
        }
        if audit.economic_evaluation
        else None,
        "execution_status": audit.execution_status,
        "execution_reference": audit.execution_reference,
        "execution_details": audit.execution_details,
        "latency_ms": audit.latency_ms,
        "input_tokens": audit.input_tokens,
        "output_tokens": audit.output_tokens,
        "estimated_llm_cost_minor": audit.estimated_llm_cost_minor,
        "ai_proposal": audit.ai_proposal,
        "proposal_validation": audit.proposal_validation,
        "policy_result": audit.policy_result,
        "authorization_result": audit.authorization_result,
        "economic_candidates": audit.economic_candidates,
        "selection_result": audit.selection_result,
        "recovery_action_id": str(audit.recovery_action_id) if audit.recovery_action_id else None,
        "action_idempotency_key": audit.action_idempotency_key,
        "outbox_event_id": str(audit.outbox_event_id) if audit.outbox_event_id else None,
        "outbox_status": audit.outbox_status,
        "execution_attempt": audit.execution_attempt,
        "approval": audit.approval,
        "financial_event_id": str(audit.financial_event_id) if audit.financial_event_id else None,
        "payment_status": audit.payment_status,
    }
