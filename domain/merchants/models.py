"""
domain/merchants/models.py

Merchant domain entity.

A Merchant is the top-level account holder on the Razorpay platform.
All customers, orders, and payments belong to a Merchant.
Recovery policies are defined per Merchant.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from domain.shared.enums import Currency


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class Merchant:
    """
    Domain entity representing a Razorpay merchant account.

    Attributes:
        id:         Globally unique identifier (UUID).
        name:       Merchant's display name.
        currency:   Default settlement currency (MVP: INR only).
        created_at: When this merchant record was created (UTC).
        updated_at: Last modification timestamp (UTC).
    """

    name: str
    currency: str = Currency.INR
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("Merchant name cannot be empty.")
        if self.currency not in {c.value for c in Currency}:
            raise ValueError(f"Unsupported currency: {self.currency!r}")

    def __repr__(self) -> str:
        return f"Merchant(id={self.id}, name={self.name!r}, currency={self.currency!r})"
