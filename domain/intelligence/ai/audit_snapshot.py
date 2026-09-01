"""Sanitized, durable audit snapshots for AI-assisted recovery decisions."""

from __future__ import annotations

import re
from dataclasses import asdict
from typing import Any

from domain.intelligence.ai.models import AIDecisionRecord, AIRecoveryContext
from domain.intelligence.models.action_economics import RecoveryDecisionRecommendation

AUDIT_SCHEMA_VERSION = "1"


def _sanitize_reason(value: str | None) -> str | None:
    """Keep operational fallback detail without persisting credentials."""
    if not value:
        return value
    sanitized = re.sub(
        r"(?i)(api[_-]?key|token|password|secret)\s*[=:]\s*[^\s,;]+",
        r"\1=***REDACTED***",
        value,
    )
    return sanitized[:512]


def build_decision_audit_snapshots(
    record: AIDecisionRecord,
    recommendation: RecoveryDecisionRecommendation,
) -> dict[str, Any]:
    """Build JSON-safe audit snapshots without introducing new authority."""
    proposal = record.raw_proposal.model_dump(mode="json") if record.raw_proposal else None
    policy = record.proposal_policy_result
    policy_result = {
        "merchant_id": str(recommendation.context.policy.merchant_id),
        "maximum_discount_percent": recommendation.context.policy.maximum_discount_percent,
        "maximum_interventions": recommendation.context.policy.maximum_interventions,
        "cooldown_hours": recommendation.context.policy.cooldown_hours,
        "high_value_threshold_minor": recommendation.context.policy.high_value_threshold_minor,
        "high_value_requires_approval": recommendation.context.policy.high_value_requires_approval,
        "proposed_action_permitted": policy.is_valid if policy else None,
        "violations": policy.violations if policy else [],
        "requires_human_approval": policy.requires_approval if policy else False,
        "policy_permitted_action": recommendation.policy_permitted_action.value,
        "policy_permitted_net_revenue_minor": recommendation.policy_permitted_net_revenue_minor,
    }
    candidates = [
        {
            "action_type": item.action_type.value,
            "estimated_success_probability": item.estimated_success_probability,
            "natural_recovery_probability": item.natural_recovery_probability,
            "incremental_recovery_probability": item.incremental_recovery_probability,
            "expected_gross_revenue_minor": item.expected_gross_revenue_minor,
            "expected_natural_revenue_minor": item.expected_natural_revenue_minor,
            "expected_incremental_revenue_minor": item.expected_incremental_revenue_minor,
            "intervention_cost_minor": item.intervention_cost_minor,
            "expected_net_incremental_revenue_minor": item.expected_net_incremental_revenue_minor,
            "is_policy_compliant": item.is_policy_compliant,
            "policy_violations": item.policy_violations,
            "requires_human_approval": item.requires_human_approval,
            "discount_percent_offered": item.discount_percent_offered,
        }
        for item in recommendation.candidate_evaluations
    ]
    return {
        "audit_schema_version": AUDIT_SCHEMA_VERSION,
        "context_snapshot_json": asdict(AIRecoveryContext.from_recovery_context(recommendation.context)),
        "proposal_json": proposal,
        "proposal_validation_json": {
            "structurally_valid": record.raw_proposal is not None,
            "accepted": not record.fallback_used,
            "fallback_triggered": record.fallback_used,
            "fallback_reason": _sanitize_reason(record.fallback_reason),
        },
        "policy_result_json": policy_result,
        "authorization_result_json": {
            "approval_required": bool(
                recommendation.get_evaluation(recommendation.recommended_action)
                and recommendation.get_evaluation(recommendation.recommended_action).requires_human_approval
            ),
            "decision_time_status": "PENDING_APPROVAL" if (
                recommendation.get_evaluation(recommendation.recommended_action)
                and recommendation.get_evaluation(recommendation.recommended_action).requires_human_approval
            ) else "NOT_REQUIRED",
        },
        "economic_candidates_json": candidates,
        "selection_result_json": {
            "ai_proposed_action": record.raw_proposal.recommended_action.value if record.raw_proposal else None,
            "economically_optimal_action": recommendation.economically_optimal_action.value,
            "economically_optimal_net_revenue_minor": recommendation.economically_optimal_net_revenue_minor,
            "policy_permitted_action": recommendation.policy_permitted_action.value,
            "deterministic_selected_action": recommendation.recommended_action.value,
            "selected_discount_percent": recommendation.recommended_discount_percent,
            "is_policy_override": recommendation.is_policy_override,
            "selection_source": "DETERMINISTIC_BASELINE_FALLBACK" if record.fallback_used else "POLICY_ECONOMIC_ENGINE",
        },
    }
