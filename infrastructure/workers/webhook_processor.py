"""
infrastructure/workers/webhook_processor.py

Asynchronous processor for Razorpay webhook inbox events.

ARCHITECTURAL RULES (Block 2, Steps 6-12):
1. Uses Block 1 `reconcile_payment_state(...)` deterministically.
2. Emits append-only `FinancialEventORM` audit records for all state transitions.
3. Manages `RecoveryCaseORM` lifecycle:
   - Opens recovery case upon `payment.failed` (only if payment is not already captured).
   - Resolves/closes recovery case upon subsequent `payment.captured`.
4. Guarantees idempotency and safe recovery transitions.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from domain.payments.state_machine import reconcile_payment_state
from domain.shared.enums import (
    AggregateType,
    FinancialEventType,
    OrderStatus,
    PaymentAttemptStatus,
    PaymentStatus,
    RecoveryCaseStatus,
)
from domain.shared.errors import InvalidStateTransitionError
from infrastructure.database.orm.events import FinancialEventORM
from infrastructure.database.orm.payment import OrderORM, PaymentAttemptORM, PaymentORM
from infrastructure.database.orm.recovery import RecoveryCaseORM
from infrastructure.database.orm.decision_request import RecoveryDecisionRequestORM
from infrastructure.database.orm.webhook import RazorpayWebhookEventORM
from infrastructure.gateways.razorpay.parser import (
    ParsedPaymentEntity,
    ParsedRazorpayEvent,
    RazorpayPayloadError,
    parse_razorpay_webhook_payload,
)

logger = logging.getLogger("infrastructure.workers.processor")


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


@dataclass(frozen=True)
class ProcessingResult:
    success: bool
    event_id: str
    payment_id: Optional[uuid.UUID] = None
    target_payment_status: Optional[str] = None
    state_changed: bool = False
    recovery_case_id: Optional[uuid.UUID] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class AuthoritativePaymentMatch:
    """Result of resolving a webhook payment to internal financial authority."""

    payment: PaymentORM | None
    order: OrderORM | None
    quarantine_reason: str | None = None


def _validate_authoritative_payment_match(
    payment: PaymentORM,
    order: OrderORM,
    pay: ParsedPaymentEntity,
) -> AuthoritativePaymentMatch:
    """Reject webhook facts that conflict with the merchant's durable amount record."""
    if payment.order_id != order.id:
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="internal payment/order relationship is inconsistent",
        )
    if payment.amount_minor != order.amount_minor:
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="internal payment and order amounts disagree",
        )
    if payment.amount_minor != pay.amount_minor:
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="webhook amount conflicts with authoritative internal amount",
        )
    if payment.currency != order.currency or payment.currency != pay.currency:
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="webhook currency conflicts with authoritative internal currency",
        )
    return AuthoritativePaymentMatch(payment=payment, order=order)


async def _find_authoritative_payment(
    session: AsyncSession,
    pay: ParsedPaymentEntity,
) -> AuthoritativePaymentMatch:
    """
    Resolve a webhook only to an already-created internal payment/order pair.

    Razorpay webhook amounts are authenticated event facts, but they are not
    merchant financial authority.  In particular, this worker never creates
    an order or payment from a webhook amount.  An unmatched or ambiguous
    event remains durably quarantined for reconciliation instead.
    """
    # Match by the external payment ID first. Lock the record because the
    # subsequent reconciliation may mutate its lifecycle state.
    payment = await session.scalar(
        select(PaymentORM)
        .where(PaymentORM.razorpay_payment_id == pay.razorpay_payment_id)
        .with_for_update()
    )
    if payment is not None:
        order = await session.scalar(
            select(OrderORM).where(OrderORM.id == payment.order_id).with_for_update()
        )
        if order is None:
            return AuthoritativePaymentMatch(
                payment=None,
                order=None,
                quarantine_reason="matched payment has no internal order",
            )
        return _validate_authoritative_payment_match(payment, order, pay)

    # A known order may associate a previously registered internal payment
    # with its Razorpay payment ID, but only if the association is unambiguous.
    if not pay.razorpay_order_id:
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="no authoritative payment or order identifier matched",
        )

    order = await session.scalar(
        select(OrderORM)
        .where(OrderORM.razorpay_order_id == pay.razorpay_order_id)
        .with_for_update()
    )
    if order is None:
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="no authoritative internal order matched the webhook",
        )

    payments = (
        await session.scalars(
            select(PaymentORM)
            .where(PaymentORM.order_id == order.id)
            .with_for_update()
        )
    ).all()
    if len(payments) != 1:
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="authoritative order has no unique internal payment match",
        )

    payment = payments[0]
    if payment.razorpay_payment_id not in (None, pay.razorpay_payment_id):
        return AuthoritativePaymentMatch(
            payment=None,
            order=None,
            quarantine_reason="internal payment is already bound to a different Razorpay payment ID",
        )

    match = _validate_authoritative_payment_match(payment, order, pay)
    if match.payment is not None:
        # This binds identity only; amount and currency remain internal facts.
        payment.razorpay_payment_id = pay.razorpay_payment_id
    return match


