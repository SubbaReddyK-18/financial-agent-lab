"""
tests/unit/test_policy.py

Unit tests for merchant recovery policy validation.

Tests cover: discount limits, intervention limits, cooldown enforcement,
high-value approval gate, and combined validation scenarios.

All validation is deterministic — no LLM, no randomness, no I/O.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from domain.policies.models import MerchantRecoveryPolicy
from domain.policies.validator import (
    PolicyValidationResult,
    validate_action_against_policy,
)
from domain.recovery.action_validator import (
    ActionValidationRequest,
    validate_recovery_action,
)
from domain.recovery.models import RecoveryCase
from domain.shared.enums import RecoveryActionType, RecoveryCaseStatus


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _policy(**kwargs) -> MerchantRecoveryPolicy:
    defaults = dict(
        merchant_id=uuid.uuid4(),
        maximum_discount_percent=10,
        maximum_interventions=3,
        cooldown_hours=1,
        high_value_threshold_minor=1_000_000,  # ₹10,000
        high_value_requires_approval=False,
        low_confidence_requires_review=False,
    )
    defaults.update(kwargs)
    return MerchantRecoveryPolicy(**defaults)


def _case(amount_minor: int = 500_000) -> RecoveryCase:
    return RecoveryCase(
        merchant_id=uuid.uuid4(),
        customer_id=uuid.uuid4(),
        payment_id=uuid.uuid4(),
        amount_at_risk_minor=amount_minor,
        status=RecoveryCaseStatus.OPEN,
    )


# ---------------------------------------------------------------------------
# Policy model validation
# ---------------------------------------------------------------------------

class TestPolicyModelValidation:
    def test_valid_policy(self):
        p = _policy()
        assert p.maximum_discount_percent == 10

    def test_discount_above_100_rejected(self):
        with pytest.raises(ValueError, match="maximum_discount_percent"):
            _policy(maximum_discount_percent=101)

    def test_negative_discount_rejected(self):
        with pytest.raises(ValueError):
            _policy(maximum_discount_percent=-1)

    def test_zero_discount_allowed(self):
        p = _policy(maximum_discount_percent=0)
        assert p.maximum_discount_percent == 0

    def test_maximum_interventions_zero_rejected(self):
        with pytest.raises(ValueError, match="maximum_interventions"):
            _policy(maximum_interventions=0)

    def test_negative_cooldown_rejected(self):
        with pytest.raises(ValueError, match="cooldown_hours"):
            _policy(cooldown_hours=-1)

    def test_float_high_value_threshold_rejected(self):
        with pytest.raises(TypeError):
            _policy(high_value_threshold_minor=10000.50)  # type: ignore[arg-type]

    def test_zero_high_value_threshold_rejected(self):
        with pytest.raises(ValueError):
            _policy(high_value_threshold_minor=0)

    def test_is_high_value_above_threshold(self):
        p = _policy(high_value_threshold_minor=1_000_000)
        assert p.is_high_value(1_000_000)
        assert p.is_high_value(1_500_000)

    def test_is_high_value_below_threshold(self):
        p = _policy(high_value_threshold_minor=1_000_000)
        assert not p.is_high_value(999_999)

    def test_is_high_value_no_threshold(self):
        p = _policy(high_value_threshold_minor=None)
        assert not p.is_high_value(99_999_999)


# ---------------------------------------------------------------------------
# Discount limit validation
# ---------------------------------------------------------------------------

class TestDiscountLimits:
    def test_discount_within_limit_passes(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_discount_percent=10),
            action_type=RecoveryActionType.PAYMENT_LINK,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
            requested_discount_percent=10,
        )
        assert result.is_valid

    def test_discount_at_zero_passes_with_zero_policy(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_discount_percent=0),
            action_type=RecoveryActionType.PAYMENT_LINK,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
            requested_discount_percent=0,
        )
        assert result.is_valid

    def test_discount_exceeds_limit_fails(self):
        """Constitution example: policy max=10%, requesting 15% must be rejected."""
        result = validate_action_against_policy(
            policy=_policy(maximum_discount_percent=10),
            action_type=RecoveryActionType.PAYMENT_LINK,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
            requested_discount_percent=15,
        )
        assert not result.is_valid
        assert any("15%" in v for v in result.violations)

    def test_discount_just_above_limit_fails(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_discount_percent=10),
            action_type=RecoveryActionType.PAYMENT_LINK,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
            requested_discount_percent=11,
        )
        assert not result.is_valid

    def test_discount_just_below_limit_passes(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_discount_percent=10),
            action_type=RecoveryActionType.PAYMENT_LINK,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
            requested_discount_percent=9,
        )
        assert result.is_valid

    def test_negative_discount_fails(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_discount_percent=10),
            action_type=RecoveryActionType.PAYMENT_LINK,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
            requested_discount_percent=-1,
        )
        assert not result.is_valid


# ---------------------------------------------------------------------------
# Intervention limit validation
# ---------------------------------------------------------------------------

class TestInterventionLimits:
    def test_first_intervention_passes(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_interventions=3),
            action_type=RecoveryActionType.RETRY,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
        )
        assert result.is_valid

    def test_at_limit_fails(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_interventions=3),
            action_type=RecoveryActionType.RETRY,
            payment_amount_minor=500_000,
            completed_interventions=3,
            last_action_at=None,
        )
        assert not result.is_valid
        assert any("3" in v for v in result.violations)

    def test_just_below_limit_passes(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_interventions=3),
            action_type=RecoveryActionType.RETRY,
            payment_amount_minor=500_000,
            completed_interventions=2,
            last_action_at=None,
        )
        assert result.is_valid

    def test_above_limit_fails(self):
        result = validate_action_against_policy(
            policy=_policy(maximum_interventions=3),
            action_type=RecoveryActionType.RETRY,
            payment_amount_minor=500_000,
            completed_interventions=5,
            last_action_at=None,
        )
        assert not result.is_valid


# ---------------------------------------------------------------------------
# Cooldown validation
# ---------------------------------------------------------------------------

class TestCooldownValidation:
    def test_no_previous_action_passes(self):
        result = validate_action_against_policy(
            policy=_policy(cooldown_hours=24),
            action_type=RecoveryActionType.NOTIFY,
            payment_amount_minor=500_000,
            completed_interventions=0,
            last_action_at=None,
        )
        assert result.is_valid

    def test_within_cooldown_fails(self):
        last = _now() - timedelta(hours=2)
        result = validate_action_against_policy(
            policy=_policy(cooldown_hours=24),
            action_type=RecoveryActionType.NOTIFY,
            payment_amount_minor=500_000,
            completed_interventions=1,
            last_action_at=last,
            now=_now(),
        )
        assert not result.is_valid
        assert any("cooldown" in v.lower() or "hour" in v.lower() for v in result.violations)

    def test_after_cooldown_passes(self):
        last = _now() - timedelta(hours=25)
        result = validate_action_against_policy(
            policy=_policy(cooldown_hours=24),
            action_type=RecoveryActionType.NOTIFY,
            payment_amount_minor=500_000,
            completed_interventions=1,
            last_action_at=last,
            now=_now(),
        )
        assert result.is_valid

    def test_exactly_at_cooldown_boundary_passes(self):
        last = _now() - timedelta(hours=24, seconds=1)
        result = validate_action_against_policy(
            policy=_policy(cooldown_hours=24),
            action_type=RecoveryActionType.NOTIFY,
            payment_amount_minor=500_000,
            completed_interventions=1,
            last_action_at=last,
            now=_now(),
        )
        assert result.is_valid

    def test_zero_cooldown_always_passes(self):
        last = _now() - timedelta(seconds=1)
        result = validate_action_against_policy(
            policy=_policy(cooldown_hours=0),
            action_type=RecoveryActionType.NOTIFY,
            payment_amount_minor=500_000,
            completed_interventions=1,
            last_action_at=last,
            now=_now(),
        )
        assert result.is_valid


# ---------------------------------------------------------------------------
# High-value approval gate
# ---------------------------------------------------------------------------

class TestHighValueApproval:
    def test_high_value_requires_approval_flag(self):
        result = validate_action_against_policy(
            policy=_policy(
                high_value_threshold_minor=1_000_000,
                high_value_requires_approval=True,
            ),
            action_type=RecoveryActionType.RETRY,
            payment_amount_minor=1_500_000,   # above threshold
            completed_interventions=0,
            last_action_at=None,
        )
        assert result.is_valid
        assert result.requires_approval

    def test_below_threshold_does_not_require_approval(self):
        result = validate_action_against_policy(
            policy=_policy(
                high_value_threshold_minor=1_000_000,
                high_value_requires_approval=True,
            ),
            action_type=RecoveryActionType.RETRY,
            payment_amount_minor=500_000,   # below threshold
            completed_interventions=0,
            last_action_at=None,
        )
        assert result.is_valid
        assert not result.requires_approval

    def test_wait_action_does_not_require_approval_even_on_high_value(self):
        result = validate_action_against_policy(
            policy=_policy(
                high_value_threshold_minor=1_000_000,
                high_value_requires_approval=True,
            ),
            action_type=RecoveryActionType.WAIT,
            payment_amount_minor=2_000_000,
            completed_interventions=0,
            last_action_at=None,
        )
        assert result.is_valid
        assert not result.requires_approval


# ---------------------------------------------------------------------------
# Combined action validator (case state + policy)
# ---------------------------------------------------------------------------

class TestActionValidator:
    def test_valid_action_on_open_case(self):
        from domain.recovery.action_validator import ActionValidationRequest, validate_recovery_action
        case = _case()
        policy = _policy()
        req = ActionValidationRequest(
            case=case,
            action_type=RecoveryActionType.RETRY,
            policy=policy,
            completed_interventions=0,
        )
        result = validate_recovery_action(req)
        assert result.is_valid

    def test_action_on_closed_case_fails(self):
        from datetime import datetime, timezone
        from domain.recovery.action_validator import ActionValidationRequest, validate_recovery_action
        closed_case = RecoveryCase(
            merchant_id=uuid.uuid4(),
            customer_id=uuid.uuid4(),
            payment_id=uuid.uuid4(),
            amount_at_risk_minor=500_000,
            status=RecoveryCaseStatus.CLOSED,
            closed_at=datetime.now(tz=timezone.utc),
        )
        policy = _policy()
        req = ActionValidationRequest(
            case=closed_case,
            action_type=RecoveryActionType.RETRY,
            policy=policy,
            completed_interventions=0,
        )
        result = validate_recovery_action(req)
        assert not result.is_valid
        assert any("CLOSED" in v or "terminal" in v for v in result.violations)

    def test_policy_violation_propagates(self):
        from domain.recovery.action_validator import ActionValidationRequest, validate_recovery_action
        case = _case()
        policy = _policy(maximum_discount_percent=5)
        req = ActionValidationRequest(
            case=case,
            action_type=RecoveryActionType.PAYMENT_LINK,
            policy=policy,
            completed_interventions=0,
            requested_discount_percent=10,  # violates policy
        )
        result = validate_recovery_action(req)
        assert not result.is_valid

    def test_multiple_violations_are_all_reported(self):
        from domain.recovery.action_validator import ActionValidationRequest, validate_recovery_action
        case = _case()
        # Exceed both intervention limit AND discount limit
        policy = _policy(maximum_interventions=1, maximum_discount_percent=5)
        req = ActionValidationRequest(
            case=case,
            action_type=RecoveryActionType.PAYMENT_LINK,
            policy=policy,
            completed_interventions=1,   # at limit
            requested_discount_percent=10,   # over limit
        )
        result = validate_recovery_action(req)
        assert not result.is_valid
        assert len(result.violations) >= 2
