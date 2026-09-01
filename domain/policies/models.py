"""
domain/policies/models.py

MerchantRecoveryPolicy domain model.

A policy represents the merchant-defined constraints on what recovery
actions the system may take on their behalf. Policy limits are
enforced DETERMINISTICALLY before any action is executed (P-03, FS-05).

Design notes:
- All monetary thresholds use integer minor units (FS-01).
- discount is expressed as a whole-number percentage (0–100).
  Example: maximum_discount_percent=10 means at most 10% discount.
- Policy is intentionally simple for Block 1. Additional rules can be
  added as fields without breaking existing policy records.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass
class MerchantRecoveryPolicy:
    """
    Merchant-defined constraints for the recovery system.

    Attributes:
        merchant_id:
            The merchant this policy applies to. One merchant has at most
            one active policy (enforced at DB level).

        maximum_discount_percent:
            Maximum percentage discount the system may offer to recover a
            payment. Range: 0–100 (integer). Default: 0 (no discounts).

        maximum_interventions:
            Maximum number of recovery actions permitted per recovery case
            before the case is automatically escalated or closed.
            Default: 3.

        cooldown_hours:
            Minimum hours that must elapse between consecutive recovery
            actions on the same case. Prevents harassment.
            Default: 24.

        high_value_threshold_minor:
            Payments at or above this amount (in minor units) are considered
            "high value" and may require additional approval. None means no
            high-value threshold is active.

        high_value_requires_approval:
            If True, recovery actions on high-value payments require explicit
            approval before execution (future: human-in-the-loop gate).

        low_confidence_requires_review:
            If True, agent decisions below a confidence threshold are flagged
            for review instead of automatic execution. (Used by Block 5+.)

        id:         UUID for the policy record.
        created_at: UTC creation timestamp.
        updated_at: UTC last-modified timestamp.
    """

    merchant_id: uuid.UUID
    maximum_discount_percent: int = 0
    maximum_interventions: int = 3
    cooldown_hours: int = 24
    high_value_threshold_minor: Optional[int] = None
    high_value_requires_approval: bool = False
    low_confidence_requires_review: bool = False
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not (0 <= self.maximum_discount_percent <= 100):
            raise ValueError(
                f"maximum_discount_percent must be 0–100, got {self.maximum_discount_percent}."
            )
        if self.maximum_interventions < 1:
            raise ValueError(
                f"maximum_interventions must be >= 1, got {self.maximum_interventions}."
            )
        if self.cooldown_hours < 0:
            raise ValueError(
                f"cooldown_hours must be >= 0, got {self.cooldown_hours}."
            )
        if self.high_value_threshold_minor is not None:
            if not isinstance(self.high_value_threshold_minor, int):
                raise TypeError(
                    "high_value_threshold_minor must be an integer (minor units)."
                )
            if self.high_value_threshold_minor <= 0:
                raise ValueError(
                    "high_value_threshold_minor must be positive if set."
                )

    def is_high_value(self, amount_minor: int) -> bool:
        """Return True if the amount meets or exceeds the high-value threshold."""
        if self.high_value_threshold_minor is None:
            return False
        return amount_minor >= self.high_value_threshold_minor

    def __repr__(self) -> str:
        return (
            f"MerchantRecoveryPolicy(merchant_id={self.merchant_id}, "
            f"max_discount={self.maximum_discount_percent}%, "
            f"max_interventions={self.maximum_interventions}, "
            f"cooldown={self.cooldown_hours}h)"
        )
