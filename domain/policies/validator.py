"""
domain/policies/validator.py

Deterministic policy validation for recovery actions.

ARCHITECTURAL RULE (P-03, FS-05):
    This module is the deterministic policy gate that sits between an AI
    decision (or any action request) and actual execution.

    No action may be executed unless it passes this validation.
    The AI CANNOT override this. It is not configurable at runtime by the AI.

    Validation is pure: given the same inputs, always produces the same output.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from domain.policies.models import MerchantRecoveryPolicy
from domain.shared.enums import RecoveryActionType


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PolicyValidationResult:
    """
    Immutable result of a deterministic policy validation check.

    Attributes:
        is_valid:          True if the proposed action passes all policy rules.
        violations:        List of human-readable violation descriptions.
                           Empty when is_valid=True.
        requires_approval: True if the action is technically permitted but
                           requires human approval before execution
                           (e.g. high-value payment + policy flag).
    """

    is_valid: bool
    violations: list[str] = field(default_factory=list)
    requires_approval: bool = False

    @classmethod
    def ok(cls, requires_approval: bool = False) -> PolicyValidationResult:
        return cls(is_valid=True, violations=[], requires_approval=requires_approval)

    @classmethod
    def fail(cls, *violations: str) -> PolicyValidationResult:
        return cls(is_valid=False, violations=list(violations))


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_action_against_policy(
    *,
    policy: MerchantRecoveryPolicy,
    action_type: RecoveryActionType,
    payment_amount_minor: int,
    completed_interventions: int,
    last_action_at: Optional[datetime],
    requested_discount_percent: Optional[int] = None,
    now: Optional[datetime] = None,
) -> PolicyValidationResult:
    """
    Deterministically validate a proposed recovery action against a merchant policy.

    All checks are explicit and enumerable. No AI, no randomness.

    Args:
        policy:
            The MerchantRecoveryPolicy to validate against.
        action_type:
            The proposed RecoveryActionType.
        payment_amount_minor:
            The at-risk payment amount in minor units.
        completed_interventions:
            How many recovery actions have already been executed on this case.
        last_action_at:
            UTC timestamp of the most recent completed action, or None if no
            actions have been taken yet.
        requested_discount_percent:
            Optional discount percentage the action intends to offer.
            Must be provided when action_type == PAYMENT_LINK and a discount
            is being offered.
        now:
            Current UTC time. Injected for testability. Defaults to utcnow().

    Returns:
        PolicyValidationResult — always returned (never raises).
        Check is_valid before proceeding with execution.
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)

    violations: list[str] = []

    # ------------------------------------------------------------------
    # Rule 1: Intervention count limit
    # ------------------------------------------------------------------
    if completed_interventions >= policy.maximum_interventions:
        violations.append(
            f"Maximum interventions reached: "
            f"{completed_interventions}/{policy.maximum_interventions} already completed."
        )

    # ------------------------------------------------------------------
    # Rule 2: Cooldown period between actions
    # ------------------------------------------------------------------
    if last_action_at is not None and policy.cooldown_hours > 0:
        cooldown_expires = last_action_at + timedelta(hours=policy.cooldown_hours)
        if now < cooldown_expires:
            remaining = cooldown_expires - now
            remaining_minutes = int(remaining.total_seconds() / 60)
            violations.append(
                f"Cooldown period active: {remaining_minutes} minute(s) remaining "
                f"(policy requires {policy.cooldown_hours}h between actions)."
            )

    # ------------------------------------------------------------------
    # Rule 3: Discount limit
    # ------------------------------------------------------------------
    if requested_discount_percent is not None:
        if not isinstance(requested_discount_percent, int):
            violations.append(
                "requested_discount_percent must be an integer (whole percentage)."
            )
        elif requested_discount_percent < 0:
            violations.append(
                f"Discount percentage cannot be negative: {requested_discount_percent}."
            )
        elif requested_discount_percent > policy.maximum_discount_percent:
            violations.append(
                f"Requested discount {requested_discount_percent}% exceeds policy "
                f"maximum of {policy.maximum_discount_percent}%."
            )

    # ------------------------------------------------------------------
    # Rule 4: WAIT action is always permitted (has no financial side effect)
    # ------------------------------------------------------------------
    # (No additional restrictions on WAIT.)

    if violations:
        return PolicyValidationResult.fail(*violations)

    # ------------------------------------------------------------------
    # Approval gate: high-value payments
    # ------------------------------------------------------------------
    requires_approval = False
    if (
        policy.high_value_requires_approval
        and policy.is_high_value(payment_amount_minor)
        and action_type != RecoveryActionType.WAIT
    ):
        requires_approval = True

    return PolicyValidationResult.ok(requires_approval=requires_approval)
