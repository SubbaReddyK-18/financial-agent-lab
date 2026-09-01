"""
infrastructure/workers/runner.py

Background runner for claiming and processing pending webhook events.

Uses PostgreSQL `FOR UPDATE SKIP LOCKED` for concurrent, race-free worker execution.
"""

from __future__ import annotations

import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.database.orm.webhook import RazorpayWebhookEventORM
from infrastructure.workers.webhook_processor import (
    ProcessingResult,
    process_single_webhook_event,
)

logger = logging.getLogger("infrastructure.workers.runner")


async def process_pending_webhooks(
    session: AsyncSession,
    limit: int = 50,
) -> list[ProcessingResult]:
    """
    Claim and process pending webhook events from the durable inbox.

    Args:
        session: Active async database session.
        limit: Max batch size to claim per run.

    Returns:
        List of ProcessingResult items.
    """
    # Atomically lock unclaimed events, skipping any locked by concurrent workers
    stmt = (
        select(RazorpayWebhookEventORM)
        .where(RazorpayWebhookEventORM.processing_status == "RECEIVED")
        .order_by(RazorpayWebhookEventORM.received_at.asc())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )

    events = (await session.scalars(stmt)).all()
    results: list[ProcessingResult] = []

    for event in events:
        try:
            result = await process_single_webhook_event(event, session)
            results.append(result)
        except Exception as e:
            logger.exception("Unexpected error processing event %r", event.razorpay_event_id)
            event.processing_status = "FAILED"
            event.error_message = f"Unexpected worker error: {e}"
            await session.flush()
            results.append(
                ProcessingResult(
                    success=False,
                    event_id=event.razorpay_event_id,
                    error_message=str(e),
                )
            )

    return results
