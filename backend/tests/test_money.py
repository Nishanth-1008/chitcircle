from decimal import Decimal
from fractions import Fraction

import pytest

from financial_engine.money import (CurrencyMismatchError, Money, MoneyError, PrecisionError,
                                    RoundingMode, round_fraction, split_equal)


def test_from_major_exact():
    assert Money.from_major("1000.00", "INR").minor == 100_000
    assert Money.from_major(Decimal("350"), "INR").minor == 35_000
    assert Money.from_major(5, "JPY").minor == 5


def test_rejects_floats_and_excess_precision():
    with pytest.raises(MoneyError):
        Money.from_major(0.1, "INR")
    with pytest.raises(MoneyError):
        Money(1.5, "INR")
    with pytest.raises(PrecisionError):
        Money.from_major("1.005", "INR")
    with pytest.raises(PrecisionError):
        Money.from_major("1.5", "JPY")


def test_currency_mismatch():
    with pytest.raises(CurrencyMismatchError):
        Money(1, "INR") + Money(1, "USD")
    with pytest.raises(MoneyError):
        Money(1, "XXX")


def test_arithmetic_and_format():
    assert (Money(500, "INR") - Money(200, "INR")).minor == 300
    assert Money(10_000_000, "INR").format() == "₹1,00,000.00"
    assert Money(-123, "USD").format() == "-$1.23"


@pytest.mark.parametrize("x,mode,exp", [
    (Fraction(5, 2), RoundingMode.HALF_UP, 3), (Fraction(5, 2), RoundingMode.HALF_EVEN, 2),
    (Fraction(7, 2), RoundingMode.HALF_EVEN, 4), (Fraction(-5, 2), RoundingMode.HALF_UP, -3),
    (Fraction(11, 10), RoundingMode.DOWN, 1), (Fraction(11, 10), RoundingMode.UP, 2),
    (Fraction(14, 10), RoundingMode.HALF_UP, 1)])
def test_rounding(x, mode, exp):
    assert round_fraction(x, mode) == exp


def test_mul_rate_exact():
    assert Money(10_000_000, "INR").mul_rate("0.05", RoundingMode.HALF_UP).minor == 500_000
    with pytest.raises(MoneyError):
        Money(1, "INR").mul_rate(0.05, RoundingMode.HALF_UP)


def test_split_equal_remainder():
    shares, rem = split_equal(Money(100, "INR"), 3)
    assert [s.minor for s in shares] == [33, 33, 33] and rem.minor == 1
