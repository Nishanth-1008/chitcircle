"""Settlement invariants (section 15)."""
from __future__ import annotations

from .money import Money
from .rules import DISCOUNT_FUNDED, Ruleset


def check_settlement(s, rules: Ruleset, prior_winners: frozenset = frozenset()) -> list:
    """Return a list of violated invariants (empty list means valid)."""
    from .errors import FinancialEngineError
    from .settlement import compute_commission
    v: list = []
    cur = rules.currency
    monies = [s.chit_value, s.discount, s.winner_payout, s.commission, s.dividend_pool, s.rounding_remainder,
              *s.contributions.values(), *s.dividends.values(), *s.net_contributions.values()]
    if s.currency != cur or any(m.currency != cur for m in monies):
        return ["CURRENCY_MISMATCH"]
    if s.ruleset_version != rules.version or s.ruleset_fingerprint != rules.fingerprint():
        v.append("RULESET_MISMATCH")
    if any(m.is_negative for m in monies):
        v.append("NEGATIVE_ALLOCATION")
    V = Money(rules.total_chit_value, cur)
    zero = Money.zero(cur)
    if s.chit_value != V:
        v.append("CHIT_VALUE_MISMATCH")
    try:
        f = compute_commission(rules, s.discount)
        if f != s.commission:
            v.append("COMMISSION_MISMATCH")
    except FinancialEngineError:
        v.append("COMMISSION_INVALID")
    if s.payout_method in DISCOUNT_FUNDED:
        if s.winner_payout != V - s.discount:
            v.append("WINNER_PAYOUT_FORMULA")
        if s.dividend_pool != s.discount - s.commission:
            v.append("DIVIDEND_POOL_FORMULA")
    else:
        if s.discount != zero:
            v.append("UNEXPECTED_DISCOUNT")
        if s.winner_payout != V - s.commission:
            v.append("WINNER_PAYOUT_FORMULA")
        if s.dividend_pool != zero:
            v.append("DIVIDEND_POOL_FORMULA")
    if sum(m.minor for m in s.dividends.values()) + s.rounding_remainder.minor != s.dividend_pool.minor:
        v.append("DIVIDENDS_DO_NOT_RECONCILE")
    if s.rounding_remainder.minor > 0 and not s.remainder_destination:
        v.append("REMAINDER_DESTINATION_MISSING")
    if sum(m.minor for m in s.contributions.values()) != V.minor:
        v.append("CONTRIBUTIONS_DO_NOT_SUM_TO_CHIT_VALUE")
    for m in s.member_order:
        if s.net_contributions[m] != s.contributions[m] - s.dividends[m]:
            v.append("NET_CONTRIBUTION_MISMATCH")
            break
    if sum(m.minor for m in s.net_contributions.values()) != (
            s.winner_payout + s.commission + s.rounding_remainder).minor:
        v.append("BALANCE_EQUATION")
    if s.winner_member_id not in s.member_order:
        v.append("WINNER_NOT_A_MEMBER")
    if rules.one_win_per_member and s.winner_member_id in prior_winners:
        v.append("WINNER_ALREADY_WON")
    return v
