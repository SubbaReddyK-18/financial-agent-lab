"""
infrastructure/workers/webhook_worker.py

PostgreSQL-backed asynchronous webhook worker CLI and lifecycle manager.

ARCHITECTURAL PRINCIPLES (Block 8, Stage 6):
1. Mirrors outbox_worker.py lifecycle: graceful SIGINT/SIGTERM shutdown.
2. Uses the existing process_pending_webhooks() PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED
   pattern — no additional queue, broker, or cache layer.
3. Configures structured JSON logging from application settings on startup.
4. PostgreSQL remains the sole persistence layer (0 Redis/Celery/Kafka dependencies).
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from apps.api.settings import Settings, get_settings
from infrastructure.workers.runner import process_pending_webhooks

logger = logging.getLogger("infrastructure.workers.webhook")


class WebhookWorker:
    """
    Dedicated worker loop polling and processing pending webhook events from the
    durable inbox using SELECT ... FOR UPDATE SKIP LOCKED.
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        poll_interval_seconds: float = 2.0,
        batch_limit: int = 50,
    ) -> None:
        self.poll_interval = poll_interval_seconds
        self.batch_limit = batch_limit
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

    async def process_single_batch(self) -> int:
        """
        Process a single batch of eligible webhook events inside an isolated transaction.

        Returns:
            Number of events processed in this batch.
        """
        async with self.session_factory() as session:
            try:
                results = await process_pending_webhooks(session, limit=self.batch_limit)
                await session.commit()
                if results:
                    logger.info(
                        "Processed webhook batch of %d events.",
                        len(results),
                        extra={"component": "webhook_worker"},
                    )
                return len(results)
            except Exception as exc:
                await session.rollback()
                logger.exception(
                    "Error processing webhook batch: %s",
                    exc,
                    extra={"component": "webhook_worker"},
                )
                return 0

    async def run(self) -> None:
        """Run the polling loop until stop() is called."""
        if self._stop_event.is_set():
            self._is_running = False
            return

        self._is_running = True
        logger.info(
            "Starting WebhookWorker with poll interval %.2fs...",
            self.poll_interval,
            extra={"component": "webhook_worker"},
        )

        while not self._stop_event.is_set():
            try:
                count = await self.process_single_batch()
                # If events were processed, poll immediately; otherwise sleep
                if not count:
                    try:
                        await asyncio.wait_for(self._stop_event.wait(), timeout=self.poll_interval)
                    except asyncio.TimeoutError:
                        pass
            except asyncio.CancelledError:
                logger.info("WebhookWorker loop cancelled.")
                break
            except Exception as exc:
                logger.error(
                    "Unexpected error in WebhookWorker loop: %s",
                    exc,
                    exc_info=True,
                    extra={"component": "webhook_worker"},
                )
                await asyncio.sleep(self.poll_interval)

        self._is_running = False
        logger.info("WebhookWorker stopped successfully.")

    def stop(self) -> None:
        """Signal the worker loop to stop gracefully."""
        logger.info("Signaling WebhookWorker to stop...")
        self._is_running = False
        self._stop_event.set()

    async def close(self) -> None:
        """Clean up database engine connections on shutdown."""
        self.stop()
        if self._engine:
            await self._engine.dispose()
            logger.info("WebhookWorker database engine disposed.")


async def run_webhook_worker_cli() -> None:
    """CLI entry point for running the webhook worker process."""
    from infrastructure.logging import configure_structured_logging

    settings = get_settings()
    configure_structured_logging(log_level=settings.log_level, json_format=settings.effective_log_json)

    worker = WebhookWorker(poll_interval_seconds=2.0, batch_limit=50)

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
    asyncio.run(run_webhook_worker_cli())
