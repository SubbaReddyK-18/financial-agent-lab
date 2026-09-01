"""
domain/recovery/case_service.py

Domain service: RecoveryCase creation.

This module contains the business logic for determining whether a payment
is eligible for a recovery case and constructing one if so.

It is deliberately:
- Pure Python (no DB calls, no external I/O)
- Deterministic (same inputs → same output)
- Framework-independent (no FastAPI, no SQLAlchemy, no LLM SDK)

The caller (application/service layer) is responsible for:
1. Checking that no open recovery case already exists for this payment.
2. Persisting the returned RecoveryCase to the database.
3. Emitting the RECOVERY_CASE_OPENED event (via outbox — Block 2+).

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from domain.customers.models import Customer
from domain.merchants.models import Merchant
from domain.payments.models import Payment
from domain.payments.state_machine import is_payment_recoverable
from domain.recovery.models import RecoveryCase
from domain.shared.errors import DuplicateRecoveryCaseError, PaymentNotRecoverableError


# ---------------------------------------------------------------------------
# Input / output types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CaseCreationRequest:
    """
    Input to create_recovery_case().

    Attributes:
        payment:               The at-risk or failed Payment.
        customer:              The Customer associated with the payment.
        merchant:              The Merchant who owns the payment.
        has_open_case:         Whether an open recovery case already exists
                               for this payment (checked by the caller via DB).
    """

    payment: Payment
    customer: Customer
    merchant: Merchant
    has_open_case: bool = False


@dataclass(frozen=True)
class CaseCreationResult:
    """
    Output of create_recovery_case().

    Attributes:
        case: The newly constructed RecoveryCase (not yet persisted).
    """

    case: RecoveryCase


# ---------------------------------------------------------------------------
# Domain service
# ---------------------------------------------------------------------------

def create_recovery_case(request: CaseCreationRequest) -> CaseCreationResult:
    """
    Create a RecoveryCase for a failed or at-risk payment.

    This function is deterministic and pure. It does NOT persist anything.
    The caller must save the returned case.

    Args:
        request: CaseCreationRequest with all required context.

    Returns:
        CaseCreationResult containing the new RecoveryCase.

    Raises:
        PaymentNotRecoverableError: if the payment status is not eligible.
        DuplicateRecoveryCaseError: if an open case already exists.
    """
    payment = request.payment
    customer = request.customer
    merchant = request.merchant

    # Guard: payment must be in a recoverable state.
    if not is_payment_recoverable(payment.status):
        raise PaymentNotRecoverableError(
            payment_id=str(payment.id),
            status=payment.status.value,
        )

    # Guard: no duplicate open cases.
    if request.has_open_case:
        raise DuplicateRecoveryCaseError(payment_id=str(payment.id))

    # Guard: customer must belong to the merchant.
    if customer.merchant_id != merchant.id:
        raise ValueError(
            f"Customer {customer.id} does not belong to merchant {merchant.id}."
        )

    # Guard: payment currency must match merchant currency.
    if payment.currency != merchant.currency:
        raise ValueError(
            f"Payment currency {payment.currency!r} does not match "
            f"merchant currency {merchant.currency!r}."
        )

    case = RecoveryCase(
        merchant_id=merchant.id,
        customer_id=customer.id,
        payment_id=payment.id,
        amount_at_risk_minor=payment.amount_minor,
    )

    return CaseCreationResult(case=case)
