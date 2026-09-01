"""
domain/shared/money.py

Money value object for the financial domain.

ARCHITECTURAL RULE (FS-01, P-01):
    All monetary values are stored and calculated as integer minor units.
    Example: INR 1,250.50  →  amount_minor=125050, currency="INR"

    Floating-point is FORBIDDEN for authoritative monetary values.
    Presentation formatting (e.g. "₹1,250.50") belongs in the UI layer only.

Does NOT depend on FastAPI, SQLAlchemy, Razorpay, or any LLM SDK.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.shared.enums import Currency
from domain.shared.errors import (
    CurrencyMismatchError,
    InvalidCurrencyError,
    InvalidMoneyAmountError,
)

# Minor units per major unit for each supported currency.
# INR: 1 rupee = 100 paise  →  minor_units_per_major = 100
_MINOR_UNITS: dict[str, int] = {
    Currency.INR: 100,
}

# All currently supported ISO 4217 currency codes.
SUPPORTED_CURRENCIES: frozenset[str] = frozenset(_MINOR_UNITS.keys())


@dataclass(frozen=True)
class Money:
    """
    Immutable monetary value object.

    Attributes:
        amount_minor: Non-negative integer in the currency's smallest unit
                      (paise for INR). Example: 125050 = ₹1,250.50.
        currency:     ISO 4217 code from the supported set (e.g. "INR").

    Design notes:
    - Frozen so it cannot be mutated after construction.
    - Arithmetic produces new Money instances; it never mutates in place.
    - Currency mismatch on arithmetic raises CurrencyMismatchError.
    - Negative amounts are forbidden; use zero for "no amount".
    """

    amount_minor: int
    currency: str

    def __post_init__(self) -> None:
        if self.currency not in SUPPORTED_CURRENCIES:
            raise InvalidCurrencyError(
                f"Currency '{self.currency}' is not supported. "
                f"Supported: {sorted(SUPPORTED_CURRENCIES)}"
            )
        if not isinstance(self.amount_minor, int):
            raise InvalidMoneyAmountError(
                f"amount_minor must be an integer, got {type(self.amount_minor).__name__}. "
                "Floating-point monetary values are forbidden (FS-01)."
            )
        if self.amount_minor < 0:
            raise InvalidMoneyAmountError(
                f"amount_minor cannot be negative: {self.amount_minor}"
            )

    # ------------------------------------------------------------------
    # Arithmetic helpers — all return new Money instances
    # ------------------------------------------------------------------

    def add(self, other: Money) -> Money:
        """Return the sum of two Money values. Currencies must match."""
        self._assert_same_currency(other)
        return Money(amount_minor=self.amount_minor + other.amount_minor, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        """
        Return the difference. Result must be non-negative.
        Currencies must match.
        """
        self._assert_same_currency(other)
        result = self.amount_minor - other.amount_minor
        if result < 0:
            raise InvalidMoneyAmountError(
                f"Subtraction would produce a negative amount: "
                f"{self} - {other} = {result} minor units."
            )
        return Money(amount_minor=result, currency=self.currency)

    def is_zero(self) -> bool:
        return self.amount_minor == 0

    def is_greater_than(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor > other.amount_minor

    def is_greater_than_or_equal(self, other: Money) -> bool:
        self._assert_same_currency(other)
        return self.amount_minor >= other.amount_minor

    # ------------------------------------------------------------------
    # Presentation (UI layer only — never use for calculations)
    # ------------------------------------------------------------------

    def format_display(self) -> str:
        """Human-readable display string. Do NOT use output for calculations."""
        minor_per_major = _MINOR_UNITS[self.currency]
        major = self.amount_minor // minor_per_major
        minor = self.amount_minor % minor_per_major
        if self.currency == Currency.INR:
            return f"₹{major:,}.{minor:02d}"
        return f"{self.currency} {major:,}.{minor:02d}"

    def __repr__(self) -> str:
        return f"Money(amount_minor={self.amount_minor}, currency='{self.currency}')"

    def __str__(self) -> str:
        return self.format_display()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise CurrencyMismatchError(
                f"Cannot operate on different currencies: "
                f"'{self.currency}' and '{other.currency}'"
            )


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def inr(amount_minor: int) -> Money:
    """Convenience factory: create an INR Money value from paise."""
    return Money(amount_minor=amount_minor, currency=Currency.INR)
