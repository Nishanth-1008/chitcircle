"""Exact money arithmetic (integer minor units). Floats are rejected everywhere."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from fractions import Fraction
from typing import Optional, Union

from .errors import FinancialEngineError

CURRENCY_EXPONENTS = {
    "INR": 2, "USD": 2, "EUR": 2, "GBP": 2, "AUD": 2, "CAD": 2,
    "SGD": 2, "AED": 2, "JPY": 0, "KWD": 3,
}
SYMBOLS = {"INR": "₹", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}


class MoneyError(FinancialEngineError, ValueError):
    pass


class CurrencyMismatchError(MoneyError):
    pass


class PrecisionError(MoneyError):
    pass


class RoundingMode(str, Enum):
    HALF_UP = "HALF_UP"        # .5 rounds away from zero
    HALF_EVEN = "HALF_EVEN"    # banker's rounding
    DOWN = "DOWN"              # toward zero
    UP = "UP"                  # away from zero


RateLike = Union[Decimal, str, int, Fraction]


def to_fraction(value: RateLike) -> Fraction:
    if isinstance(value, (bool, float)):
        raise MoneyError("floating-point and boolean values are not allowed in money math")
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError, TypeError) as exc:
        raise MoneyError(f"invalid exact number: {value!r}") from exc


def round_fraction(x: Fraction, mode: RoundingMode) -> int:
    sign = -1 if x < 0 else 1
    a = abs(x)
    q, r = divmod(a.numerator, a.denominator)
    if r == 0:
        res = q
    elif mode == RoundingMode.DOWN:
        res = q
    elif mode == RoundingMode.UP:
        res = q + 1
    else:
        twice = 2 * r
        if twice > a.denominator:
            res = q + 1
        elif twice < a.denominator:
            res = q
        elif mode == RoundingMode.HALF_UP:
            res = q + 1
        else:  # HALF_EVEN
            res = q + 1 if q % 2 else q
    return sign * res


def _indian_group(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


@dataclass(frozen=True)
class Money:
    minor: int
    currency: str

    def __post_init__(self) -> None:
        if isinstance(self.minor, bool) or not isinstance(self.minor, int):
            raise MoneyError("Money.minor must be an int number of minor units")
        if not isinstance(self.currency, str) or self.currency not in CURRENCY_EXPONENTS:
            raise MoneyError(f"unsupported currency: {self.currency!r}")

    # construction -----------------------------------------------------
    @classmethod
    def zero(cls, currency: str) -> "Money":
        return cls(0, currency)

    @classmethod
    def from_major(cls, amount: Union[int, str, Decimal], currency: str) -> "Money":
        if isinstance(amount, (float, bool)):
            raise MoneyError("floats are not accepted; pass str, int or Decimal")
        if currency not in CURRENCY_EXPONENTS:
            raise MoneyError(f"unsupported currency: {currency!r}")
        try:
            d = Decimal(str(amount))
        except InvalidOperation as exc:
            raise MoneyError(f"invalid amount: {amount!r}") from exc
        scaled = d * (Decimal(10) ** CURRENCY_EXPONENTS[currency])
        if scaled != scaled.to_integral_value():
            raise PrecisionError(f"{amount} has more precision than {currency} supports")
        return cls(int(scaled), currency)

    # arithmetic -------------------------------------------------------
    def _same(self, other: "Money") -> None:
        if not isinstance(other, Money):
            raise MoneyError("operand is not Money")
        if other.currency != self.currency:
            raise CurrencyMismatchError(f"{self.currency} vs {other.currency}")

    def __add__(self, o: "Money") -> "Money":
        self._same(o)
        return Money(self.minor + o.minor, self.currency)

    def __sub__(self, o: "Money") -> "Money":
        self._same(o)
        return Money(self.minor - o.minor, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.minor, self.currency)

    def __lt__(self, o: "Money") -> bool:
        self._same(o)
        return self.minor < o.minor

    def __le__(self, o: "Money") -> bool:
        self._same(o)
        return self.minor <= o.minor

    def __gt__(self, o: "Money") -> bool:
        self._same(o)
        return self.minor > o.minor

    def __ge__(self, o: "Money") -> bool:
        self._same(o)
        return self.minor >= o.minor

    def mul_rate(self, rate: RateLike, mode: RoundingMode) -> "Money":
        return Money(round_fraction(Fraction(self.minor) * to_fraction(rate), mode), self.currency)

    @property
    def is_negative(self) -> bool:
        return self.minor < 0

    @property
    def is_zero(self) -> bool:
        return self.minor == 0

    # presentation / serialisation ---------------------------------------
    def to_major(self) -> Decimal:
        return Decimal(self.minor) / (Decimal(10) ** CURRENCY_EXPONENTS[self.currency])

    def format(self) -> str:
        exp = CURRENCY_EXPONENTS[self.currency]
        sign = "-" if self.minor < 0 else ""
        whole, frac = divmod(abs(self.minor), 10 ** exp)
        grouped = _indian_group(whole) if self.currency == "INR" else f"{whole:,}"
        sym = SYMBOLS.get(self.currency, self.currency + " ")
        return f"{sign}{sym}{grouped}" + (f".{frac:0{exp}d}" if exp else "")

    def to_dict(self) -> dict:
        return {"minor": self.minor, "currency": self.currency}

    @classmethod
    def from_dict(cls, d: dict) -> "Money":
        return cls(d["minor"], d["currency"])


def split_equal(total: Money, n: int) -> tuple[tuple[Money, ...], Money]:
    """Floor-split ``total`` into ``n`` equal shares and return (shares, remainder)."""
    if n <= 0:
        raise MoneyError("cannot split among zero recipients")
    if total.minor < 0:
        raise MoneyError("cannot split a negative amount")
    base, rem = divmod(total.minor, n)
    return tuple(Money(base, total.currency) for _ in range(n)), Money(rem, total.currency)


@dataclass(frozen=True)
class RoundingAdjustment:
    """Explicit record of a rounding remainder (never silently discarded)."""
    cycle_id: str
    currency: str
    calculation: str
    reason: str
    rule_version: int
    amount: Money
    destination: Optional[str]

    def to_dict(self) -> dict:
        return {
            "cycle_id": self.cycle_id, "currency": self.currency,
            "calculation": self.calculation, "reason": self.reason,
            "rule_version": self.rule_version, "amount": self.amount.to_dict(),
            "destination": self.destination,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RoundingAdjustment":
        return cls(d["cycle_id"], d["currency"], d["calculation"], d["reason"],
                   d["rule_version"], Money.from_dict(d["amount"]), d["destination"])
