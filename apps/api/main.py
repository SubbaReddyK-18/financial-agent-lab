"""
apps/api/main.py

FastAPI application factory for Financial Agent Lab.

Hardened for production with:
- Structured exception handling
- Request correlation context middleware
- Operational health and readiness checks
- Lifespan management for graceful startup/shutdown
- Config-driven authentication boundaries.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI

from apps.api.middleware.correlation import CorrelationIdMiddleware
from apps.api.middleware.error_handler import register_exception_handlers
from apps.api.routes import ai_decisions, approvals, health, observability, simulation, webhooks
from apps.api.security.auth import verify_admin_auth
from apps.api.settings import get_settings
from infrastructure.database.connection import async_engine
from infrastructure.logging import configure_structured_logging

logger = logging.getLogger("apps.api.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan manager.
    Handles startup configuration and graceful database connection shutdown.
    """
    settings = get_settings()
    configure_structured_logging(log_level=settings.log_level, json_format=settings.effective_log_json)
    logger.info(
        "Starting Financial Agent Lab API [env=%s, log_level=%s]",
        settings.app_env,
        settings.log_level,
    )
    yield
    logger.info("Shutting down Financial Agent Lab API...")
    # Cleanly close database engine connection pools
    await async_engine.dispose()
    logger.info("Database engine connections cleanly disposed.")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application instance.
    """
    settings = get_settings()
    app = FastAPI(
        title="Financial Agent Lab",
        description=(
            "Financial Agent Simulation & Decision Lab. "
            "Evaluates whether autonomous financial agents make economically "
            "sound decisions under realistic and adversarial conditions."
        ),
        version="0.8.0",
        docs_url="/docs" if settings.app_env != "production" else None,
        redoc_url="/redoc" if settings.app_env != "production" else None,
        lifespan=lifespan,
    )

    # 1. Register Middlewares
    app.add_middleware(CorrelationIdMiddleware)

    # 2. Register Structured Exception Handlers
    register_exception_handlers(app)

    # 3. Register Route Groups
    app.include_router(health.router)
    app.include_router(webhooks.router)
    app.include_router(observability.router)
    app.include_router(simulation.router, dependencies=[Depends(verify_admin_auth)])
    app.include_router(ai_decisions.router, dependencies=[Depends(verify_admin_auth)])
    app.include_router(approvals.router)

    return app


# Module-level app instance for uvicorn.
app = create_app()
