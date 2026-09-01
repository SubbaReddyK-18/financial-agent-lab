"""
domain/recovery/models.py

RecoveryCase and RecoveryAction domain entities.

RecoveryCase: Represents an active revenue-recovery opportunity for a
              failed (or at-risk) payment.

RecoveryAction: Represents a proposed or executed action taken (or to be
                taken) to recover a payment.

Design notes:
- One Payment may have at most one OPEN RecoveryCase (enforced by service layer).
- One RecoveryCase may have many RecoveryActions over its lifetime.
- action metadata is a flexible dict for action-specific context
  (e.g. payment link URL, notification channel used).
- discount_percent_offered is surfaced explicitly on RecoveryAction so that
  policy validation can check it without parsing opaque metadata.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from domain.shared.enums import (
    RecoveryActionStatus,
    RecoveryActionType,
    RecoveryCaseStatus,
)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------------------
# RecoveryCase
# ---------------------------------------------------------------------------

@dataclass
class RecoveryCase:
    """
    A revenue-recovery opportunity for a failed payment.

    Lifecycle: OPEN → IN_PROGRESS → RECOVERED | IRRECOVERABLE → CLOSED
    (see domain/recovery/state_machine.py)

    Attributes:
        id:                   Globally unique identifier (UUID).
        merchant_id:          Owning merchant.
        customer_id:          The customer who owns the payment.
        payment_id:           The failed/at-risk payment being recovered.
        amount_at_risk_minor: Original payment amount in minor units.
        status:               Current RecoveryCaseStatus.
        opened_at:            When the case was created (UTC).
        closed_at:            When the case was resolved (UTC), or None if open.
    """

    merchant_id: uuid.UUID
    customer_id: uuid.UUID
    payment_id: uuid.UUID
    amount_at_risk_minor: int
    status: RecoveryCaseStatus = RecoveryCaseStatus.OPEN
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    opened_at: datetime = field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not isinstance(self.amount_at_risk_minor, int):
            raise TypeError(
                f"amount_at_risk_minor must be int, got {type(self.amount_at_risk_minor).__name__}. "
                "Floating-point amounts are forbidden (FS-01)."
            )
        if self.amount_at_risk_minor <= 0:
            raise ValueError(
                f"amount_at_risk_minor must be positive, got {self.amount_at_risk_minor}."
            )
        if self.closed_at is not None and self.status not in {
            RecoveryCaseStatus.RECOVERED,
            RecoveryCaseStatus.IRRECOVERABLE,
            RecoveryCaseStatus.CLOSED,
        }:
            raise ValueError(
                "closed_at may only be set when status is RECOVERED, IRRECOVERABLE, or CLOSED."
            )

    def is_open(self) -> bool:
        return self.status in {RecoveryCaseStatus.OPEN, RecoveryCaseStatus.IN_PROGRESS}

    def is_closed(self) -> bool:
        return self.status == RecoveryCaseStatus.CLOSED

    def __repr__(self) -> str:
        return (
            f"RecoveryCase(id={self.id}, payment_id={self.payment_id}, "
            f"amount_at_risk_minor={self.amount_at_risk_minor}, status={self.status!r})"
        )


# ---------------------------------------------------------------------------
# RecoveryAction
# ---------------------------------------------------------------------------

@dataclass
class RecoveryAction:
    """
    A single recovery action within a RecoveryCase.

    Actions are proposed by the agent (Block 5+) or rule engine and must
    pass policy validation before execution (P-03).

    Attributes:
        id:                      Globally unique identifier (UUID).
        recovery_case_id:        The parent RecoveryCase.
        action_type:             The type of recovery action (WAIT, RETRY, etc.).
        status:                  Current RecoveryActionStatus.
        discount_percent_offered:Explicit discount offered (if any), as integer %.
                                 Checked against policy maximum. 0 = no discount.
        metadata:                Extensible dict for action-specific data
                                 (e.g. {"payment_link_url": "...", "channel": "sms"}).
        created_at:              When the action was proposed (UTC).
        executed_at:             When execution started (UTC), or None.
    """

    recovery_case_id: uuid.UUID
    action_type: RecoveryActionType
    status: RecoveryActionStatus = RecoveryActionStatus.PROPOSED
    discount_percent_offered: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    created_at: datetime = field(default_factory=_utcnow)
    executed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not (0 <= self.discount_percent_offered <= 100):
            raise ValueError(
                f"discount_percent_offered must be 0–100, got {self.discount_percent_offered}."
            )
        if self.executed_at is not None and self.status == RecoveryActionStatus.PROPOSED:
            raise ValueError("executed_at cannot be set when status is PROPOSED.")

    def is_terminal(self) -> bool:
        return self.status in {
            RecoveryActionStatus.COMPLETED,
            RecoveryActionStatus.FAILED,
            RecoveryActionStatus.CANCELLED,
        }

    def __repr__(self) -> str:
        return (
            f"RecoveryAction(id={self.id}, case_id={self.recovery_case_id}, "
            f"type={self.action_type!r}, status={self.status!r})"
        )
