"""PostgreSQL-backed asynchronous recovery-decision worker."""
from __future__ import annotations
import asyncio
import logging
import signal
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
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


class DecisionWorker:
    """
    Dedicated worker loop polling and processing pending recovery decision requests.

    Uses PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED for concurrent, race-free execution.
    Mirrors the OutboxWorker/WebhookWorker lifecycle pattern.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        poll_interval_seconds: float = 2.0,
        batch_limit: int = 10,
    ) -> None:
        self.poll_interval = poll_interval_seconds
        self.batch_limit = batch_limit
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._engine = None

        if session_factory is None:
            from apps.api.settings import get_settings
            settings = get_settings()
            self._engine = create_async_engine(
                settings.async_database_url,
                pool_pre_ping=True,
                echo=False,
            )
            self.session_factory = async_sessionmaker(
                bind=self._engine,
                expire_on_commit=False,
            )
        else:
            self.session_factory = session_factory

    async def process_single_batch(self) -> int:
        """Process a single batch of eligible decision requests in an isolated transaction."""
        async with self.session_factory() as session:
            try:
                count = await process_pending_decision_requests(session, limit=self.batch_limit)
                await session.commit()
                if count:
                    logger.info(
                        "Processed decision batch of %d requests.",
                        count,
                        extra={"component": "decision_worker"},
                    )
                return count
            except Exception as exc:
                await session.rollback()
                logger.exception(
                    "Error processing decision batch: %s",
                    exc,
                    extra={"component": "decision_worker"},
                )
                return 0

    async def run(self) -> None:
        """Run the polling loop until stop() is called."""
        if self._stop_event.is_set():
            self._is_running = False
            return

        self._is_running = True
        logger.info("Starting DecisionWorker with poll interval %.2fs...", self.poll_interval)

        while not self._stop_event.is_set():
            try:
                count = await self.process_single_batch()
                if not count:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                logger.info("DecisionWorker loop cancelled.")
                break
            except Exception as exc:
                logger.error("Unexpected error in DecisionWorker loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.poll_interval)

        self._is_running = False
        logger.info("DecisionWorker stopped successfully.")

    def stop(self) -> None:
        """Signal the worker loop to stop gracefully."""
        logger.info("Signaling DecisionWorker to stop...")
        self._is_running = False
        self._stop_event.set()

    async def close(self) -> None:
        """Clean up database engine connections on shutdown."""
        self.stop()
        if self._engine:
            await self._engine.dispose()
            logger.info("DecisionWorker database engine disposed.")


async def run_decision_worker_cli() -> None:
    """CLI entry point for running the decision worker process."""
    from infrastructure.logging import configure_structured_logging
    from apps.api.settings import get_settings

    settings = get_settings()
    configure_structured_logging(log_level=settings.log_level, json_format=settings.effective_log_json)

    worker = DecisionWorker(poll_interval_seconds=2.0, batch_limit=10)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            # Signal handlers not implemented on Windows for some signals
            pass

    try:
        await worker.run()
    finally:
        await worker.close()


if __name__ == "__main__":
    asyncio.run(run_decision_worker_cli())
