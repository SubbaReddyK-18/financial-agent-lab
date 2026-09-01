"""
domain/recovery/execution.py

Test-mode action execution implementations for Recovery Actions.

ARCHITECTURAL PRINCIPLES (Block 5, Requirement 7 & Constitutional Rules):
1. Test-mode executors do NOT perform live external money movement or capture/refunds.
2. Deterministic execution produces structured execution records suitable for simulation/auditing.
3. Every action type (WAIT, RETRY, PAYMENT_LINK, NOTIFY, ESCALATE) has a dedicated executor.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, Protocol

from domain.intelligence.models.context import RecoveryContext
from domain.shared.enums import RecoveryActionType


@dataclass(frozen=True)
class ActionExecutionResult:
    """Immutable result of a test-mode recovery action execution."""

    action_id: uuid.UUID
    action_type: RecoveryActionType
    status: str  # "COMPLETED", "FAILED", "PENDING_APPROVAL"
    execution_reference: str
    details: dict[str, Any] = field(default_factory=dict)
    is_retryable: bool = False
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    executed_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    is_test_mode: bool = True


class ActionExecutor(Protocol):
    """Protocol for recovery action executors."""

    async def execute(
        self,
        action_id: uuid.UUID,
        context: RecoveryContext,
        discount_percent: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionExecutionResult:
        ...


class WaitActionExecutor:
    """Test-mode executor for WAIT (passive observation/cooldown)."""

    async def execute(
        self,
        action_id: uuid.UUID,
        context: RecoveryContext,
        discount_percent: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionExecutionResult:
        now = datetime.now(tz=timezone.utc)
        cooldown_hours = context.policy.cooldown_hours
        resuming_at = now + timedelta(hours=cooldown_hours)

        return ActionExecutionResult(
            action_id=action_id,
            action_type=RecoveryActionType.WAIT,
            status="COMPLETED",
            execution_reference=f"TEST_WAIT_{action_id.hex[:12]}",
            details={
                "mode": "OBSERVATION",
                "cooldown_hours": cooldown_hours,
                "resuming_at": resuming_at.isoformat(),
                "reason": "Passive monitoring for organic customer retry or status update.",
            },
            executed_at=now,
            is_test_mode=True,
        )


class RetryActionExecutor:
    """Test-mode executor for RETRY (automated technical re-attempt)."""

    async def execute(
        self,
        action_id: uuid.UUID,
        context: RecoveryContext,
        discount_percent: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionExecutionResult:
        now = datetime.now(tz=timezone.utc)
        next_attempt_number = context.payment.attempt_count + 1

        return ActionExecutionResult(
            action_id=action_id,
            action_type=RecoveryActionType.RETRY,
            status="COMPLETED",
            execution_reference=f"TEST_RETRY_{action_id.hex[:12]}",
            details={
                "target_payment_id": str(context.payment.payment_id),
                "simulated_attempt_number": next_attempt_number,
                "amount_minor": context.amount_minor,
                "idempotency_key": f"retry_idem_{action_id.hex}",
                "retry_delay_seconds": 15,
            },
            executed_at=now,
            is_test_mode=True,
        )


class PaymentLinkActionExecutor:
    """Test-mode executor for PAYMENT_LINK (out-of-band checkout portal with optional discount)."""

    async def execute(
        self,
        action_id: uuid.UUID,
        context: RecoveryContext,
        discount_percent: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionExecutionResult:
        now = datetime.now(tz=timezone.utc)
        discount_amount_minor = (context.amount_minor * discount_percent) // 100
        final_amount_minor = context.amount_minor - discount_amount_minor
        token = action_id.hex[:16]

        return ActionExecutionResult(
            action_id=action_id,
            action_type=RecoveryActionType.PAYMENT_LINK,
            status="COMPLETED",
            execution_reference=f"TEST_PLINK_{token}",
            details={
                "payment_url": f"https://test-checkout.financialagentlab.local/pay/{token}",
                "original_amount_minor": context.amount_minor,
                "discount_percent": discount_percent,
                "discount_amount_minor": discount_amount_minor,
                "final_amount_minor": final_amount_minor,
                "expires_at": (now + timedelta(hours=24)).isoformat(),
            },
            executed_at=now,
            is_test_mode=True,
        )


class NotifyActionExecutor:
    """Test-mode executor for NOTIFY (customer notification alert)."""

    async def execute(
        self,
        action_id: uuid.UUID,
        context: RecoveryContext,
        discount_percent: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionExecutionResult:
        now = datetime.now(tz=timezone.utc)

        return ActionExecutionResult(
            action_id=action_id,
            action_type=RecoveryActionType.NOTIFY,
            status="COMPLETED",
            execution_reference=f"TEST_NOTIF_{action_id.hex[:12]}",
            details={
                "customer_id": str(context.customer.customer_id),
                "channels": ["SMS", "WHATSAPP"],
                "template": "PAYMENT_FAILED_GENTLE_REMINDER",
                "failure_code": context.payment.failure_code,
            },
            executed_at=now,
            is_test_mode=True,
        )


class EscalateActionExecutor:
    """Test-mode executor for ESCALATE (human support routing / high-touch outreach)."""

    async def execute(
        self,
        action_id: uuid.UUID,
        context: RecoveryContext,
        discount_percent: int = 0,
        metadata: Optional[dict[str, Any]] = None,
    ) -> ActionExecutionResult:
        now = datetime.now(tz=timezone.utc)

        return ActionExecutionResult(
            action_id=action_id,
            action_type=RecoveryActionType.ESCALATE,
            status="COMPLETED",
            execution_reference=f"TEST_TICKET_{action_id.hex[:12]}",
            details={
                "customer_id": str(context.customer.customer_id),
                "priority": "HIGH" if context.is_high_value else "MEDIUM",
                "queue": "VIP_RECOVERY_DESK" if context.customer.customer_segment == "VIP" else "CUSTOMER_SUPPORT",
                "at_risk_amount_minor": context.amount_minor,
                "sla_minutes": 30,
            },
            executed_at=now,
            is_test_mode=True,
        )


def get_action_executor(action_type: RecoveryActionType) -> ActionExecutor:
    """Factory returning the appropriate test-mode action executor."""
    executors = {
        RecoveryActionType.WAIT: WaitActionExecutor(),
        RecoveryActionType.RETRY: RetryActionExecutor(),
        RecoveryActionType.PAYMENT_LINK: PaymentLinkActionExecutor(),
        RecoveryActionType.NOTIFY: NotifyActionExecutor(),
        RecoveryActionType.ESCALATE: EscalateActionExecutor(),
    }
    if action_type not in executors:
        raise ValueError(f"No executor registered for action type: {action_type}")
    return executors[action_type]
