"""
apps/api/routes/health.py

Operational Health & Readiness check endpoints.

ARCHITECTURAL PRINCIPLES (Block 8, Requirement 7):
1. GET /health: Liveness check. Returns 200 if the process is alive.
2. GET /ready: Readiness check. Verifies database connectivity and configuration readiness.
3. NEVER exposes database passwords, internal connection strings, or full stack traces.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.settings import Settings, get_settings
from infrastructure.database.connection import get_db_session

logger = logging.getLogger("apps.api.health")
router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness check")
async def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """
    Liveness endpoint. Returns 200 if the API process is alive.
    Does not perform external I/O or database queries.
    """
    return {
        "status": "ok",
        "service": "financial-agent-lab",
        "environment": settings.app_env,
    }


@router.get("/ready", summary="Service readiness check")
async def readiness(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """
    Readiness endpoint. Verifies database connectivity and configuration readiness.
    Returns 200 when ready to accept traffic, 503 when dependencies are unreachable.
    """
    db_ok = False
    try:
        result = await db.execute(text("SELECT 1"))
        if result.scalar() == 1:
            db_ok = True
    except Exception as exc:
        logger.error("Readiness probe failed database ping: %s", exc)
        db_ok = False

    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {
            "status": "unready",
            "database": "unreachable",
            "environment": settings.app_env,
        }

    return {
        "status": "ready",
        "database": "connected",
        "environment": settings.app_env,
        "ai_provider": settings.ai_provider,
    }


@router.get("/health/db", summary="Database liveness check (legacy)")
async def health_db(
    response: Response,
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    """Legacy database check endpoint."""
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        return {"status": "ok", "database": "reachable"}
    except Exception as exc:
        logger.error("Database health check failed: %s", exc)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "error", "database": "unreachable"}
