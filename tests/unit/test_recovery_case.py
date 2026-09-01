"""
tests/unit/test_recovery_case.py

Unit tests for recovery case creation and lifecycle.

Tests cover: case creation from eligible payments, rejection of ineligible
payments, duplicate case prevention, and case state transitions.

No I/O. No database. No external services.
"""

import uuid

import pytest

from domain.customers.models import Customer
from domain.merchants.models import Merchant
from domain.payments.models import Payment
from domain.recovery.case_service import CaseCreationRequest, create_recovery_case
from domain.recovery.models import RecoveryCase
from domain.recovery.state_machine import validate_case_transition
from domain.shared.enums import PaymentStatus, RecoveryCaseStatus
from domain.shared.errors import (
    DuplicateRecoveryCaseError,
    InvalidStateTransitionError,
    PaymentNotRecoverableError,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def merchant() -> Merchant:
    return Merchant(name="Test Merchant", currency="INR")


@pytest.fixture
def customer(merchant: Merchant) -> Customer:
    return Customer(merchant_id=merchant.id, external_reference="CUST-001")


@pytest.fixture
def failed_payment(customer: Customer) -> Payment:
    return Payment(
        order_id=uuid.uuid4(),
        customer_id=customer.id,
        amount_minor=500000,   # ₹5,000.00 in paise
        currency="INR",
        status=PaymentStatus.FAILED,
    )


# ---------------------------------------------------------------------------
# Case creation — happy path
# ---------------------------------------------------------------------------

class TestRecoveryCaseCreation:
    def test_creates_case_for_failed_payment(
        self, merchant: Merchant, customer: Customer, failed_payment: Payment
    ):
        request = CaseCreationRequest(
            payment=failed_payment,
            customer=customer,
            merchant=merchant,
        )
        result = create_recovery_case(request)
        case = result.case
        assert case.payment_id == failed_payment.id
        assert case.merchant_id == merchant.id
        assert case.customer_id == customer.id
        assert case.amount_at_risk_minor == failed_payment.amount_minor
        assert case.status == RecoveryCaseStatus.OPEN

    def test_case_amount_matches_payment_amount(
        self, merchant: Merchant, customer: Customer, failed_payment: Payment
    ):
        request = CaseCreationRequest(
            payment=failed_payment,
            customer=customer,
            merchant=merchant,
        )
        result = create_recovery_case(request)
        assert result.case.amount_at_risk_minor == failed_payment.amount_minor

    def test_returned_case_has_new_uuid(
        self, merchant: Merchant, customer: Customer, failed_payment: Payment
    ):
        request = CaseCreationRequest(
            payment=failed_payment,
            customer=customer,
            merchant=merchant,
        )
        result = create_recovery_case(request)
        assert isinstance(result.case.id, uuid.UUID)

    def test_returned_case_is_open(
        self, merchant: Merchant, customer: Customer, failed_payment: Payment
    ):
        request = CaseCreationRequest(
            payment=failed_payment,
            customer=customer,
            merchant=merchant,
        )
        result = create_recovery_case(request)
        assert result.case.is_open()
        assert result.case.closed_at is None


# ---------------------------------------------------------------------------
# Case creation — rejection cases
# ---------------------------------------------------------------------------

class TestRecoveryCaseRejection:
    def test_captured_payment_not_recoverable(
        self, merchant: Merchant, customer: Customer
    ):
        captured = Payment(
            order_id=uuid.uuid4(),
            customer_id=customer.id,
            amount_minor=100000,
            currency="INR",
            status=PaymentStatus.CAPTURED,
        )
        request = CaseCreationRequest(
            payment=captured,
            customer=customer,
            merchant=merchant,
        )
        with pytest.raises(PaymentNotRecoverableError) as exc_info:
            create_recovery_case(request)
        assert exc_info.value.status == "CAPTURED"

    def test_created_payment_not_recoverable(
        self, merchant: Merchant, customer: Customer
    ):
        pending = Payment(
            order_id=uuid.uuid4(),
            customer_id=customer.id,
            amount_minor=100000,
            currency="INR",
            status=PaymentStatus.CREATED,
        )
        request = CaseCreationRequest(
            payment=pending,
            customer=customer,
            merchant=merchant,
        )
        with pytest.raises(PaymentNotRecoverableError):
            create_recovery_case(request)

    def test_duplicate_case_rejected(
        self, merchant: Merchant, customer: Customer, failed_payment: Payment
    ):
        request = CaseCreationRequest(
            payment=failed_payment,
            customer=customer,
            merchant=merchant,
            has_open_case=True,   # caller signals an open case already exists
        )
        with pytest.raises(DuplicateRecoveryCaseError) as exc_info:
            create_recovery_case(request)
        assert str(failed_payment.id) in str(exc_info.value)

    def test_customer_merchant_mismatch_rejected(
        self, merchant: Merchant, failed_payment: Payment
    ):
        other_merchant_id = uuid.uuid4()
        wrong_customer = Customer(merchant_id=other_merchant_id)
        wrong_payment = Payment(
            order_id=uuid.uuid4(),
            customer_id=wrong_customer.id,
            amount_minor=100000,
            currency="INR",
            status=PaymentStatus.FAILED,
        )
        request = CaseCreationRequest(
            payment=wrong_payment,
            customer=wrong_customer,
            merchant=merchant,
        )
        with pytest.raises(ValueError, match="merchant"):
            create_recovery_case(request)


# ---------------------------------------------------------------------------
# Recovery case state machine
# ---------------------------------------------------------------------------

class TestRecoveryCaseStateMachine:
    def test_open_to_in_progress(self):
        validate_case_transition(RecoveryCaseStatus.OPEN, RecoveryCaseStatus.IN_PROGRESS)

    def test_open_to_irrecoverable(self):
        validate_case_transition(RecoveryCaseStatus.OPEN, RecoveryCaseStatus.IRRECOVERABLE)

    def test_in_progress_to_recovered(self):
        validate_case_transition(
            RecoveryCaseStatus.IN_PROGRESS, RecoveryCaseStatus.RECOVERED
        )

    def test_in_progress_to_irrecoverable(self):
        validate_case_transition(
            RecoveryCaseStatus.IN_PROGRESS, RecoveryCaseStatus.IRRECOVERABLE
        )

    def test_recovered_to_closed(self):
        validate_case_transition(RecoveryCaseStatus.RECOVERED, RecoveryCaseStatus.CLOSED)

    def test_irrecoverable_to_closed(self):
        validate_case_transition(
            RecoveryCaseStatus.IRRECOVERABLE, RecoveryCaseStatus.CLOSED
        )

    def test_closed_is_terminal(self):
        for target in RecoveryCaseStatus:
            with pytest.raises(InvalidStateTransitionError):
                validate_case_transition(RecoveryCaseStatus.CLOSED, target)

    def test_recovered_to_open_invalid(self):
        with pytest.raises(InvalidStateTransitionError):
            validate_case_transition(RecoveryCaseStatus.RECOVERED, RecoveryCaseStatus.OPEN)


# ---------------------------------------------------------------------------
# RecoveryCase model validation
# ---------------------------------------------------------------------------

class TestRecoveryCaseModel:
    def test_negative_amount_rejected(self):
        with pytest.raises((ValueError, TypeError)):
            RecoveryCase(
                merchant_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
                payment_id=uuid.uuid4(),
                amount_at_risk_minor=-1,
            )

    def test_zero_amount_rejected(self):
        with pytest.raises(ValueError):
            RecoveryCase(
                merchant_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
                payment_id=uuid.uuid4(),
                amount_at_risk_minor=0,
            )

    def test_float_amount_rejected(self):
        with pytest.raises((TypeError, ValueError)):
            RecoveryCase(
                merchant_id=uuid.uuid4(),
                customer_id=uuid.uuid4(),
                payment_id=uuid.uuid4(),
                amount_at_risk_minor=5000.50,  # type: ignore[arg-type]
            )
