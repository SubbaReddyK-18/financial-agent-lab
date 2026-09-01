"""
domain/recovery/control_plane.py

Production-Safe Recovery Action & Control Plane.

ARCHITECTURAL PRINCIPLES (Block 7, Requirements 1-10):
1. Deterministic Action Lifecycle: Strict state transitions enforced via state machine.
2. Idempotency & Database Integrity: Deterministic idempotency keys backed by UNIQUE constraints.
3. Transactional Outbox Pattern: Atomic outbox events persisted alongside recovery actions.
4. Bounded Retries: Deterministic exponential backoff with max attempt exhaustion.
5. Stale / Superseded Protection: Verifies case, payment, and supersession state before execution.
6. Execution Control Boundary: Action execution != payment capture; only reconciliation transitions payments.
7. Observability & Telemetry: Complete audit trails without logging secrets or raw chain-of-thought.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.intelligence.models.context import (
    CustomerProfile,
    PaymentFailureDetails,
    RecoveryContext,
    TemporalContext,
)
from domain.policies.models import MerchantRecoveryPolicy
from domain.recovery.execution import ActionExecutionResult, get_action_executor
from domain.recovery.action_validator import ActionValidationRequest, validate_recovery_action
from domain.recovery.models import RecoveryCase
from domain.recovery.state_machine import validate_action_transition
from domain.shared.enums import (
    OutboxEventStatus,
    OutboxEventType,
    PaymentStatus,
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)
from infrastructure.database.orm.outbox import RecoveryOutboxEventORM
from infrastructure.database.orm.approval import RecoveryActionApprovalORM
from infrastructure.database.orm.payment import PaymentAttemptORM, PaymentORM
from infrastructure.database.orm.recovery import (
    MerchantRecoveryPolicyORM,
    RecoveryActionORM,
    RecoveryCaseORM,
)

logger = logging.getLogger("domain.recovery.control_plane")


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def generate_action_idempotency_key(
    case_id: uuid.UUID,
    action_type: RecoveryActionType,
    attempt_number: int = 1,
    decision_id: Optional[uuid.UUID] = None,
) -> str:
    """
    Generate a deterministic SHA-256 idempotency key for a recovery action.
    """
    dec_str = str(decision_id) if decision_id else "direct"
    raw = f"recovery_action:{case_id}:{action_type.value}:{attempt_number}:{dec_str}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class RecoveryActionControlPlane:
    """
    Control plane coordinating action lifecycle, idempotency guards,
    transactional outbox persistence, and execution dispatching.
    """

    def __init__(self) -> None:
        pass

    async def create_approved_action_with_outbox(
        self,
        case: RecoveryCaseORM,
        action_type: RecoveryActionType,
        discount_percent: int,
        session: AsyncSession,
        decision_id: Optional[uuid.UUID] = None,
        economic_metadata: Optional[dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
        now: Optional[datetime] = None,
        requires_approval: bool = False,
    ) -> tuple[RecoveryActionORM, Optional[RecoveryOutboxEventORM]]:
        """
        Persist the selected action. Approval-gated actions intentionally have
        no dispatch event until an authenticated approval operation succeeds.
        """
        now = now or _utcnow()
        attempt_number = len(case.actions) + 1 if hasattr(case, "actions") and case.actions else 1
        idem_key = generate_action_idempotency_key(
            case_id=case.id,
            action_type=action_type,
            attempt_number=attempt_number,
            decision_id=decision_id,
        )

        metadata = {
            "decision_id": str(decision_id) if decision_id else None,
            "correlation_id": correlation_id,
            "economic_evaluation": economic_metadata or {},
        }

        action_id = uuid.uuid4()
        outbox_id = uuid.uuid4()

        action_orm = RecoveryActionORM(
            id=action_id,
            recovery_case_id=case.id,
            action_type=action_type.value,
            status=(RecoveryActionStatus.PENDING_APPROVAL.value if requires_approval
                    else RecoveryActionStatus.APPROVED.value),
            discount_percent_offered=discount_percent,
            idempotency_key=idem_key,
            execution_attempt=attempt_number,
            max_retries=3,
            retry_count=0,
            metadata_json=metadata,
            created_at=now,
        )
        session.add(action_orm)
        await session.flush()

        if requires_approval:
            return action_orm, None

        outbox_payload = {
            "action_id": str(action_id),
            "recovery_case_id": str(case.id),
            "payment_id": str(case.payment_id),
            "action_type": action_type.value,
            "discount_percent": discount_percent,
            "correlation_id": correlation_id,
        }

        outbox_event = RecoveryOutboxEventORM(
            id=outbox_id,
            recovery_action_id=action_id,
            recovery_case_id=case.id,
            event_type=OutboxEventType.RECOVERY_ACTION_DISPATCH.value,
            status=OutboxEventStatus.PENDING.value,
            payload_json=outbox_payload,
            idempotency_key=f"outbox_{idem_key}",
            attempt_count=0,
            max_attempts=3,
            next_attempt_at=now,
            created_at=now,
        )
        session.add(outbox_event)
        await session.flush()

        return action_orm, outbox_event

    async def dispatch_action(
        self,
        action_id: uuid.UUID,
        session: AsyncSession,
        correlation_id: Optional[str] = None,
        now: Optional[datetime] = None,
        action_orm: Optional[RecoveryActionORM] = None,
        case_orm: Optional[RecoveryCaseORM] = None,
        payment_orm: Optional[PaymentORM] = None,
        context: Optional[RecoveryContext] = None,
    ) -> ActionExecutionResult:
        """
        Execute pre-execution guards, transition action to EXECUTING, invoke the
        appropriate executor, and handle completion or bounded retries.
        """
        now = now or _utcnow()
        should_check_newer = action_orm is None

        # 1. Acquire RecoveryAction row
        if action_orm is None:
            action_orm = await session.scalar(
                select(RecoveryActionORM)
                .where(RecoveryActionORM.id == action_id)
                .with_for_update()
            )
        if action_orm is None:
            raise ValueError(f"Recovery action {action_id} not found.")

        # 2. Guard against already completed/terminal actions
        current_status = RecoveryActionStatus(action_orm.status)
        if current_status != RecoveryActionStatus.APPROVED:
            # An outbox row for any non-approved action is never executable.
            # Normal pending approval has no row; this also safely neutralizes
            # stale/reclaimed rows created before a cancellation/supersession.
            if current_status == RecoveryActionStatus.PENDING_APPROVAL:
                await self._update_outbox_status(
                    action_id, OutboxEventStatus.CANCELLED, session, now
                )
                logger.warning("Action %s is pending human approval; refusing dispatch.", action_id)
            elif current_status in (
                RecoveryActionStatus.COMPLETED,
                RecoveryActionStatus.FAILED,
                RecoveryActionStatus.CANCELLED,
                RecoveryActionStatus.EXPIRED,
                RecoveryActionStatus.SUPERSEDED,
            ):
                terminal_outbox_status = OutboxEventStatus(current_status.value)
                await self._update_outbox_status(
                    action_id, terminal_outbox_status, session, now, processed_at=now
                )
                logger.info(
                    "Action %s already in terminal state %s; skipping dispatch.",
                    action_id, current_status.value,
                )
            else:
                await self._update_outbox_status(
                    action_id, OutboxEventStatus.CANCELLED, session, now, processed_at=now
                )
                logger.warning("Action %s is not approved; refusing dispatch.", action_id)
            return ActionExecutionResult(
                action_id=action_id,
                action_type=RecoveryActionType(action_orm.action_type),
                status=current_status.value,
                execution_reference=f"IDEMPOTENT_SKIPPED_{action_id.hex[:12]}",
                details={"reason": f"Action is not executable in status {current_status.value}"},
                executed_at=now,
                is_test_mode=True,
            )

        # 3. Guard against stale / superseded conditions
        if case_orm is None:
            case_orm = await session.scalar(
                select(RecoveryCaseORM)
                .where(RecoveryCaseORM.id == action_orm.recovery_case_id)
                .with_for_update()
            )
        if case_orm is None:
            raise ValueError(f"Recovery case {action_orm.recovery_case_id} not found.")

        # Check if RecoveryCase has already closed or reached terminal status
        if case_orm.status in (
            RecoveryCaseStatus.CLOSED.value,
            RecoveryCaseStatus.RECOVERED.value,
            RecoveryCaseStatus.IRRECOVERABLE.value,
        ):
            validate_action_transition(current_status, RecoveryActionStatus.SUPERSEDED)
            action_orm.status = RecoveryActionStatus.SUPERSEDED.value
            action_orm.failure_reason = f"Case is in terminal state: {case_orm.status}"
            await self._update_outbox_status(action_id, OutboxEventStatus.SUPERSEDED, session, now)
            logger.warning("Action %s superseded: case in state %s", action_id, case_orm.status)
            return ActionExecutionResult(
                action_id=action_id,
                action_type=RecoveryActionType(action_orm.action_type),
                status=RecoveryActionStatus.SUPERSEDED.value,
                execution_reference=f"SUPERSEDED_{action_id.hex[:12]}",
                details={"reason": action_orm.failure_reason},
                executed_at=now,
                is_test_mode=True,
            )

        # Check if payment has already captured or succeeded
        if payment_orm is None:
            payment_orm = await session.scalar(
                select(PaymentORM).where(PaymentORM.id == case_orm.payment_id)
            )
        if payment_orm and payment_orm.status in (
            PaymentStatus.CAPTURED.value,
            PaymentStatus.AUTHORIZED.value,
        ):
            validate_action_transition(current_status, RecoveryActionStatus.SUPERSEDED)
            action_orm.status = RecoveryActionStatus.SUPERSEDED.value
            action_orm.failure_reason = f"Payment already resolved: {payment_orm.status}"
            await self._update_outbox_status(action_id, OutboxEventStatus.SUPERSEDED, session, now)
            logger.warning("Action %s superseded: payment status is %s", action_id, payment_orm.status)
            return ActionExecutionResult(
                action_id=action_id,
                action_type=RecoveryActionType(action_orm.action_type),
                status=RecoveryActionStatus.SUPERSEDED.value,
                execution_reference=f"SUPERSEDED_{action_id.hex[:12]}",
                details={"reason": action_orm.failure_reason},
                executed_at=now,
                is_test_mode=True,
            )

        # Check if action has expired (> 72 hours TTL)
        if (now - action_orm.created_at).total_seconds() > 72 * 3600:
            validate_action_transition(current_status, RecoveryActionStatus.EXPIRED)
            action_orm.status = RecoveryActionStatus.EXPIRED.value
            action_orm.failure_reason = "Action expired: exceeded 72 hour TTL"
            await self._update_outbox_status(action_id, OutboxEventStatus.EXPIRED, session, now)
            logger.warning("Action %s EXPIRED: exceeded 72h TTL", action_id)
            return ActionExecutionResult(
                action_id=action_id,
                action_type=RecoveryActionType(action_orm.action_type),
                status=RecoveryActionStatus.EXPIRED.value,
                execution_reference=f"EXPIRED_{action_id.hex[:12]}",
                details={"reason": action_orm.failure_reason},
                executed_at=now,
                is_test_mode=True,
            )

        # 4. Check for newer active action on the same case (only when dispatching asynchronously from outbox)
        if should_check_newer:
            newer_action = await session.scalar(
                select(RecoveryActionORM)
                .where(
                    RecoveryActionORM.recovery_case_id == case_orm.id,
                    RecoveryActionORM.id != action_orm.id,
                    RecoveryActionORM.created_at > action_orm.created_at,
                    RecoveryActionORM.status.in_([
                        RecoveryActionStatus.APPROVED.value,
                        RecoveryActionStatus.EXECUTING.value,
                        RecoveryActionStatus.COMPLETED.value,
                    ]),
                )
            )
            if newer_action is not None:
                validate_action_transition(current_status, RecoveryActionStatus.SUPERSEDED)
                action_orm.status = RecoveryActionStatus.SUPERSEDED.value
                action_orm.superseded_by_action_id = newer_action.id
                action_orm.failure_reason = f"Superseded by newer action {newer_action.id}"
                await self._update_outbox_status(action_id, OutboxEventStatus.SUPERSEDED, session, now)
                logger.warning("Action %s superseded by newer action %s", action_id, newer_action.id)
                return ActionExecutionResult(
                    action_id=action_id,
                    action_type=RecoveryActionType(action_orm.action_type),
                    status=RecoveryActionStatus.SUPERSEDED.value,
                    execution_reference=f"SUPERSEDED_{action_id.hex[:12]}",
                    details={"superseded_by": str(newer_action.id)},
                    executed_at=now,
                    is_test_mode=True,
                )

        # 5. Revalidate deterministic policy and authorization against the
        # current authoritative database state.  An APPROVED status is a
        # dispatch authorization, not permanent permission to execute.
        policy_orm = await session.scalar(
            select(MerchantRecoveryPolicyORM).where(
                MerchantRecoveryPolicyORM.merchant_id == case_orm.merchant_id
            )
        )
        domain_policy = (
            MerchantRecoveryPolicy(
                merchant_id=policy_orm.merchant_id,
                maximum_discount_percent=policy_orm.maximum_discount_percent,
                maximum_interventions=policy_orm.maximum_interventions,
                cooldown_hours=policy_orm.cooldown_hours,
                high_value_threshold_minor=policy_orm.high_value_threshold_minor,
                high_value_requires_approval=policy_orm.high_value_requires_approval,
                low_confidence_requires_review=policy_orm.low_confidence_requires_review,
            )
            if policy_orm
            else MerchantRecoveryPolicy(merchant_id=case_orm.merchant_id)
        )
        completed_interventions = await session.scalar(
            select(func.count())
            .select_from(RecoveryActionORM)
            .where(
                RecoveryActionORM.recovery_case_id == case_orm.id,
                RecoveryActionORM.status == RecoveryActionStatus.COMPLETED.value,
            )
        )
        last_completed_action = await session.scalar(
            select(RecoveryActionORM)
            .where(
                RecoveryActionORM.recovery_case_id == case_orm.id,
                RecoveryActionORM.status == RecoveryActionStatus.COMPLETED.value,
            )
            .order_by(RecoveryActionORM.executed_at.desc())
            .limit(1)
        )
        validation = validate_recovery_action(
            ActionValidationRequest(
                case=RecoveryCase(
                    id=case_orm.id,
                    merchant_id=case_orm.merchant_id,
                    customer_id=case_orm.customer_id,
                    payment_id=case_orm.payment_id,
                    amount_at_risk_minor=case_orm.amount_at_risk_minor,
                    status=RecoveryCaseStatus(case_orm.status),
                    opened_at=case_orm.opened_at,
                    closed_at=case_orm.closed_at,
                ),
                action_type=RecoveryActionType(action_orm.action_type),
                policy=domain_policy,
                completed_interventions=completed_interventions or 0,
                last_action_at=(
                    last_completed_action.executed_at if last_completed_action else None
                ),
                requested_discount_percent=action_orm.discount_percent_offered,
                now=now,
            )
        )
        if not validation.is_valid:
            validate_action_transition(current_status, RecoveryActionStatus.CANCELLED)
            action_orm.status = RecoveryActionStatus.CANCELLED.value
            action_orm.failure_reason = "; ".join(validation.violations)
            await self._update_outbox_status(
                action_id, OutboxEventStatus.CANCELLED, session, now,
                processed_at=now, error_message=action_orm.failure_reason,
            )
            logger.warning("Action %s cancelled by execution-time policy: %s", action_id, action_orm.failure_reason)
            return ActionExecutionResult(
                action_id=action_id,
                action_type=RecoveryActionType(action_orm.action_type),
                status=RecoveryActionStatus.CANCELLED.value,
                execution_reference=f"POLICY_REJECTED_{action_id.hex[:12]}",
                details={"reason": action_orm.failure_reason},
                error_code="POLICY_REVALIDATION_FAILED",
                executed_at=now,
                is_test_mode=True,
            )
        if validation.requires_approval:
            approval = await session.scalar(
                select(RecoveryActionApprovalORM).where(
                    RecoveryActionApprovalORM.recovery_action_id == action_id,
                    RecoveryActionApprovalORM.decision == "APPROVED",
                )
            )
            if approval is None:
                validate_action_transition(current_status, RecoveryActionStatus.CANCELLED)
                action_orm.status = RecoveryActionStatus.CANCELLED.value
                action_orm.failure_reason = "Required human approval record is absent."
                await self._update_outbox_status(
                    action_id, OutboxEventStatus.CANCELLED, session, now,
                    processed_at=now, error_message=action_orm.failure_reason,
                )
                return ActionExecutionResult(
                    action_id=action_id,
                    action_type=RecoveryActionType(action_orm.action_type),
                    status=RecoveryActionStatus.CANCELLED.value,
                    execution_reference=f"APPROVAL_MISSING_{action_id.hex[:12]}",
                    details={"reason": action_orm.failure_reason},
                    error_code="AUTHORIZATION_REVALIDATION_FAILED",
                    executed_at=now,
                    is_test_mode=True,
                )

        # 6. Transition to EXECUTING
        validate_action_transition(current_status, RecoveryActionStatus.EXECUTING)
        action_orm.status = RecoveryActionStatus.EXECUTING.value
        await self._update_outbox_status(action_id, OutboxEventStatus.PROCESSING, session, now)
        await session.flush()

        # 7. Build or use existing recovery context
        if context is None:
            attempt_orm = (
                await session.scalar(
                    select(PaymentAttemptORM)
                    .where(PaymentAttemptORM.payment_id == payment_orm.id)
                    .order_by(PaymentAttemptORM.attempt_number.desc())
                )
                if payment_orm
                else None
            )

            context = RecoveryContext(
                payment=PaymentFailureDetails(
                    payment_id=case_orm.payment_id,
                    amount_minor=case_orm.amount_at_risk_minor,
                    attempt_count=attempt_orm.attempt_number if attempt_orm else 1,
                    failure_code=attempt_orm.failure_code if attempt_orm else "PAYMENT_FAILED",
                ),
                customer=CustomerProfile(
                    customer_id=case_orm.customer_id,
                ),
                policy=domain_policy,
                temporal=TemporalContext(current_time=now),
            )

        # 8. Execute via dedicated ActionExecutor
        action_type = RecoveryActionType(action_orm.action_type)
        executor = get_action_executor(action_type)
        try:
            exec_result = await executor.execute(
                action_id=action_orm.id,
                context=context,
                discount_percent=action_orm.discount_percent_offered,
                metadata=action_orm.metadata_json,
            )
        except Exception as exc:
            logger.exception("Unexpected exception executing action %s", action_id)
            exec_result = ActionExecutionResult(
                action_id=action_id,
                action_type=action_type,
                status=RecoveryActionStatus.FAILED.value,
                execution_reference=f"ERROR_{action_id.hex[:12]}",
                is_retryable=True,
                error_message=str(exc),
                error_code="EXECUTION_EXCEPTION",
                executed_at=now,
                is_test_mode=True,
            )

        # 9. Handle execution outcome
        if exec_result.status == "COMPLETED":
            validate_action_transition(RecoveryActionStatus.EXECUTING, RecoveryActionStatus.COMPLETED)
            action_orm.status = RecoveryActionStatus.COMPLETED.value
            action_orm.executed_at = exec_result.executed_at

            current_meta = dict(action_orm.metadata_json or {})
            current_meta["execution_reference"] = exec_result.execution_reference
            current_meta["execution_details"] = exec_result.details
            action_orm.metadata_json = current_meta

            await self._update_outbox_status(
                action_id,
                OutboxEventStatus.COMPLETED,
                session,
                now,
                processed_at=exec_result.executed_at,
            )
            logger.info("Action %s COMPLETED with ref %s", action_id, exec_result.execution_reference)
        else:
            action_orm.failure_reason = exec_result.error_message or "Execution failed"
            current_meta = dict(action_orm.metadata_json or {})
            current_meta["last_execution_error_code"] = exec_result.error_code
            current_meta["last_execution_retryable"] = exec_result.is_retryable
            action_orm.metadata_json = current_meta

            outbox_event = await session.scalar(
                select(RecoveryOutboxEventORM).where(
                    RecoveryOutboxEventORM.recovery_action_id == action_id
                )
            )
            retry_limit_available = (
                outbox_event is not None
                and outbox_event.attempt_count < outbox_event.max_attempts
                and action_orm.retry_count < action_orm.max_retries
            )

            # Retry the same deterministic action.  It retains its identity,
            # idempotency key, and decision; this path never invokes AI.
            if exec_result.is_retryable and retry_limit_available:
                validate_action_transition(RecoveryActionStatus.EXECUTING, RecoveryActionStatus.APPROVED)
                action_orm.status = RecoveryActionStatus.APPROVED.value
                action_orm.retry_count += 1
                delay_sec = 2 ** action_orm.retry_count * 10
                action_orm.next_retry_at = now + timedelta(seconds=delay_sec)

                await self._update_outbox_status(
                    action_id,
                    OutboxEventStatus.PENDING,
                    session,
                    now,
                    next_attempt_at=action_orm.next_retry_at,
                    error_message=exec_result.error_message,
                )
                logger.warning(
                    "Action %s failed (retryable). Outbox retry #%d at %s",
                    action_id,
                    action_orm.retry_count,
                    action_orm.next_retry_at.isoformat(),
                )
            else:
                validate_action_transition(RecoveryActionStatus.EXECUTING, RecoveryActionStatus.FAILED)
                action_orm.status = RecoveryActionStatus.FAILED.value
                await self._update_outbox_status(
                    action_id,
                    OutboxEventStatus.FAILED,
                    session,
                    now,
                    processed_at=now,
                    error_message=action_orm.failure_reason,
                )
                logger.error("Action %s FAILED terminally: %s", action_id, action_orm.failure_reason)

        return exec_result

    async def process_outbox_batch(
        self,
        session: AsyncSession,
        limit: int = 10,
        now: Optional[datetime] = None,
    ) -> list[ActionExecutionResult]:
        """
        Claim and execute pending outbox events using row-level locking.
        Reclaims abandoned PROCESSING events stuck > 15 minutes.
        """
        now = now or _utcnow()
        stuck_threshold = now - timedelta(minutes=15)
        outbox_events = (
            await session.scalars(
                select(RecoveryOutboxEventORM)
                .where(
                    or_(
                        and_(
                            RecoveryOutboxEventORM.status == OutboxEventStatus.PENDING.value,
                            RecoveryOutboxEventORM.next_attempt_at <= now,
                        ),
                        and_(
                            RecoveryOutboxEventORM.status == OutboxEventStatus.PROCESSING.value,
                            RecoveryOutboxEventORM.created_at <= stuck_threshold,
                        ),
                    )
                )
                .order_by(RecoveryOutboxEventORM.created_at.asc())
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()

        results: list[ActionExecutionResult] = []
        for event in outbox_events:
            event.status = OutboxEventStatus.PROCESSING.value
            event.attempt_count += 1
            await session.flush()

            res = await self.dispatch_action(
                action_id=event.recovery_action_id,
                session=session,
                correlation_id=event.payload_json.get("correlation_id") if event.payload_json else None,
                now=now,
            )
            results.append(res)

        return results

    async def _update_outbox_status(
        self,
        action_id: uuid.UUID,
        new_status: OutboxEventStatus,
        session: AsyncSession,
        now: datetime,
        attempt_increment: bool = False,
        next_attempt_at: Optional[datetime] = None,
        processed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Helper to update associated outbox event state."""
        try:
            outbox_event = await session.scalar(
                select(RecoveryOutboxEventORM).where(
                    RecoveryOutboxEventORM.recovery_action_id == action_id
                )
            )
            if outbox_event:
                outbox_event.status = new_status.value
                if attempt_increment:
                    outbox_event.attempt_count += 1
                if next_attempt_at:
                    outbox_event.next_attempt_at = next_attempt_at
                if processed_at:
                    outbox_event.processed_at = processed_at
                if error_message:
                    outbox_event.error_message = error_message
        except Exception:
            logger.debug("Outbox record update skipped or not present for action %s", action_id)
