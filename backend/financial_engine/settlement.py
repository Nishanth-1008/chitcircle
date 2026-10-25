"""Settlement calculation.

Discount-funded modes (auction, agreed discount):  W = V - D,  P = D - F,  sum(net) = W + F + R
No-discount modes (rotation, lottery):             W = V - F,  P = 0,      sum(net) = W + F
R is the explicit rounding remainder of the dividend split (never silently dropped).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from .contributions import compute_contributions
from .errors import FinancialEngineError
from .money import Money, RoundingAdjustment, split_equal
from .rules import (CommissionBase, DISCOUNT_FUNDED, DividendAllocation, PayoutMethod, Ruleset)


class SettlementError(FinancialEngineError):
    pass


class CommissionLimitError(SettlementError):
    pass


class CommissionNotFundableError(SettlementError):
    pass


class RoundingPolicyIncompleteError(SettlementError):
    pass


class SettlementValidationError(SettlementError):
    def __init__(self, violations: list):
        self.violations = violations
        super().__init__("settlement failed validation: " + ", ".join(violations))


@dataclass(frozen=True)
class Settlement:
    circle_id: str
    cycle_id: str
    ruleset_version: int
    ruleset_fingerprint: str
    currency: str
    payout_method: PayoutMethod
    winner_member_id: str
    member_order: tuple
    chit_value: Money
    discount: Money
    winner_payout: Money
    commission: Money
    dividend_pool: Money
    contributions: dict
    dividends: dict
    net_contributions: dict
    rounding_remainder: Money
    remainder_destination: Optional[str]
    adjustments: tuple

    def to_dict(self) -> dict:
        md = lambda m: {k: v.to_dict() for k, v in m.items()}  # noqa: E731
        return {
            "circle_id": self.circle_id, "cycle_id": self.cycle_id,
            "ruleset_version": self.ruleset_version, "ruleset_fingerprint": self.ruleset_fingerprint,
            "currency": self.currency, "payout_method": self.payout_method.value,
            "winner_member_id": self.winner_member_id, "member_order": list(self.member_order),
            "chit_value": self.chit_value.to_dict(), "discount": self.discount.to_dict(),
            "winner_payout": self.winner_payout.to_dict(), "commission": self.commission.to_dict(),
            "dividend_pool": self.dividend_pool.to_dict(), "contributions": md(self.contributions),
            "dividends": md(self.dividends), "net_contributions": md(self.net_contributions),
            "rounding_remainder": self.rounding_remainder.to_dict(),
            "remainder_destination": self.remainder_destination,
            "adjustments": [a.to_dict() for a in self.adjustments],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Settlement":
        mm = lambda m: {k: Money.from_dict(v) for k, v in m.items()}  # noqa: E731
        return cls(
            d["circle_id"], d["cycle_id"], d["ruleset_version"], d["ruleset_fingerprint"], d["currency"],
            PayoutMethod(d["payout_method"]), d["winner_member_id"], tuple(d["member_order"]),
            Money.from_dict(d["chit_value"]), Money.from_dict(d["discount"]),
            Money.from_dict(d["winner_payout"]), Money.from_dict(d["commission"]),
            Money.from_dict(d["dividend_pool"]), mm(d["contributions"]), mm(d["dividends"]),
            mm(d["net_contributions"]), Money.from_dict(d["rounding_remainder"]),
            d["remainder_destination"], tuple(RoundingAdjustment.from_dict(a) for a in d["adjustments"]))


def compute_commission(rules: Ruleset, discount: Money) -> Money:
    """Commission from the explicitly configured base; rejects out-of-limit results."""
    c, cur = rules.commission, rules.currency
    if c.base == CommissionBase.PERCENT_OF_CHIT_VALUE:
        f = Money(rules.total_chit_value, cur).mul_rate(c.rate, c.rounding)
    elif c.base == CommissionBase.PERCENT_OF_DISCOUNT:
        f = discount.mul_rate(c.rate, c.rounding)
    else:
        f = Money(c.fixed_amount, cur)
    if c.min_amount is not None and f.minor < c.min_amount:
        raise CommissionLimitError(f"commission {f.minor} is below the configured minimum {c.min_amount}")
    if c.max_amount is not None and f.minor > c.max_amount:
        raise CommissionLimitError(f"commission {f.minor} exceeds the configured maximum {c.max_amount}")
    return f


def calculate_settlement(rules: Ruleset, cycle_id: str, member_ids: Iterable[str], winner_id: str,
                         payout_method: PayoutMethod, discount: Optional[Money] = None,
                         eligible_for_dividend: Optional[Iterable[str]] = None,
                         prior_winners: frozenset = frozenset()) -> Settlement:
    from .validation import check_settlement
    cur = rules.currency
    members = tuple(member_ids)
    if winner_id not in members:
        raise SettlementError("winner is not a member of the circle")
    if rules.one_win_per_member and winner_id in prior_winners:
        raise SettlementError("member has already won in this circle")
    if payout_method == PayoutMethod.AGREED_DISCOUNT and not rules.allow_agreed_discount:
        raise SettlementError("agreed-discount payouts are not enabled in this ruleset")
    plan = compute_contributions(rules, members, cycle_id)
    V = Money(rules.total_chit_value, cur)
    D = discount if discount is not None else Money.zero(cur)
    adjustments = list(plan.adjustments)

    if payout_method in DISCOUNT_FUNDED:
        if D.minor <= 0 or D.currency != cur:
            raise SettlementError("a positive discount in the settlement currency is required")
        if D.minor > rules.discount_cap_minor():
            raise SettlementError("discount exceeds the permitted cap")
        F = compute_commission(rules, D)
        W, P = V - D, D - F
        if P.is_negative:
            raise CommissionNotFundableError("commission exceeds the winning discount")
    else:
        if not D.is_zero:
            raise SettlementError("discount is only valid for discount-funded payout methods")
        F = compute_commission(rules, D)
        W, P = V - F, Money.zero(cur)
        if W.is_negative:
            raise CommissionNotFundableError("commission exceeds the pot")

    dividends = {m: Money.zero(cur) for m in members}
    remainder, destination = Money.zero(cur), None
    if P.minor > 0:
        if rules.dividend.allocation == DividendAllocation.ALL_MEMBERS:
            recipients = list(members)
        else:
            elig = set(eligible_for_dividend or ())
            if not elig <= set(members):
                raise SettlementError("dividend-eligible set contains non-members")
            recipients = [m for m in members if m in elig]
            if not recipients:
                raise SettlementError("dividend pool is positive but no member is eligible")
        shares, remainder = split_equal(P, len(recipients))
        for m, s in zip(recipients, shares):
            dividends[m] = s
        if remainder.minor > 0:
            if rules.rounding.remainder_destination is None:
                raise RoundingPolicyIncompleteError(
                    "dividend split leaves a remainder but the ruleset defines no remainder destination")
            destination = rules.rounding.remainder_destination.value
            adjustments.append(RoundingAdjustment(
                cycle_id, cur, "DIVIDEND_SPLIT",
                f"{remainder.minor} minor unit(s) remain after equal split of the dividend pool",
                rules.version, remainder, destination))

    net = {m: plan.contributions[m] - dividends[m] for m in members}
    s = Settlement(rules.circle_id, cycle_id, rules.version, rules.fingerprint(), cur, payout_method,
                   winner_id, members, V, D, W, F, P, dict(plan.contributions), dividends, net,
                   remainder, destination, tuple(adjustments))
    violations = check_settlement(s, rules, prior_winners)
    if violations:
        raise SettlementValidationError(violations)
    return s
