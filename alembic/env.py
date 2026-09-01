"""
alembic/env.py

Alembic environment configuration for Financial Agent Lab.

Uses synchronous psycopg2 driver for migration execution.
Imports all ORM models so metadata is fully populated before any migration runs.
Reuses the shared application settings (get_settings()) to load credentials from .env.

SECURITY: Connection URL is assembled from shared application settings.
          Credentials are NEVER hardcoded here.
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make project root importable.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import all ORM models to register them with SQLAlchemy metadata.
# This MUST happen before target_metadata is referenced.
from infrastructure.database.base import Base
import infrastructure.database.orm  # noqa: F401 — side-effect import
from apps.api.settings import get_settings

# Alembic Config object (gives access to alembic.ini values).
config = context.config

# Configure Python logging from alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _get_sync_url() -> str:
    """
    Build synchronous psycopg2 URL using the shared application settings.
    Never reads credentials from alembic.ini or hardcodes them.
    """
    url = os.getenv("DATABASE_URL", "")
    if url:
        # Normalise to psycopg2 scheme for sync use.
        if url.startswith("postgresql+asyncpg://"):
            return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+psycopg2://", 1)
        return url
    return get_settings().sync_database_url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (generates SQL without a live connection)."""
    url = _get_sync_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (requires a live database connection)."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _get_sync_url()

    connectable = engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
