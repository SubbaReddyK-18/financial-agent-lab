"""PostgreSQL-backed asynchronous recovery-decision worker."""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from domain.recovery.orchestrator import RecoveryDecisionOrchestrator
from infrastructure.database.orm.decision_request import RecoveryDecisionRequestORM

logger = logging.getLogger("infrastructure.workers.decision")

def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)

async def process_pending_decision_requests(session: AsyncSession, limit: int = 10, now: datetime | None = None) -> int:
    """Claim due requests with SKIP LOCKED and durably record bounded retries."""
    now = now or _utcnow()
    requests = (await session.scalars(select(RecoveryDecisionRequestORM).where(
        RecoveryDecisionRequestORM.status == "PENDING", RecoveryDecisionRequestORM.next_attempt_at <= now
    ).order_by(RecoveryDecisionRequestORM.created_at).limit(limit).with_for_update(skip_locked=True))).all()
    completed = 0
    for request in requests:
        request.status = "PROCESSING"
        request.attempt_count += 1
        await session.flush()
        try:
            result = await RecoveryDecisionOrchestrator().orchestrate_case(
                request.recovery_case_id, session, correlation_id=request.correlation_id, now=now,
                decision_request_id=request.id,
            )
            request.status = "COMPLETED"
            request.processed_at = now
            request.error_message = None
            completed += 1
        except Exception as exc:
            if request.attempt_count >= request.max_attempts:
                request.status = "FAILED"
                request.processed_at = now
            else:
                request.status = "PENDING"
                request.next_attempt_at = now + timedelta(seconds=(2 ** request.attempt_count) * 10)
            request.error_message = str(exc)[:512]
            logger.exception("Recovery decision request %s failed", request.id)
        await session.flush()
    return completed
