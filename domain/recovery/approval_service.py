"""Explicit, durable authorization for actions requiring human approval."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.recovery.state_machine import validate_action_transition
from domain.shared.enums import OutboxEventStatus, OutboxEventType, RecoveryActionStatus
from domain.shared.errors import InvalidActionError
from infrastructure.database.orm.approval import RecoveryActionApprovalORM
from infrastructure.database.orm.outbox import RecoveryOutboxEventORM
from infrastructure.database.orm.recovery import RecoveryActionORM


async def approve_recovery_action(action_id: uuid.UUID, actor_id: str, session: AsyncSession, correlation_id: str | None = None, reason: str | None = None) -> RecoveryActionORM:
    """Approve one pending action and atomically enqueue its dispatch."""
    return await _record_decision(action_id, actor_id, "APPROVED", session, correlation_id, reason)


async def reject_recovery_action(action_id: uuid.UUID, actor_id: str, session: AsyncSession, correlation_id: str | None = None, reason: str | None = None) -> RecoveryActionORM:
    """Reject one pending action; rejection is final and creates no outbox."""
    return await _record_decision(action_id, actor_id, "REJECTED", session, correlation_id, reason)


async def _record_decision(action_id: uuid.UUID, actor_id: str, decision: str, session: AsyncSession, correlation_id: str | None, reason: str | None) -> RecoveryActionORM:
    if not actor_id:
        raise InvalidActionError("A verified approval actor is required.")
    # Row locking serializes concurrent approvers for the same action.
    action = await session.scalar(select(RecoveryActionORM).where(RecoveryActionORM.id == action_id).with_for_update())
    if action is None:
        raise InvalidActionError("Recovery action not found.")
    existing = await session.scalar(select(RecoveryActionApprovalORM).where(RecoveryActionApprovalORM.recovery_action_id == action_id))
    if existing is not None:
        if existing.decision == decision:
            return action  # idempotent replay; do not create another event
        raise InvalidActionError("Recovery action has already received an approval decision.")
    if action.status != RecoveryActionStatus.PENDING_APPROVAL.value:
        raise InvalidActionError(f"Recovery action is not awaiting approval: {action.status}")

    now = datetime.now(tz=timezone.utc)
    if decision == "APPROVED":
        validate_action_transition(RecoveryActionStatus.PENDING_APPROVAL, RecoveryActionStatus.APPROVED)
        action.status = RecoveryActionStatus.APPROVED.value
    else:
        validate_action_transition(RecoveryActionStatus.PENDING_APPROVAL, RecoveryActionStatus.CANCELLED)
        action.status = RecoveryActionStatus.CANCELLED.value
        action.failure_reason = reason or "Action rejected by authorized approver"
    session.add(RecoveryActionApprovalORM(id=uuid.uuid4(), recovery_action_id=action.id, actor_id=actor_id, decision=decision, reason=reason, correlation_id=correlation_id, created_at=now))
    if decision == "APPROVED":
        session.add(RecoveryOutboxEventORM(id=uuid.uuid4(), recovery_action_id=action.id, recovery_case_id=action.recovery_case_id, event_type=OutboxEventType.RECOVERY_ACTION_DISPATCH.value, status=OutboxEventStatus.PENDING.value, payload_json={"action_id": str(action.id), "recovery_case_id": str(action.recovery_case_id), "correlation_id": correlation_id}, idempotency_key=f"outbox_{action.idempotency_key}", attempt_count=0, max_attempts=3, next_attempt_at=now, created_at=now))
    await session.flush()
    return action
