"""
infrastructure/workers/outbox_worker.py

Production-Safe Transactional Outbox Worker.

ARCHITECTURAL PRINCIPLES (Block 8, Requirement 5 & 6):
1. Reliable batch processing using SELECT ... FOR UPDATE SKIP LOCKED.
2. Graceful shutdown on SIGINT/SIGTERM, allowing in-flight tasks to complete cleanly.
3. Automatically reclaims abandoned PROCESSING events (> 15m old).
4. Handles bounded exponential backoff retries and terminal failure transitions.
5. PostgreSQL remains the sole persistence layer (0 Redis/Celery/Kafka dependencies).
"""

from __future__ import annotations

import asyncio
import logging
import signal
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.settings import Settings, get_settings
from domain.recovery.control_plane import RecoveryActionControlPlane
from domain.recovery.execution import ActionExecutionResult

logger = logging.getLogger("infrastructure.workers.outbox")


class OutboxWorker:
    """
    Dedicated worker loop polling and processing pending outbox events.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        poll_interval_seconds: float = 2.0,
        batch_limit: int = 10,
        control_plane: Optional[RecoveryActionControlPlane] = None,
    ) -> None:
        self.poll_interval = poll_interval_seconds
        self.batch_limit = batch_limit
        self.control_plane = control_plane or RecoveryActionControlPlane()
        self._is_running = False
        self._stop_event = asyncio.Event()
        self._engine = None

        if session_factory is None:
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

    async def process_single_batch(
        self, now: Optional[datetime] = None
    ) -> list[ActionExecutionResult]:
        """
        Process a single batch of eligible outbox events inside an isolated transaction.
        """
        async with self.session_factory() as session:
            try:
                results = await self.control_plane.process_outbox_batch(
                    session=session,
                    limit=self.batch_limit,
                    now=now,
                )
                await session.commit()
                if results:
                    logger.info("Processed outbox batch of %d events.", len(results))
                return results
            except Exception as exc:
                await session.rollback()
                logger.exception("Error processing outbox batch: %s", exc)
                return []

    async def run(self) -> None:
        """Run the polling loop until stop() is called."""
        if self._stop_event.is_set():
            self._is_running = False
            return

        self._is_running = True
        logger.info("Starting OutboxWorker with poll interval %.2fs...", self.poll_interval)

        while not self._stop_event.is_set():
            try:
                results = await self.process_single_batch()
                # If events were processed, poll immediately for more; otherwise sleep
                if not results:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                logger.info("OutboxWorker loop cancelled.")
                break
            except Exception as exc:
                logger.error("Unexpected error in OutboxWorker loop: %s", exc, exc_info=True)
                await asyncio.sleep(self.poll_interval)

        self._is_running = False
        logger.info("OutboxWorker stopped successfully.")

    def stop(self) -> None:
        """Signal the worker loop to stop gracefully."""
        logger.info("Signaling OutboxWorker to stop...")
        self._is_running = False
        self._stop_event.set()

    async def close(self) -> None:
        """Clean up database engine connections on shutdown."""
        self.stop()
        if self._engine:
            await self._engine.dispose()
            logger.info("OutboxWorker database engine disposed.")


async def run_outbox_worker_cli() -> None:
    """CLI entry point for running the outbox worker process."""
    from infrastructure.logging import configure_structured_logging

    settings = get_settings()
    configure_structured_logging(log_level=settings.log_level, json_format=settings.effective_log_json)

    worker = OutboxWorker(poll_interval_seconds=2.0, batch_limit=20)

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
    asyncio.run(run_outbox_worker_cli())
