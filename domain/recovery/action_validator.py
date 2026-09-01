"""
domain/recovery/action_validator.py

Deterministic recovery action validation.

This module is the decision-gate before any recovery action can be executed.
It combines:
  1. State machine validation (is the case in a state that allows actions?)
  2. Action-specific rules (e.g. WAIT doesn't need policy check)
  3. Policy validation (P-03 deterministic control layer)

ARCHITECTURAL RULE (P-03):
    The AI may propose an action. This validator must approve it.
    If this validator rejects the action, execution does NOT proceed,
    regardless of AI confidence.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from domain.policies.models import MerchantRecoveryPolicy
from domain.policies.validator import (
    PolicyValidationResult,
    validate_action_against_policy,
)
from domain.recovery.models import RecoveryCase
from domain.recovery.state_machine import validate_case_transition
from domain.shared.enums import RecoveryActionType, RecoveryCaseStatus
from domain.shared.errors import InvalidStateTransitionError


# ---------------------------------------------------------------------------
# Input / output types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ActionValidationRequest:
    """
    Input to validate_recovery_action().

    Attributes:
        case:                      The RecoveryCase the action targets.
        action_type:               The proposed action type.
        policy:                    The merchant's recovery policy.
        completed_interventions:   Actions already completed on this case.
        last_action_at:            UTC timestamp of the most recent action, or None.
        requested_discount_percent:Optional discount the action offers (integer %).
        now:                       Current UTC time (injectable for testing).
    """

    case: RecoveryCase
    action_type: RecoveryActionType
    policy: MerchantRecoveryPolicy
    completed_interventions: int
    last_action_at: Optional[datetime] = None
    requested_discount_percent: Optional[int] = None
    now: Optional[datetime] = None


@dataclass(frozen=True)
class ActionValidationResult:
    """
    Immutable result of action validation.

    Attributes:
        is_valid:          True if the action may proceed (after any approval).
        violations:        List of rejection reasons (empty when is_valid=True).
        requires_approval: True if the action is permitted but needs human approval.
        policy_result:     The underlying PolicyValidationResult.
    """

    is_valid: bool
    violations: list[str] = field(default_factory=list)
    requires_approval: bool = False
    policy_result: Optional[PolicyValidationResult] = None

    @classmethod
    def ok(
        cls,
        requires_approval: bool = False,
        policy_result: Optional[PolicyValidationResult] = None,
    ) -> ActionValidationResult:
        return cls(
            is_valid=True,
            violations=[],
            requires_approval=requires_approval,
            policy_result=policy_result,
        )

    @classmethod
    def fail(
        cls,
        *violations: str,
        policy_result: Optional[PolicyValidationResult] = None,
    ) -> ActionValidationResult:
        return cls(
            is_valid=False,
            violations=list(violations),
            policy_result=policy_result,
        )


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_recovery_action(
    request: ActionValidationRequest,
) -> ActionValidationResult:
    """
    Deterministically validate a proposed recovery action.

    Checks (in order):
    1. The RecoveryCase must be in an actionable state (OPEN or IN_PROGRESS).
    2. Policy validation (interventions, cooldown, discount).
    3. High-value approval gate.

    Args:
        request: ActionValidationRequest with all required context.

    Returns:
        ActionValidationResult — always returned, never raises for policy
        violations. InvalidStateTransitionError may raise for structural
        state errors (indicates a programming error, not a user error).
    """
    now = request.now or datetime.now(tz=timezone.utc)
    case = request.case

    # ------------------------------------------------------------------
    # Check 1: Case must be actionable
    # ------------------------------------------------------------------
    if not case.is_open():
        return ActionValidationResult.fail(
            f"RecoveryCase {case.id} is in terminal state {case.status!r} "
            "and cannot accept new actions."
        )

    # ------------------------------------------------------------------
    # Check 2: WAIT is always structurally valid (no financial side effect).
    #          Still run policy check for intervention count / cooldown.
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Check 3: Policy validation
    # ------------------------------------------------------------------
    policy_result = validate_action_against_policy(
        policy=request.policy,
        action_type=request.action_type,
        payment_amount_minor=case.amount_at_risk_minor,
        completed_interventions=request.completed_interventions,
        last_action_at=request.last_action_at,
        requested_discount_percent=request.requested_discount_percent,
        now=now,
    )

    if not policy_result.is_valid:
        return ActionValidationResult.fail(
            *policy_result.violations,
            policy_result=policy_result,
        )

    return ActionValidationResult.ok(
        requires_approval=policy_result.requires_approval,
        policy_result=policy_result,
    )
