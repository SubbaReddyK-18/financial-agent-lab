"""
infrastructure/database/base.py

SQLAlchemy declarative base for all ORM models.

All ORM models inherit from Base. This module is the single registration
point for SQLAlchemy's metadata, which Alembic uses for autogenerate.

Note: ORM models in infrastructure/database/orm/ are the PERSISTENCE layer.
They are separate from domain models in domain/. The application layer
converts between the two as needed.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared SQLAlchemy declarative base for all ORM models."""
    pass
