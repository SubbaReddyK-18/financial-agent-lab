"""
domain/customers/models.py

Customer domain entity.

A Customer is scoped to a Merchant. The same real-world person may exist
as separate Customer records under different merchants.

external_reference stores the merchant's own customer identifier
(e.g. their internal user ID) for correlation. It is nullable because
not all payment flows require a pre-registered customer.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class Customer:
    """
    Domain entity representing a merchant's customer.

    Attributes:
        id:                 Globally unique identifier (UUID).
        merchant_id:        The Merchant this customer belongs to.
        external_reference: Merchant-assigned customer identifier (optional).
        created_at:         Record creation timestamp (UTC).
        updated_at:         Last modification timestamp (UTC).
    """

    merchant_id: uuid.UUID
    external_reference: str | None = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __repr__(self) -> str:
        return (
            f"Customer(id={self.id}, merchant_id={self.merchant_id}, "
            f"external_reference={self.external_reference!r})"
        )