async def process_single_webhook_event(
    event: RazorpayWebhookEventORM,
    session: AsyncSession,
) -> ProcessingResult:
    """
    Process a single persisted Razorpay webhook inbox event.

    Transitions:
    - Parses payload.
    - Reconciles payment state.
    - Emits financial event.
    - Creates or closes recovery case.
    - Updates processing_status to PROCESSED, FAILED, or QUARANTINED.
    """
    event.processing_status = "PROCESSING"
    await session.flush()

    try:
        parsed_event: ParsedRazorpayEvent = parse_razorpay_webhook_payload(
            payload_dict=event.payload,
            event_id_header=event.razorpay_event_id,
        )
    except RazorpayPayloadError as e:
        event.processing_status = "FAILED"
        event.error_message = f"Parse error: {e}"
        event.processed_at = _utcnow()
        await session.flush()
        return ProcessingResult(
            success=False,
            event_id=event.razorpay_event_id,
            error_message=str(e),
        )

    # If payload doesn't contain a payment entity (e.g. ping/test event), mark as processed
    if not parsed_event.payment:
        event.processing_status = "PROCESSED"
        event.processed_at = _utcnow()
        await session.flush()
        return ProcessingResult(
            success=True,
            event_id=event.razorpay_event_id,
        )

    pay = parsed_event.payment

    # 1. Resolve the event against an authoritative internal payment/order.
    # A verified webhook must never create financial authority from its amount.
    authoritative_match = await _find_authoritative_payment(session, pay)
    if authoritative_match.payment is None or authoritative_match.order is None:
        event.processing_status = "QUARANTINED"
        event.error_message = (
            "RECONCILIATION_REQUIRED: "
            f"{authoritative_match.quarantine_reason or 'no authoritative financial match'}"
        )
        event.processed_at = _utcnow()
        await session.flush()
        return ProcessingResult(
            success=True,
            event_id=event.razorpay_event_id,
            error_message=event.error_message,
        )

    payment_orm = authoritative_match.payment
    order_orm = authoritative_match.order

    # 2. Reconcile Payment state using Block 1 deterministic reconciliation API
    current_status = PaymentStatus(payment_orm.status)
    incoming_status = pay.status

    try:
        rec_result = reconcile_payment_state(
            current=current_status,
            incoming=incoming_status,
        )
    except InvalidStateTransitionError as e:
        # Invalid state downgrade (e.g. CAPTURED -> FAILED) rejected by state machine
        logger.warning(
            "Rejected forbidden payment state transition for event %r: %s",
            event.razorpay_event_id,
            e,
        )
        event.processing_status = "PROCESSED"  # Processed and rejected per business rules
        event.error_message = f"State transition rejected: {e}"
        event.processed_at = _utcnow()
        await session.flush()
        return ProcessingResult(
            success=True,
            event_id=event.razorpay_event_id,
            payment_id=payment_orm.id,
            target_payment_status=payment_orm.status,
            state_changed=False,
            error_message=str(e),
        )

    # 3. Apply state mutation if changed
    if rec_result.state_changed:
        payment_orm.status = rec_result.target_status.value
        payment_orm.updated_at = _utcnow()
        if pay.payment_method:
            payment_orm.payment_method = pay.payment_method.value

        if rec_result.target_status == PaymentStatus.CAPTURED:
            order_orm.status = OrderStatus.COMPLETED.value
            order_orm.updated_at = _utcnow()

    # 4. Record Payment Attempt
    existing_attempts = (
        await session.scalars(
            select(PaymentAttemptORM.attempt_number).where(
                PaymentAttemptORM.payment_id == payment_orm.id
            )
        )
    ).all()
    next_number = (max(existing_attempts) + 1) if existing_attempts else 1

    attempt_status = (
        PaymentAttemptStatus.FAILED
        if incoming_status == PaymentStatus.FAILED
        else PaymentAttemptStatus.SUCCESS
    )
    attempt = PaymentAttemptORM(
        id=uuid.uuid4(),
        payment_id=payment_orm.id,
        attempt_number=next_number,
        status=attempt_status.value,
        failure_code=pay.error_code if attempt_status == PaymentAttemptStatus.FAILED else None,
        failure_reason=pay.error_description if attempt_status == PaymentAttemptStatus.FAILED else None,
        attempted_at=parsed_event.event_created_at or _utcnow(),
    )
    session.add(attempt)

    # 5. Append-only Financial Event emission (FS-07, Step 12)
    fin_event_type = f"PAYMENT_{rec_result.target_status.value}"
    fin_event = FinancialEventORM(
        id=uuid.uuid4(),
        event_type=fin_event_type,
        aggregate_type=AggregateType.PAYMENT.value,
        aggregate_id=str(payment_orm.id),
        occurred_at=parsed_event.event_created_at or _utcnow(),
        payload={
            "razorpay_event_id": parsed_event.event_id,
            "razorpay_payment_id": pay.razorpay_payment_id,
            "razorpay_order_id": pay.razorpay_order_id,
            # Amount/currency are intentionally sourced from the already
            # matched merchant record, never directly from the webhook.
            "amount_minor": payment_orm.amount_minor,
            "currency": payment_orm.currency,
            "status": rec_result.target_status.value,
            "state_changed": rec_result.state_changed,
            "is_reconciled_from_failed": rec_result.is_reconciled_from_failed,
        },
        correlation_id=event.correlation_id,
    )
    session.add(fin_event)

    # 6. Recovery Case Lifecycle Management (Step 11)
    recovery_case_id: Optional[uuid.UUID] = None

    # Scenario A: Payment is FAILED -> Open a RecoveryCase (if not already captured and no open case)
    if payment_orm.status == PaymentStatus.FAILED.value:
        active_case = await session.scalar(
            select(RecoveryCaseORM).where(
                RecoveryCaseORM.payment_id == payment_orm.id,
                RecoveryCaseORM.status.in_([
                    RecoveryCaseStatus.OPEN.value,
                    RecoveryCaseStatus.IN_PROGRESS.value,
                ]),
            )
        )
        if active_case is None:
            new_case = RecoveryCaseORM(
                id=uuid.uuid4(),
                merchant_id=payment_orm.order.merchant_id if payment_orm.order else order_orm.merchant_id,
                customer_id=payment_orm.customer_id,
                payment_id=payment_orm.id,
                amount_at_risk_minor=payment_orm.amount_minor,
                status=RecoveryCaseStatus.OPEN.value,
                opened_at=_utcnow(),
            )
            session.add(new_case)
            recovery_case_id = new_case.id
            # Decisioning is deliberately deferred to a worker after this
            # reconciliation transaction commits; no LLM runs here.
            session.add(RecoveryDecisionRequestORM(
                id=uuid.uuid4(), recovery_case_id=new_case.id, payment_id=payment_orm.id,
                idempotency_key=f"decision_request:{new_case.id}:OPEN",
                correlation_id=event.correlation_id,
            ))

            # Emit RECOVERY_CASE_OPENED event
            case_event = FinancialEventORM(
                id=uuid.uuid4(),
                event_type=FinancialEventType.RECOVERY_CASE_OPENED.value,
                aggregate_type=AggregateType.RECOVERY_CASE.value,
                aggregate_id=str(new_case.id),
                occurred_at=_utcnow(),
                payload={
                    "payment_id": str(payment_orm.id),
                    "amount_at_risk_minor": payment_orm.amount_minor,
                    "razorpay_event_id": parsed_event.event_id,
                },
                correlation_id=event.correlation_id,
            )
            session.add(case_event)
        else:
            recovery_case_id = active_case.id

    # Scenario B: Payment is CAPTURED -> Resolve active RecoveryCase
    elif payment_orm.status == PaymentStatus.CAPTURED.value:
        active_case = await session.scalar(
            select(RecoveryCaseORM).where(
                RecoveryCaseORM.payment_id == payment_orm.id,
                RecoveryCaseORM.status.in_([
                    RecoveryCaseStatus.OPEN.value,
                    RecoveryCaseStatus.IN_PROGRESS.value,
                ]),
            )
        )
        if active_case is not None:
            active_case.status = RecoveryCaseStatus.RECOVERED.value
            active_case.closed_at = _utcnow()
            recovery_case_id = active_case.id

            # Emit RECOVERY_CASE_CLOSED event
            case_closed_event = FinancialEventORM(
                id=uuid.uuid4(),
                event_type=FinancialEventType.RECOVERY_CASE_CLOSED.value,
                aggregate_type=AggregateType.RECOVERY_CASE.value,
                aggregate_id=str(active_case.id),
                occurred_at=_utcnow(),
                payload={
                    "payment_id": str(payment_orm.id),
                    "resolution": "RECOVERED_VIA_LATE_CAPTURE",
                    "razorpay_event_id": parsed_event.event_id,
                },
                correlation_id=event.correlation_id,
            )
            session.add(case_closed_event)

    # 7. Finalize webhook event record
    event.processing_status = "PROCESSED"
    event.processed_at = _utcnow()
    event.error_message = None
    await session.flush()

    return ProcessingResult(
        success=True,
        event_id=event.razorpay_event_id,
        payment_id=payment_orm.id,
        target_payment_status=payment_orm.status,
        state_changed=rec_result.state_changed,
        recovery_case_id=recovery_case_id,
    )
