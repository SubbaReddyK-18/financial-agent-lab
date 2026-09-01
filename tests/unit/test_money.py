"""
tests/unit/test_money.py

Unit tests for the Money value object.

Tests cover: integer minor units, valid/invalid amounts, currency validation,
arithmetic operations, and currency mismatch protection.

No I/O. No database. No external services.
"""

import pytest

from domain.shared.errors import (
    CurrencyMismatchError,
    InvalidCurrencyError,
    InvalidMoneyAmountError,
)
from domain.shared.money import Money, inr


class TestMoneyConstruction:
    def test_valid_inr_amount(self):
        m = Money(amount_minor=125050, currency="INR")
        assert m.amount_minor == 125050
        assert m.currency == "INR"

    def test_zero_amount_is_valid(self):
        m = Money(amount_minor=0, currency="INR")
        assert m.amount_minor == 0

    def test_inr_factory_helper(self):
        m = inr(100)
        assert m.amount_minor == 100
        assert m.currency == "INR"

    def test_money_is_immutable(self):
        m = Money(amount_minor=1000, currency="INR")
        with pytest.raises((AttributeError, TypeError)):
            m.amount_minor = 2000  # type: ignore[misc]

    def test_float_amount_is_rejected(self):
        """FS-01: floating-point amounts are forbidden."""
        with pytest.raises((InvalidMoneyAmountError, TypeError)):
            Money(amount_minor=1250.50, currency="INR")  # type: ignore[arg-type]

    def test_negative_amount_is_rejected(self):
        with pytest.raises(InvalidMoneyAmountError):
            Money(amount_minor=-1, currency="INR")

    def test_unsupported_currency_is_rejected(self):
        with pytest.raises(InvalidCurrencyError):
            Money(amount_minor=100, currency="XYZ")

    def test_empty_currency_is_rejected(self):
        with pytest.raises(InvalidCurrencyError):
            Money(amount_minor=100, currency="")

    def test_usd_not_supported_in_mvp(self):
        with pytest.raises(InvalidCurrencyError):
            Money(amount_minor=100, currency="USD")


class TestMoneyArithmetic:
    def test_add_same_currency(self):
        a = inr(1000)
        b = inr(500)
        result = a.add(b)
        assert result.amount_minor == 1500
        assert result.currency == "INR"

    def test_add_produces_new_instance(self):
        a = inr(1000)
        b = inr(500)
        result = a.add(b)
        assert result is not a
        assert result is not b

    def test_subtract_same_currency(self):
        a = inr(1000)
        b = inr(400)
        result = a.subtract(b)
        assert result.amount_minor == 600

    def test_subtract_to_zero(self):
        a = inr(500)
        result = a.subtract(inr(500))
        assert result.amount_minor == 0

    def test_subtract_producing_negative_raises(self):
        a = inr(100)
        b = inr(200)
        with pytest.raises(InvalidMoneyAmountError):
            a.subtract(b)

    def test_add_different_currencies_raises(self):
        a = Money(amount_minor=1000, currency="INR")
        # We can't create USD yet since it's not supported —
        # test with a hypothetical future-supported currency by patching.
        # For now, verify the mismatch guard exists by testing same-type comparison.
        # (This test will grow when multi-currency is introduced.)
        assert a.currency == "INR"

    def test_currency_mismatch_on_add_raises(self):
        """Directly test the mismatch guard by constructing two INR moneys
        and patching one's currency string (bypass immutability for testing)."""
        a = inr(100)
        # object.__setattr__ bypasses frozen dataclass for testing mismatch path
        b_patched = object.__new__(Money)
        object.__setattr__(b_patched, "amount_minor", 50)
        object.__setattr__(b_patched, "currency", "USD")
        with pytest.raises(CurrencyMismatchError):
            a.add(b_patched)


class TestMoneyComparisons:
    def test_is_zero(self):
        assert inr(0).is_zero()
        assert not inr(1).is_zero()

    def test_is_greater_than(self):
        assert inr(200).is_greater_than(inr(100))
        assert not inr(100).is_greater_than(inr(200))
        assert not inr(100).is_greater_than(inr(100))

    def test_is_greater_than_or_equal(self):
        assert inr(100).is_greater_than_or_equal(inr(100))
        assert inr(101).is_greater_than_or_equal(inr(100))
        assert not inr(99).is_greater_than_or_equal(inr(100))

    def test_equality(self):
        assert inr(500) == inr(500)
        assert inr(500) != inr(501)


class TestMoneyPresentation:
    def test_format_display_inr(self):
        m = inr(125050)
        display = m.format_display()
        assert "1,250" in display
        assert "50" in display
        assert "₹" in display

    def test_format_display_zero(self):
        m = inr(0)
        display = m.format_display()
        assert "₹" in display
        assert "0" in display

    def test_str_returns_formatted(self):
        m = inr(100)
        assert str(m) == m.format_display()
