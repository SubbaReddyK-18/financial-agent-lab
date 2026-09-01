"""
domain/observability/service.py

Observability and evaluation query service.

ARCHITECTURAL PRINCIPLES (Block 6):
1. READ/EVALUATE ONLY: Does not mutate payment/order state, cannot move money.
2. Derives operational and economic metrics directly from authoritative database records.
3. Performs clean joins and bulk aggregations to avoid N+1 query explosions.
4. Preserves integer minor units (paise) for all monetary metrics.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.intelligence.ai.provider import AIDecisionProvider
from domain.observability.audit_view import (
    DecisionAuditDetail,
    EconomicValuationSummary,
    ObservableContextSummary,
)
from domain.observability.metrics import (
    DecisionMetricsSummary,
    EconomicMetricsSummary,
    ObservabilitySummary,
    compute_percentile,
)
from domain.observability.simulation_evaluator import (
    AdvancedSimulationEvaluator,
    SimulationEvaluationReport,
)
from domain.shared.enums import PaymentStatus, RecoveryActionType
from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.approval import RecoveryActionApprovalORM
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.payment import PaymentORM
from infrastructure.database.orm.recovery import RecoveryActionORM, RecoveryCaseORM
from infrastructure.database.orm.outbox import RecoveryOutboxEventORM

logger = logging.getLogger("domain.observability.service")


class ObservabilityService:
    """
    Query service for recovery decision metrics, audit traces, and simulation evaluations.
    """

    async def get_decision_audit(
        self,
        decision_id: uuid.UUID,
        session: AsyncSession,
    ) -> Optional[DecisionAuditDetail]:
        """Retrieve full structured decision audit detail by decision ID."""
        audit = await session.scalar(
            select(AIDecisionRecordORM).where(AIDecisionRecordORM.id == decision_id)
        )
        if audit is None:
            return None

        return await self._build_audit_detail(audit, session)

    async def get_recovery_case_audit(
        self,
        case_id: uuid.UUID,
        session: AsyncSession,
    ) -> Optional[DecisionAuditDetail]:
        """Retrieve decision audit by RecoveryCase ID."""
        audit = await session.scalar(
            select(AIDecisionRecordORM)
            .where(AIDecisionRecordORM.recovery_case_id == case_id)
            .order_by(AIDecisionRecordORM.created_at.desc())
        )
        # Compatibility for pre-Block-9 audit rows.
        if audit is None:
            audit = await session.scalar(
                select(AIDecisionRecordORM)
                .where(AIDecisionRecordORM.scenario_id == str(case_id))
                .order_by(AIDecisionRecordORM.created_at.desc())
            )
        if audit is None:
            return None

        return await self._build_audit_detail(audit, session)

    async def get_payment_audit(
        self,
        payment_id: uuid.UUID,
        session: AsyncSession,
    ) -> Optional[DecisionAuditDetail]:
        """Retrieve decision audit for a specific payment ID."""
        case = await session.scalar(
            select(RecoveryCaseORM)
            .where(RecoveryCaseORM.payment_id == payment_id)
            .order_by(RecoveryCaseORM.opened_at.desc())
        )
        if case is None:
            return None

        return await self.get_recovery_case_audit(case.id, session)

    async def _build_audit_detail(
        self,
        audit: AIDecisionRecordORM,
        session: AsyncSession,
    ) -> DecisionAuditDetail:
        """Helper to reconstruct audit detail from related database entities."""
        # Find related recovery case
        case: Optional[RecoveryCaseORM] = None
        try:
            case_uuid = getattr(audit, "recovery_case_id", None) or uuid.UUID(audit.scenario_id)
            case = await session.scalar(
                select(RecoveryCaseORM).where(RecoveryCaseORM.id == case_uuid)
            )
        except ValueError:
            pass

        # Find latest associated recovery action, payment, and payment attempt
        action: Optional[RecoveryActionORM] = None
        payment: Optional[PaymentORM] = None
        attempt: Optional[Any] = None
        if case:
            action_id = getattr(audit, "recovery_action_id", None)
            action = await session.scalar(
                select(RecoveryActionORM).where(RecoveryActionORM.id == action_id)
            ) if action_id else await session.scalar(
                select(RecoveryActionORM)
                .where(RecoveryActionORM.recovery_case_id == case.id)
                .order_by(RecoveryActionORM.created_at.desc())
            )
            payment = await session.scalar(
                select(PaymentORM).where(PaymentORM.id == case.payment_id)
            )
            if payment:
                from infrastructure.database.orm.payment import PaymentAttemptORM
                attempt = await session.scalar(
                    select(PaymentAttemptORM)
                    .where(PaymentAttemptORM.payment_id == payment.id)
                    .order_by(PaymentAttemptORM.attempt_number.desc())
                )

        # Linked execution and approval records are read from their
        # authoritative tables; snapshots remain evidence, not state.
        outbox = approval = None
        if action and getattr(audit, "audit_schema_version", None):
            outbox = await session.scalar(
                select(RecoveryOutboxEventORM).where(
                    RecoveryOutboxEventORM.recovery_action_id == action.id
                )
            )
            approval = await session.scalar(
                select(RecoveryActionApprovalORM).where(
                    RecoveryActionApprovalORM.recovery_action_id == action.id
                )
            )

        # Context summary
        context_summary: Optional[ObservableContextSummary] = None
        if payment:
            context_summary = ObservableContextSummary(
                payment_id=payment.id,
                amount_minor=payment.amount_minor,
                currency=payment.currency,
                payment_method=payment.payment_method or "UPI",
                failure_code=(attempt.failure_code if attempt and attempt.failure_code else "PAYMENT_FAILURE"),
                attempt_count=(attempt.attempt_number if attempt else 1),
                customer_segment="VIP" if payment.amount_minor > 10000_00 else "RETURNING",
                customer_historical_success_rate=0.85,
                is_cooldown_active=False,
                is_business_hours=True,
            )

        # Economic breakdown
        economic_summary: Optional[EconomicValuationSummary] = None
        if action and action.metadata_json and "economic_evaluation" in action.metadata_json:
            econ = action.metadata_json["economic_evaluation"]
            economic_summary = EconomicValuationSummary(
                expected_gross_revenue_minor=econ.get("expected_gross_revenue_minor", 0),
                expected_natural_revenue_minor=econ.get("expected_natural_revenue_minor", 0),
                expected_incremental_revenue_minor=econ.get("expected_incremental_revenue_minor", 0),
                intervention_cost_minor=econ.get("intervention_cost_minor", 0),
                expected_net_incremental_revenue_minor=econ.get("expected_net_incremental_revenue_minor", 0),
                estimated_llm_cost_minor=audit.estimated_llm_cost_minor,
            )

        # Execution metadata
        execution_status = action.status if action else "COMPLETED"
        execution_reference = (
            action.metadata_json.get("execution_reference")
            if action and action.metadata_json
            else None
        )
        execution_details = (
            action.metadata_json.get("execution_details", {})
            if action and action.metadata_json
            else {}
        )

        return DecisionAuditDetail(
            decision_id=audit.id,
            scenario_id=audit.scenario_id,
            recovery_case_id=case.id if case else None,
            payment_id=payment.id if payment else None,
            correlation_id=getattr(audit, "correlation_id", None),
            created_at=audit.created_at,
            provider=audit.provider,
            model=audit.model,
            prompt_version=audit.prompt_version,
            observable_context=context_summary,
            proposed_action=audit.recommended_action,
            confidence=audit.confidence,
            uncertainty=audit.uncertainty or "LOW",
            reasoning_codes=audit.reasoning_codes or [],
            policy_approved=not (audit.fallback_used and "policy" in str(audit.fallback_reason).lower()),
            requires_human_review=audit.requires_human_review,
            fallback_used=audit.fallback_used,
            fallback_reason=audit.fallback_reason,
            final_action=audit.final_action,
            discount_percent_offered=action.discount_percent_offered if action else 0,
            economic_evaluation=economic_summary,
            execution_status=execution_status,
            execution_reference=execution_reference,
            execution_details=execution_details,
            latency_ms=audit.latency_ms,
            input_tokens=audit.input_tokens,
            output_tokens=audit.output_tokens,
            estimated_llm_cost_minor=audit.estimated_llm_cost_minor,
            decision_request_id=getattr(audit, "decision_request_id", None),
            audit_schema_version=getattr(audit, "audit_schema_version", None),
            ai_proposal=getattr(audit, "proposal_json", None),
            proposal_validation=getattr(audit, "proposal_validation_json", {}) or {},
            policy_result=getattr(audit, "policy_result_json", {}) or {},
            authorization_result=getattr(audit, "authorization_result_json", {}) or {},
            economic_candidates=getattr(audit, "economic_candidates_json", []) or [],
            selection_result=getattr(audit, "selection_result_json", {}) or {},
            recovery_action_id=action.id if action else getattr(audit, "recovery_action_id", None),
            action_idempotency_key=action.idempotency_key if action else None,
            outbox_event_id=outbox.id if outbox else None,
            outbox_status=outbox.status if outbox else None,
            execution_attempt=action.execution_attempt if action else None,
            approval=(
                {
                    "approval_id": str(approval.id), "decision": approval.decision,
                    "actor_id": approval.actor_id, "reason": approval.reason,
                    "correlation_id": approval.correlation_id,
                    "created_at": approval.created_at.isoformat(),
                } if approval else None
            ),
            financial_event_id=getattr(audit, "financial_event_id", None),
            payment_status=payment.status if payment else None,
        )

    async def get_observability_summary(
        self,
        session: AsyncSession,
    ) -> ObservabilitySummary:
        """
        Aggregate operational decision health and economic performance across all live records.
        """
        # 1. Fetch all decision records
        audit_records = (
            await session.scalars(select(AIDecisionRecordORM).order_by(AIDecisionRecordORM.created_at.desc()))
        ).all()

        total_decisions = len(audit_records)
        if total_decisions == 0:
            return ObservabilitySummary(
                decision_metrics=DecisionMetricsSummary(),
                economic_metrics=EconomicMetricsSummary(),
                source_type="LIVE_PRODUCTION",
            )

        ai_attempted = total_decisions
        successful_ai = sum(1 for a in audit_records if not a.fallback_used)
        fallback_count = sum(1 for a in audit_records if a.fallback_used)
        fallback_rate = round(fallback_count / total_decisions, 4)

        policy_rejections = sum(
            1 for a in audit_records
            if a.fallback_used and "policy" in str(a.fallback_reason).lower()
        )
        policy_rejection_rate = round(policy_rejections / total_decisions, 4)

        final_dist: dict[str, int] = {}
        proposed_dist: dict[str, int] = {}
        fallback_dist: dict[str, int] = {}
        human_review_count = 0
        latencies: list[float] = []
        total_in_tokens = 0
        total_out_tokens = 0
        total_llm_cost = 0
        total_expected_net_minor = 0
        positive_val_count = 0
        negative_val_count = 0

        for a in audit_records:
            final_dist[a.final_action] = final_dist.get(a.final_action, 0) + 1
            proposed_dist[a.recommended_action] = proposed_dist.get(a.recommended_action, 0) + 1
            if a.fallback_used:
                fallback_dist[a.final_action] = fallback_dist.get(a.final_action, 0) + 1

            if a.requires_human_review:
                human_review_count += 1

            latencies.append(a.latency_ms)
            total_in_tokens += a.input_tokens
            total_out_tokens += a.output_tokens
            total_llm_cost += a.estimated_llm_cost_minor

            net_val = a.expected_net_incremental_revenue_minor
            total_expected_net_minor += net_val
            if net_val > 0:
                positive_val_count += 1
            elif net_val < 0:
                negative_val_count += 1

        avg_latency = round(sum(latencies) / len(latencies), 2)
        p50_latency = compute_percentile(latencies, 0.50)
        p95_latency = compute_percentile(latencies, 0.95)
        p99_latency = compute_percentile(latencies, 0.99)

        # 2. Fetch actions to verify execution health & control plane stats
        actions = (await session.scalars(select(RecoveryActionORM))).all()
        exec_success = sum(1 for act in actions if act.status == "COMPLETED")
        exec_fail = sum(1 for act in actions if act.status == "FAILED")
        actions_prop = sum(1 for act in actions if act.status == "PROPOSED")
        actions_appr = sum(1 for act in actions if act.status == "APPROVED")
        actions_exec = sum(1 for act in actions if act.status == "EXECUTING")
        actions_canc = sum(1 for act in actions if act.status == "CANCELLED")
        actions_exp = sum(1 for act in actions if act.status == "EXPIRED")
        actions_sup = sum(1 for act in actions if act.status == "SUPERSEDED")
        total_retries_cnt = sum(getattr(act, "retry_count", 0) for act in actions)

        # Outbox event counts
        from infrastructure.database.orm.outbox import RecoveryOutboxEventORM
        pending_outbox_cnt = (
            await session.scalar(
                select(func.count())
                .select_from(RecoveryOutboxEventORM)
                .where(RecoveryOutboxEventORM.status == "PENDING")
            )
        ) or 0
        processing_outbox_cnt = (
            await session.scalar(
                select(func.count())
                .select_from(RecoveryOutboxEventORM)
                .where(RecoveryOutboxEventORM.status == "PROCESSING")
            )
        ) or 0
        failed_outbox_cnt = (
            await session.scalar(
                select(func.count())
                .select_from(RecoveryOutboxEventORM)
                .where(RecoveryOutboxEventORM.status == "FAILED")
            )
        ) or 0

        # 3. Sum economic aggregates from actions metadata
        gross_recovery = 0
        natural_recovery = 0
        incremental_recovery = 0
        intervention_cost = 0

        for act in actions:
            if act.metadata_json and "economic_evaluation" in act.metadata_json:
                econ = act.metadata_json["economic_evaluation"]
                gross_recovery += econ.get("expected_gross_revenue_minor", 0)
                natural_recovery += econ.get("expected_natural_revenue_minor", 0)
                incremental_recovery += econ.get("expected_incremental_revenue_minor", 0)
                intervention_cost += econ.get("intervention_cost_minor", 0)

        # 4. Realized revenue from captured payments related to recovery cases
        realized_revenue = (
            await session.scalar(
                select(func.coalesce(func.sum(PaymentORM.amount_minor), 0))
                .join(RecoveryCaseORM, RecoveryCaseORM.payment_id == PaymentORM.id)
                .where(PaymentORM.status == PaymentStatus.CAPTURED.value)
            )
        ) or 0

        decision_metrics = DecisionMetricsSummary(
            total_decisions=total_decisions,
            ai_proposals_attempted=ai_attempted,
            successful_ai_proposals=successful_ai,
            fallback_count=fallback_count,
            fallback_rate=fallback_rate,
            policy_rejection_count=policy_rejections,
            policy_rejection_rate=policy_rejection_rate,
            final_action_distribution=final_dist,
            ai_proposed_action_distribution=proposed_dist,
            fallback_action_distribution=fallback_dist,
            execution_success_count=exec_success,
            execution_failure_count=exec_fail,
            human_review_required_count=human_review_count,
            actions_proposed=actions_prop,
            actions_approved=actions_appr,
            actions_executing=actions_exec,
            actions_completed=exec_success,
            actions_failed=exec_fail,
            actions_cancelled=actions_canc,
            actions_expired=actions_exp,
            actions_superseded=actions_sup,
            total_retries=total_retries_cnt,
            pending_outbox_count=pending_outbox_cnt,
            outbox_processing_count=processing_outbox_cnt,
            outbox_failed_count=failed_outbox_cnt,
            avg_latency_ms=avg_latency,
            p50_latency_ms=p50_latency,
            p95_latency_ms=p95_latency,
            p99_latency_ms=p99_latency,
            avg_input_tokens=round(total_in_tokens / total_decisions, 1),
            avg_output_tokens=round(total_out_tokens / total_decisions, 1),
            total_input_tokens=total_in_tokens,
            total_output_tokens=total_out_tokens,
            total_inference_cost_minor=total_llm_cost,
        )

        economic_metrics = EconomicMetricsSummary(
            expected_gross_recovery_minor=gross_recovery,
            expected_natural_recovery_minor=natural_recovery,
            expected_incremental_recovery_minor=incremental_recovery,
            intervention_cost_minor=intervention_cost,
            ai_inference_cost_minor=total_llm_cost,
            expected_net_incremental_revenue_minor=total_expected_net_minor,
            realized_captured_revenue_minor=int(realized_revenue),
            total_economic_value_minor=total_expected_net_minor - total_llm_cost,
            avg_economic_value_minor=round((total_expected_net_minor - total_llm_cost) / total_decisions),
            positive_value_decision_rate=round(positive_val_count / total_decisions, 4),
            negative_value_decision_rate=round(negative_val_count / total_decisions, 4),
        )

        return ObservabilitySummary(
            decision_metrics=decision_metrics,
            economic_metrics=economic_metrics,
            source_type="LIVE_PRODUCTION",
        )

    async def run_simulation_evaluation(
        self,
        scenario_count: int = 100,
        seed: int = 42,
        ai_provider: Optional[AIDecisionProvider] = None,
    ) -> SimulationEvaluationReport:
        """Execute offline simulation evaluation with probability calibration."""
        provider = ai_provider or AIDecisionProvider()
        evaluator = AdvancedSimulationEvaluator(seed=seed)
        return await evaluator.evaluate_async(ai_provider=provider, scenario_count=scenario_count)
