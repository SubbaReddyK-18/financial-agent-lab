"""
domain/shared/enums.py

Strongly-typed enumerations for the financial domain.
These are the only permitted values for controlled states throughout the system.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from enum import StrEnum


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------

class Currency(StrEnum):
    """Supported currencies for MVP. INR only initially."""
    INR = "INR"


# ---------------------------------------------------------------------------
# Order lifecycle
# ---------------------------------------------------------------------------

class OrderStatus(StrEnum):
    CREATED = "CREATED"
    CONFIRMED = "CONFIRMED"      # order acknowledged by merchant
    COMPLETED = "COMPLETED"      # payment captured
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Payment lifecycle
# ---------------------------------------------------------------------------

class PaymentStatus(StrEnum):
    """
    Full lifecycle of a payment.

    Valid transition graph (see domain/payments/state_machine.py):

        CREATED ──► AUTHORIZED ──► CAPTURED ──► REFUNDED
           │              │
           └──────────────┴──► FAILED

    NOTE: FAILED is not strictly terminal — the system must handle late/
    out-of-order events safely without data corruption. Arriving events
    that would cause an invalid transition are rejected, not silently applied.
    """
    CREATED = "CREATED"
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentAttemptStatus(StrEnum):
    """
    Status of a single payment attempt.
    One Payment may have many PaymentAttempts.
    """
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class PaymentMethod(StrEnum):
    """Payment instruments supported. Extensible for future blocks."""
    CARD = "CARD"
    UPI = "UPI"
    NETBANKING = "NETBANKING"
    WALLET = "WALLET"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Recovery lifecycle
# ---------------------------------------------------------------------------

class RecoveryCaseStatus(StrEnum):
    """
    Lifecycle of a revenue-recovery case.

        OPEN ──► IN_PROGRESS ──► RECOVERED
           │           │
           └───────────┴──────► IRRECOVERABLE
                                       │
                               CLOSED (terminal)
    """
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    RECOVERED = "RECOVERED"
    IRRECOVERABLE = "IRRECOVERABLE"
    CLOSED = "CLOSED"


class RecoveryActionType(StrEnum):
    """
    Permitted recovery actions. AI may select from this catalogue only.
    Selection is constrained by MerchantRecoveryPolicy.
    """
    WAIT = "WAIT"
    RETRY = "RETRY"
    PAYMENT_LINK = "PAYMENT_LINK"
    NOTIFY = "NOTIFY"
    ESCALATE = "ESCALATE"


class RecoveryActionStatus(StrEnum):
    """Lifecycle of a single recovery action."""
    PROPOSED = "PROPOSED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"       # cleared policy + auth; awaiting execution
    EXECUTING = "EXECUTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    SUPERSEDED = "SUPERSEDED"


# ---------------------------------------------------------------------------
# Outbox events
# ---------------------------------------------------------------------------

class OutboxEventStatus(StrEnum):
    """Lifecycle of an outbox dispatch event."""
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class OutboxEventType(StrEnum):
    """Outbox event message types."""
    RECOVERY_ACTION_DISPATCH = "RECOVERY_ACTION_DISPATCH"


class DecisionRequestStatus(StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# ---------------------------------------------------------------------------
# Financial events
# ---------------------------------------------------------------------------

class AggregateType(StrEnum):
    """Domain aggregate types — used in FinancialEvent for routing."""
    MERCHANT = "MERCHANT"
    CUSTOMER = "CUSTOMER"
    ORDER = "ORDER"
    PAYMENT = "PAYMENT"
    PAYMENT_ATTEMPT = "PAYMENT_ATTEMPT"
    RECOVERY_CASE = "RECOVERY_CASE"
    RECOVERY_ACTION = "RECOVERY_ACTION"


class FinancialEventType(StrEnum):
    """
    Durable domain event types. Each represents a state transition
    that must be persisted reliably (outbox pattern, Block 2+).
    """
    # Payment events
    PAYMENT_CREATED = "PAYMENT_CREATED"
    PAYMENT_AUTHORIZED = "PAYMENT_AUTHORIZED"
    PAYMENT_CAPTURED = "PAYMENT_CAPTURED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    PAYMENT_REFUNDED = "PAYMENT_REFUNDED"

    # Payment attempt events
    PAYMENT_ATTEMPT_STARTED = "PAYMENT_ATTEMPT_STARTED"
    PAYMENT_ATTEMPT_SUCCEEDED = "PAYMENT_ATTEMPT_SUCCEEDED"
    PAYMENT_ATTEMPT_FAILED = "PAYMENT_ATTEMPT_FAILED"

    # Recovery events
    RECOVERY_CASE_OPENED = "RECOVERY_CASE_OPENED"
    RECOVERY_CASE_CLOSED = "RECOVERY_CASE_CLOSED"
    RECOVERY_ACTION_PROPOSED = "RECOVERY_ACTION_PROPOSED"
    RECOVERY_ACTION_EXECUTED = "RECOVERY_ACTION_EXECUTED"
    RECOVERY_ACTION_COMPLETED = "RECOVERY_ACTION_COMPLETED"
    RECOVERY_ACTION_FAILED = "RECOVERY_ACTION_FAILED"
