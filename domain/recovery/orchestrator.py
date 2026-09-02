"""
domain/recovery/orchestrator.py

RecoveryDecisionOrchestrator coordinates end-to-end recovery decisioning and
test-mode execution under strict deterministic controls.

ARCHITECTURAL PRINCIPLES (Block 5, Requirements 1-10):
1. AI proposes; deterministic systems calculate, validate, and control.
2. The orchestrator never allows AI to mutate payment/order state, move funds, or capture payments.
3. Every proposal is checked against the deterministic policy gate.
4. Failures, timeouts, 429s, or malformed responses gracefully use deterministic baseline fallback.
5. Idempotent processing prevents duplicate action execution on closed/stale cases.
6. Emits append-only financial events and persists full audit records to PostgreSQL.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.intelligence.ai.audit_snapshot import build_decision_audit_snapshots
from domain.intelligence.ai.models import AIDecisionRecord
from domain.intelligence.ai.provider import AIDecisionProvider
from domain.intelligence.models.action_economics import RecoveryDecisionRecommendation
from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.policies.validator import validate_action_against_policy
from domain.recovery.control_plane import RecoveryActionControlPlane
from domain.recovery.execution import ActionExecutionResult, get_action_executor
from domain.shared.enums import (
    AggregateType,
    PaymentMethod,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from infrastructure.database.orm.ai import AIDecisionRecordORM
from infrastructure.database.orm.customer import CustomerORM
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.merchant import MerchantORM
from infrastructure.database.orm.payment import OrderORM, PaymentAttemptORM, PaymentORM
from infrastructure.database.orm.recovery import (
    MerchantRecoveryPolicyORM,
    RecoveryActionORM,
    RecoveryCaseORM,
)

logger = logging.getLogger("domain.recovery.orchestrator")


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class OrchestrationResult:
    """Immutable outcome of an orchestration run."""

    success: bool
    recovery_case_id: uuid.UUID
    payment_id: uuid.UUID
    case_status: str
    decision: Optional[RecoveryDecisionRecommendation] = None
    action_id: Optional[uuid.UUID] = None
    action_type: Optional[RecoveryActionType] = None
    action_status: Optional[str] = None
    execution_result: Optional[ActionExecutionResult] = None
    fallback_used: bool = False
    fallback_reason: Optional[str] = None
    is_idempotent: bool = False
    error_message: Optional[str] = None
    correlation_id: Optional[str] = None


class RecoveryDecisionOrchestrator:
    """
    Coordinates RecoveryCase decisioning, deterministic policy gate validation,
    economic valuation, test-mode execution, and audit trail persistence.
    """

    def __init__(
        self,
        provider: Optional[AIDecisionProvider] = None,
        control_plane: Optional[RecoveryActionControlPlane] = None,
    ):
        self._provider = provider or AIDecisionProvider()
        self._control_plane = control_plane or RecoveryActionControlPlane()

    async def orchestrate_case(
        self,
        case_id: uuid.UUID,
        session: AsyncSession,
        correlation_id: Optional[str] = None,
        now: Optional[datetime] = None,
        decision_request_id: Optional[uuid.UUID] = None,
    ) -> OrchestrationResult:
        """
        Execute full recovery decisioning pipeline for a specific RecoveryCase.
        """
        now = now or _utcnow()

        # ------------------------------------------------------------------
        # Step 1: Idempotency & Concurrency-Safe State Check (Row Locking)
        # ------------------------------------------------------------------
        case_orm = await session.scalar(
            select(RecoveryCaseORM)
            .where(RecoveryCaseORM.id == case_id)
            .with_for_update()
        )
        if case_orm is None:
            raise ValueError(f"Recovery case {case_id} not found.")

        # Stale/Closed/Terminal Case Protection
        if case_orm.status in (
            RecoveryCaseStatus.CLOSED.value,
            RecoveryCaseStatus.RECOVERED.value,
            RecoveryCaseStatus.IRRECOVERABLE.value,
        ):
            logger.info("Recovery case %s is already terminal (%s). Skipping action.", case_id, case_orm.status)
            return OrchestrationResult(
                success=True,
                recovery_case_id=case_id,
                payment_id=case_orm.payment_id,
                case_status=case_orm.status,
                is_idempotent=True,
                correlation_id=correlation_id,
            )

        # Check for active/executing actions to prevent duplicate in-flight executions
        action_scalars = await session.scalars(
            select(RecoveryActionORM)
            .where(RecoveryActionORM.recovery_case_id == case_id)
            .order_by(RecoveryActionORM.created_at.desc())
        )
        existing_actions = action_scalars.all()

        executing_action = next((a for a in existing_actions if a.status == "EXECUTING"), None)
        if executing_action is not None:
            logger.info("Recovery case %s already has an active executing action %s.", case_id, executing_action.id)
            return OrchestrationResult(
                success=True,
                recovery_case_id=case_id,
                payment_id=case_orm.payment_id,
                case_status=case_orm.status,
                action_id=executing_action.id,
                action_type=RecoveryActionType(executing_action.action_type),
                action_status=executing_action.status,
                is_idempotent=True,
                correlation_id=correlation_id,
            )

        # ------------------------------------------------------------------
        # Step 2: Assemble RecoveryContext from DB
        # ------------------------------------------------------------------
        payment_orm = await session.scalar(
            select(PaymentORM).where(PaymentORM.id == case_orm.payment_id)
        )
        customer_orm = await session.scalar(
            select(CustomerORM).where(CustomerORM.id == case_orm.customer_id)
        )
        policy_orm = await session.scalar(
            select(MerchantRecoveryPolicyORM).where(
                MerchantRecoveryPolicyORM.merchant_id == case_orm.merchant_id
            )
        )

        if payment_orm is None or customer_orm is None:
            raise ValueError(f"Corrupted recovery case {case_id}: missing payment or customer record.")

        # Default policy if merchant has no explicit policy configured
        if policy_orm is None:
            policy = MerchantRecoveryPolicy(
                merchant_id=case_orm.merchant_id,
                maximum_discount_percent=0,
                maximum_interventions=3,
                cooldown_hours=24,
            )
        else:
            policy = MerchantRecoveryPolicy(
                merchant_id=policy_orm.merchant_id,
                maximum_discount_percent=policy_orm.maximum_discount_percent,
                maximum_interventions=policy_orm.maximum_interventions,
                cooldown_hours=policy_orm.cooldown_hours,
                high_value_threshold_minor=policy_orm.high_value_threshold_minor,
                high_value_requires_approval=policy_orm.high_value_requires_approval,
                low_confidence_requires_review=policy_orm.low_confidence_requires_review,
            )

        # Query latest payment attempt for failure metadata
        latest_attempt = await session.scalar(
            select(PaymentAttemptORM)
            .where(PaymentAttemptORM.payment_id == payment_orm.id)
            .order_by(PaymentAttemptORM.attempt_number.desc())
        )

        failure_code = latest_attempt.failure_code if latest_attempt else "GENERIC_DECLINE"
        failure_reason = latest_attempt.failure_reason if latest_attempt else "Payment failure"
        attempt_count = latest_attempt.attempt_number if latest_attempt else 1

        # Count completed interventions (excluding WAIT)
        completed_interventions = sum(
            1 for a in existing_actions
            if a.status == "COMPLETED" and a.action_type != RecoveryActionType.WAIT.value
        )
        last_completed_action = next(
            (a for a in existing_actions if a.status == "COMPLETED"), None
        )
        last_action_at = last_completed_action.executed_at if last_completed_action else None

        payment_method_enum = (
            PaymentMethod(payment_orm.payment_method)
            if payment_orm.payment_method and payment_orm.payment_method in PaymentMethod._value2member_map_
            else PaymentMethod.UPI
        )

        # Compute customer history dynamically from transactional records
        past_payments_scalars = await session.scalars(
            select(PaymentORM.status).where(PaymentORM.customer_id == customer_orm.id)
        )
        past_payments = past_payments_scalars.all()
        hist_count = len(past_payments)
        success_count = sum(1 for s in past_payments if s == PaymentStatus.CAPTURED.value)
        hist_success_rate = round(success_count / hist_count, 4) if hist_count > 0 else 0.85
        hist_fail_rate = round(1.0 - hist_success_rate, 4)

        prior_cases_scalars = await session.scalars(
            select(RecoveryCaseORM.id).where(RecoveryCaseORM.customer_id == customer_orm.id)
        )
        prior_cases = prior_cases_scalars.all()
        prior_interventions_count = 0
        if prior_cases:
            action_scalars = await session.scalars(
                select(RecoveryActionORM.id).where(
                    RecoveryActionORM.recovery_case_id.in_(prior_cases),
                    RecoveryActionORM.status == "COMPLETED",
                    RecoveryActionORM.action_type != RecoveryActionType.WAIT.value,
                )
            )
            prior_interventions_count = len(action_scalars.all())

        customer_profile = CustomerProfile(
            customer_id=customer_orm.id,
            historical_payment_count=max(hist_count, 1),
            historical_success_rate=hist_success_rate,
            historical_failure_rate=hist_fail_rate,
            prior_interventions_count=prior_interventions_count,
            customer_segment="VIP" if payment_orm.amount_minor > 10000_00 else "RETURNING",
        )

        recovery_context = RecoveryContext(
            payment=PaymentFailureDetails(
                payment_id=payment_orm.id,
                amount_minor=payment_orm.amount_minor,
                currency=payment_orm.currency,
                payment_method=payment_method_enum,
                attempt_count=attempt_count,
                failure_code=failure_code or "GENERIC_DECLINE",
                failure_reason=failure_reason,
                failed_at=payment_orm.created_at,
            ),
            customer=customer_profile,
            policy=policy,
            completed_interventions=completed_interventions,
            last_action_at=last_action_at,
            temporal=TemporalContext(
                current_time=now,
                hour_of_day=now.hour,
                day_of_week=now.weekday(),
                is_cooldown_active=(
                    last_action_at is not None
                    and (now - last_action_at).total_seconds() < policy.cooldown_hours * 3600
                ),
            ),
        )

        # ------------------------------------------------------------------
        # Step 3: AI / Fallback Decision Evaluation
        # ------------------------------------------------------------------
        rec: RecoveryDecisionRecommendation = await self._provider.evaluate_decision_async(
            context=recovery_context,
            scenario_id=str(case_id),
        )
        audit_record = self._provider.last_decision_record
        fallback_used = audit_record.fallback_used if audit_record else False
        fallback_reason = audit_record.fallback_reason if audit_record else None

        # ------------------------------------------------------------------
        # Step 4: Create RecoveryAction & Transactional Outbox Record
        # ------------------------------------------------------------------
        chosen_eval = rec.get_evaluation(rec.recommended_action)
        eval_dict = (
            {
                "expected_gross_revenue_minor": chosen_eval.expected_gross_revenue_minor,
                "expected_natural_revenue_minor": chosen_eval.expected_natural_revenue_minor,
                "expected_incremental_revenue_minor": chosen_eval.expected_incremental_revenue_minor,
                "intervention_cost_minor": chosen_eval.intervention_cost_minor,
                "expected_net_incremental_revenue_minor": chosen_eval.expected_net_incremental_revenue_minor,
                "requires_human_approval": chosen_eval.requires_human_approval,
            }
            if chosen_eval
            else {}
        )

        action_orm, outbox_event = await self._control_plane.create_approved_action_with_outbox(
            case=case_orm,
            action_type=rec.recommended_action,
            discount_percent=rec.recommended_discount_percent,
            session=session,
            decision_id=rec.decision_id,
            economic_metadata=eval_dict,
            correlation_id=correlation_id,
            now=now,
            requires_approval=chosen_eval.requires_human_approval if chosen_eval else False,
        )
        action_id = action_orm.id

        # Dispatch is exclusively performed after commit by the outbox worker.
        exec_result: Optional[ActionExecutionResult] = None

        # ------------------------------------------------------------------
        # Step 6: Case State Mutation & Financial Event Emission
        # ------------------------------------------------------------------
        if case_orm.status == RecoveryCaseStatus.OPEN.value and rec.recommended_action != RecoveryActionType.WAIT:
            case_orm.status = RecoveryCaseStatus.IN_PROGRESS.value

        # Emit append-only financial event
        fin_event = FinancialEventORM(
            id=uuid.uuid4(),
            event_type=f"RECOVERY_ACTION_{action_orm.status}",
            aggregate_type=AggregateType.RECOVERY_ACTION.value,
            aggregate_id=str(action_id),
            occurred_at=now,
            payload={
                "schema_version": "1",
                "recovery_case_id": str(case_id),
                "payment_id": str(payment_orm.id),
                "action_type": rec.recommended_action.value,
                "discount_percent": rec.recommended_discount_percent,
                "action_status": action_orm.status,
                "fallback_used": fallback_used,
                "expected_net_revenue_minor": rec.expected_net_incremental_revenue_minor,
            },
            correlation_id=correlation_id,
        )
        session.add(fin_event)
        await session.flush()

        # ------------------------------------------------------------------
        # Step 7: Persist AI Decision Audit Record
        # ------------------------------------------------------------------
        if audit_record:
            snapshots = build_decision_audit_snapshots(audit_record, rec)
            orm_audit = AIDecisionRecordORM(
                id=audit_record.decision_id,
                scenario_id=str(case_id),
                recovery_case_id=case_orm.id,
                payment_id=payment_orm.id,
                decision_request_id=decision_request_id,
                recovery_action_id=action_orm.id,
                financial_event_id=fin_event.id,
                correlation_id=correlation_id,
                audit_schema_version=snapshots["audit_schema_version"],
                provider=audit_record.provider,
                model=audit_record.model,
                prompt_version=audit_record.prompt_version,
                prompt_hash=audit_record.prompt_hash,
                agent_version=audit_record.agent_version,
                recommended_action=audit_record.recommended_action.value,
                confidence=audit_record.confidence,
                reasoning_codes=audit_record.reasoning_codes,
                uncertainty=audit_record.uncertainty,
                requires_human_review=audit_record.requires_human_review,
                fallback_used=audit_record.fallback_used,
                fallback_reason=audit_record.fallback_reason,
                latency_ms=audit_record.latency_ms,
                input_tokens=audit_record.input_tokens,
                output_tokens=audit_record.output_tokens,
                estimated_llm_cost_minor=audit_record.estimated_llm_cost_minor,
                final_action=rec.recommended_action.value,
                expected_net_incremental_revenue_minor=rec.expected_net_incremental_revenue_minor,
                context_snapshot_json=snapshots["context_snapshot_json"],
                proposal_json=snapshots["proposal_json"],
                proposal_validation_json=snapshots["proposal_validation_json"],
                policy_result_json=snapshots["policy_result_json"],
                authorization_result_json=snapshots["authorization_result_json"],
                economic_candidates_json=snapshots["economic_candidates_json"],
                selection_result_json=snapshots["selection_result_json"],
                created_at=audit_record.created_at,
            )
            session.add(orm_audit)

        await session.flush()

        return OrchestrationResult(
            success=True,
            recovery_case_id=case_id,
            payment_id=payment_orm.id,
            case_status=case_orm.status,
            decision=rec,
            action_id=action_id,
            action_type=rec.recommended_action,
            action_status=action_orm.status,
            execution_result=exec_result,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            is_idempotent=False,
            correlation_id=correlation_id,
        )
