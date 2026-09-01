"""
domain/shared/errors.py

Domain exception hierarchy for the financial domain.

All domain errors inherit from DomainError so callers can catch at
the right level of specificity.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""


class DomainError(Exception):
    """Base class for all domain errors. Signals a violated domain invariant."""


# ---------------------------------------------------------------------------
# Money errors
# ---------------------------------------------------------------------------

class InvalidMoneyAmountError(DomainError):
    """Raised when a monetary amount is invalid (e.g. negative, float)."""


class InvalidCurrencyError(DomainError):
    """Raised when a currency code is not supported."""


class CurrencyMismatchError(DomainError):
    """Raised when an operation is attempted on two different currencies."""


# ---------------------------------------------------------------------------
# State machine errors
# ---------------------------------------------------------------------------

class InvalidStateTransitionError(DomainError):
    """
    Raised when a requested state transition is not permitted
    by the domain state machine.
    """

    def __init__(self, entity: str, from_state: str, to_state: str) -> None:
        self.entity = entity
        self.from_state = from_state
        self.to_state = to_state
        super().__init__(
            f"Invalid {entity} state transition: {from_state!r} → {to_state!r}"
        )


# ---------------------------------------------------------------------------
# Policy errors
# ---------------------------------------------------------------------------

class PolicyViolationError(DomainError):
    """
    Raised when a proposed action violates the merchant's recovery policy.
    The AI must not override this — it is a deterministic safety gate (P-03).
    """

    def __init__(self, rule: str, detail: str) -> None:
        self.rule = rule
        self.detail = detail
        super().__init__(f"Policy violation [{rule}]: {detail}")


# ---------------------------------------------------------------------------
# Recovery errors
# ---------------------------------------------------------------------------

class RecoveryCaseError(DomainError):
    """Base class for errors related to recovery case management."""


class DuplicateRecoveryCaseError(RecoveryCaseError):
    """Raised when a recovery case already exists for the payment."""

    def __init__(self, payment_id: str) -> None:
        self.payment_id = payment_id
        super().__init__(
            f"An open recovery case already exists for payment {payment_id!r}. "
            "Duplicate cases are not permitted."
        )


class PaymentNotRecoverableError(RecoveryCaseError):
    """Raised when a payment is not in a state eligible for recovery."""

    def __init__(self, payment_id: str, status: str) -> None:
        self.payment_id = payment_id
        self.status = status
        super().__init__(
            f"Payment {payment_id!r} with status {status!r} is not eligible for recovery."
        )


class InvalidActionError(DomainError):
    """Raised when a recovery action request is structurally invalid."""
