"""
infrastructure/database/connection.py

Database engine and session factories.

Provides:
- async_engine: for application use (asyncpg driver)
- AsyncSessionFactory: async context manager for DB sessions
- sync_engine: for Alembic migrations only (psycopg2 driver)

SECURITY: Connection strings are assembled from shared application settings (.env).
          Credentials are NEVER hardcoded here.

P-08: PostgreSQL is the authoritative financial data store.
"""

from __future__ import annotations

import os
from typing import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from apps.api.settings import get_settings


def _build_async_url() -> str:
    """Build asyncpg connection URL from individual env vars or DATABASE_URL."""
    url = os.getenv("DATABASE_URL")
    if url:
        # Ensure the scheme is asyncpg-compatible.
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url
    return get_settings().async_database_url


def _build_sync_url() -> str:
    """Build psycopg2 connection URL for sync use."""
    url = os.getenv("DATABASE_URL")
    if url:
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    return get_settings().sync_database_url


from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Async engine — used by the application
# ---------------------------------------------------------------------------

async_engine = create_async_engine(
    _build_async_url(),
    echo=os.getenv("APP_DEBUG", "false").lower() == "true",
    poolclass=NullPool,
)

AsyncSessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async DB session.

    Usage in a route:
        async def my_route(db: AsyncSession = Depends(get_db_session)):
            ...
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ---------------------------------------------------------------------------
# Sync engine — Alembic migrations only
# ---------------------------------------------------------------------------

def get_sync_engine():
    """Return a synchronous engine for Alembic migration use only."""
    return create_engine(_build_sync_url(), echo=False)
