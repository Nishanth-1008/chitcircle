"""Base contribution calculation."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import FinancialEngineError
from .money import Money, RoundingAdjustment
from .rules import ContributionRemainder, Ruleset


class ContributionError(FinancialEngineError):
    pass


class ContributionNotDivisibleError(ContributionError):
    pass


@dataclass(frozen=True)
class ContributionPlan:
    contributions: dict          # member_id -> Money
    adjustments: tuple           # tuple[RoundingAdjustment, ...]


def compute_contributions(rules: Ruleset, member_ids: Iterable[str], cycle_id: str) -> ContributionPlan:
    """C = V / N. A non-divisible value follows the configured contribution-rounding policy."""
    ids = tuple(member_ids)
    if len(ids) != rules.member_count or len(set(ids)) != len(ids):
        raise ContributionError("member list must contain exactly member_count distinct members")
    cur = rules.currency
    base, rem = divmod(rules.total_chit_value, rules.member_count)
    if rem == 0:
        return ContributionPlan({m: Money(base, cur) for m in ids}, ())
    if rules.rounding.contribution_remainder == ContributionRemainder.REJECT:
        raise ContributionNotDivisibleError(
            f"chit value {rules.total_chit_value} is not divisible by {rules.member_count} "
            f"and the ruleset rejects remainders")
    contribs = {m: Money(base + (1 if i < rem else 0), cur) for i, m in enumerate(ids)}
    adj = RoundingAdjustment(
        cycle_id, cur, "CONTRIBUTION_SPLIT",
        f"{rem} minor unit(s) spread over the first {rem} member(s) by position",
        rules.version, Money(rem, cur), None)
    return ContributionPlan(contribs, (adj,))


def net_contribution(contribution: Money, dividend_credit: Money) -> Money:
    """C_i,net = C_i - d_i. This is an obligation, NOT cash received."""
    return contribution - dividend_credit
