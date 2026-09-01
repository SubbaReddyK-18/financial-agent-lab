"""
domain/intelligence/models/context.py

RecoveryContext domain model representing the full decision context available
when evaluating recovery actions for a failed or at-risk payment.

ARCHITECTURAL PRINCIPLES (P-01, P-03, Block 3):
- Pure Python model with zero framework dependencies.
- Every feature has a clear economic/operational justification.
- Captures payment, customer profile, merchant policy, and temporal state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import PaymentMethod, RecoveryActionType


@dataclass(frozen=True)
class CustomerProfile:
    """
    Historical behavioral profile of the customer.

    Attributes:
        customer_id: Unique customer ID.
        historical_payment_count: Total past payment attempts.
        historical_success_rate: Ratio of past successful payments (0.0 to 1.0).
        historical_failure_rate: Ratio of past failed payments (0.0 to 1.0).
        prior_interventions_count: Number of times this customer received recovery interventions.
        prior_recovery_success_rate: Ratio of interventions that resulted in successful payment.
        customer_segment: Segment classification (e.g. 'VIP', 'RETURNING', 'NEW', 'AT_RISK').
    """

    customer_id: uuid.UUID
    historical_payment_count: int = 1
    historical_success_rate: float = 0.85
    historical_failure_rate: float = 0.15
    prior_interventions_count: int = 0
    prior_recovery_success_rate: float = 0.50
    customer_segment: str = "RETURNING"

    def __post_init__(self) -> None:
        if not (0.0 <= self.historical_success_rate <= 1.0):
            raise ValueError(f"historical_success_rate must be between 0.0 and 1.0, got {self.historical_success_rate}")
        if not (0.0 <= self.historical_failure_rate <= 1.0):
            raise ValueError(f"historical_failure_rate must be between 0.0 and 1.0, got {self.historical_failure_rate}")
        if self.prior_interventions_count < 0:
            raise ValueError("prior_interventions_count cannot be negative")


@dataclass(frozen=True)
class PaymentFailureDetails:
    """
    Specifics of the failed payment.

    Attributes:
        payment_id: Internal Payment UUID.
        amount_minor: Authoritative monetary amount in minor units (paise).
        currency: ISO 4217 code (default INR).
        payment_method: Payment method used (UPI, CARD, NETBANKING, etc.).
        attempt_count: Number of network/gateway attempts already made.
        failure_code: Standardized error code (e.g. 'GATEWAY_TIMEOUT', 'INSUFFICIENT_FUNDS', 'AUTH_DECLINED').
        failure_reason: Detailed descriptive error from issuer/network.
        failed_at: Timestamp when the failure occurred.
    """

    payment_id: uuid.UUID
    amount_minor: int
    currency: str = "INR"
    payment_method: PaymentMethod = PaymentMethod.UPI
    attempt_count: int = 1
    failure_code: str = "GATEWAY_TIMEOUT"
    failure_reason: Optional[str] = None
    failed_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not isinstance(self.amount_minor, int):
            raise TypeError("amount_minor must be an integer (FS-01).")
        if self.amount_minor <= 0:
            raise ValueError("amount_minor must be positive.")
        if self.attempt_count <= 0:
            raise ValueError("attempt_count must be at least 1.")


@dataclass(frozen=True)
class TemporalContext:
    """
    Temporal conditions when the recovery decision is being made.

    Attributes:
        current_time: UTC timestamp.
        hour_of_day: Hour (0-23) in merchant/customer local time.
        day_of_week: Day (0=Mon, 6=Sun).
        time_since_failure_seconds: Elapsed seconds since failure.
        is_cooldown_active: Whether policy-mandated cooldown is currently active.
    """

    current_time: datetime
    hour_of_day: int = 14
    day_of_week: int = 2
    time_since_failure_seconds: int = 60
    is_cooldown_active: bool = False

    def is_business_hours(self) -> bool:
        """Standard customer notification window (9 AM to 9 PM)."""
        return 9 <= self.hour_of_day <= 21


@dataclass(frozen=True)
class RecoveryContext:
    """
    Full context passed to the Economic Engine and Decision Providers.

    Combines:
    - Failed payment details
    - Customer history
    - Merchant policy
    - Prior completed interventions
    - Temporal context
    """

    payment: PaymentFailureDetails
    customer: CustomerProfile
    policy: MerchantRecoveryPolicy
    completed_interventions: int = 0
    last_action_at: Optional[datetime] = None
    temporal: Optional[TemporalContext] = None

    def __post_init__(self) -> None:
        if self.completed_interventions < 0:
            raise ValueError("completed_interventions cannot be negative.")

    @property
    def amount_minor(self) -> int:
        return self.payment.amount_minor

    @property
    def is_high_value(self) -> bool:
        return self.policy.is_high_value(self.amount_minor)
