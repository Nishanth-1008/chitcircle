from decimal import Decimal

import pytest
from hypothesis import given, settings, strategies as st

from financial_engine.errors import FinancialEngineError
from financial_engine.money import Money
from financial_engine.rules import PayoutMethod
from financial_engine.settlement import (CommissionLimitError, CommissionNotFundableError,
                                         RoundingPolicyIncompleteError, SettlementError, calculate_settlement)
from financial_engine.validation import check_settlement
from .conftest import make_rules, members

INR = lambda n: Money(n, "INR")  # noqa: E731
AUC = PayoutMethod.SEALED_BID_AUCTION


def test_worked_example_regression():
    """Permanent regression: the ₹1,00,000 example from the concept document."""
    r = make_rules()
    s = calculate_settlement(r, "cy1", members(), "m03", AUC, discount=INR(1_200_000))
    assert s.winner_payout == INR(8_800_000)            # ₹88,000
    assert s.commission == INR(500_000)                 # ₹5,000
    assert s.dividend_pool == INR(700_000)              # ₹7,000
    assert all(d == INR(35_000) for d in s.dividends.values())          # ₹350
    assert all(n == INR(465_000) for n in s.net_contributions.values()) # ₹4,650
    assert sum(n.minor for n in s.net_contributions.values()) == 9_300_000 == (s.winner_payout + s.commission).minor
    assert s.rounding_remainder.is_zero and not s.adjustments
    assert check_settlement(s, r) == []


def test_commission_bases():
    pct_disc = make_rules(commission=dict(base="PERCENT_OF_DISCOUNT", rate="0.25", rounding="HALF_UP"))
    s = calculate_settlement(pct_disc, "c", members(), "m01", AUC, discount=INR(1_200_000))
    assert s.commission == INR(300_000) and s.dividend_pool == INR(900_000)
    fixed = make_rules(commission=dict(base="FIXED_AMOUNT", fixed_amount=250_000, rounding="DOWN"))
    s = calculate_settlement(fixed, "c", members(), "m01", AUC, discount=INR(1_200_000))
    assert s.commission == INR(250_000) and s.dividend_pool == INR(950_000)


def test_commission_limits_rejected():
    r = make_rules(commission=dict(base="PERCENT_OF_CHIT_VALUE", rate="0.05", rounding="HALF_UP", max_amount=400_000))
    with pytest.raises(CommissionLimitError):
        calculate_settlement(r, "c", members(), "m01", AUC, discount=INR(1_200_000))
    r = make_rules(commission=dict(base="PERCENT_OF_CHIT_VALUE", rate="0.05", rounding="HALF_UP", min_amount=600_000))
    with pytest.raises(CommissionLimitError):
        calculate_settlement(r, "c", members(), "m01", AUC, discount=INR(1_200_000))


def test_commission_not_fundable():
    with pytest.raises(CommissionNotFundableError):
        calculate_settlement(make_rules(), "c", members(), "m01", AUC, discount=INR(400_000))


def test_dividend_remainder_needs_destination():
    # pool 700,001 / 20 leaves remainder 1
    r = make_rules()
    with pytest.raises(RoundingPolicyIncompleteError):
        calculate_settlement(r, "c", members(), "m01", AUC, discount=INR(1_200_001))
    r2 = make_rules(rounding=dict(contribution_remainder="REJECT", remainder_destination="CIRCLE_RESERVE"))
    s = calculate_settlement(r2, "c", members(), "m01", AUC, discount=INR(1_200_001))
    assert s.rounding_remainder == INR(1) and s.adjustments[0].destination == "CIRCLE_RESERVE"
    assert check_settlement(s, r2) == []


def test_eligible_member_dividends():
    r = make_rules(dividend=dict(allocation="ELIGIBLE_MEMBERS"))
    elig = members()[:10]
    s = calculate_settlement(r, "c", members(), "m01", AUC, discount=INR(1_200_000), eligible_for_dividend=elig)
    assert s.dividends["m01"] == INR(70_000) and s.dividends["m20"].is_zero
    assert check_settlement(s, r) == []
    with pytest.raises(SettlementError):
        calculate_settlement(r, "c", members(), "m01", AUC, discount=INR(1_200_000), eligible_for_dividend=[])


def test_rotation_has_no_discount_and_commission_comes_from_pot():
    r = make_rules(payout_mode="FIXED_ROTATION", auction=None)
    s = calculate_settlement(r, "c", members(), "m01", PayoutMethod.FIXED_ROTATION)
    assert s.winner_payout == INR(9_500_000) and s.dividend_pool.is_zero
    assert sum(n.minor for n in s.net_contributions.values()) == 10_000_000
    with pytest.raises(SettlementError):
        calculate_settlement(r, "c", members(), "m01", PayoutMethod.FIXED_ROTATION, discount=INR(1))


def test_one_win_and_cap_and_unknown_winner():
    with pytest.raises(SettlementError):
        calculate_settlement(make_rules(), "c", members(), "m01", AUC, discount=INR(1_200_000),
                             prior_winners=frozenset({"m01"}))
    with pytest.raises(SettlementError):
        calculate_settlement(make_rules(), "c", members(), "m01", AUC, discount=INR(4_000_001))
    with pytest.raises(SettlementError):
        calculate_settlement(make_rules(), "c", members(), "zzz", AUC, discount=INR(1_200_000))


def test_tampered_settlement_fails_validation():
    from dataclasses import replace
    r = make_rules()
    s = calculate_settlement(r, "c", members(), "m01", AUC, discount=INR(1_200_000))
    assert "WINNER_PAYOUT_FORMULA" in check_settlement(replace(s, winner_payout=INR(8_800_001)), r)


@settings(max_examples=300, deadline=None)
@given(n=st.integers(2, 30), per=st.integers(1, 2_000_000), rate=st.integers(0, 100),
       disc_pct=st.integers(1, 39), extra=st.integers(0, 999), dist=st.sampled_from(["ALL_MEMBERS", "ELIGIBLE_MEMBERS"]),
       base=st.sampled_from(["PERCENT_OF_CHIT_VALUE", "PERCENT_OF_DISCOUNT", "FIXED_AMOUNT"]),
       k=st.integers(0, 30))
def test_property_settlements_reconcile_or_are_rejected(n, per, rate, disc_pct, extra, dist, base, k):
    commission = dict(base=base, rounding="HALF_EVEN", rate=str(Decimal(rate) / 1000),
                      fixed_amount=per * n // 50)
    try:
        r = make_rules(total_chit_value=per * n, member_count=n, commission=commission,
                       dividend=dict(allocation=dist),
                       rounding=dict(contribution_remainder="REJECT", remainder_destination="ORGANIZER"))
    except FinancialEngineError:
        return
    ids = members(n)
    D = Money(min(r.discount_cap_minor(), per * n * disc_pct // 100 + extra), "INR")
    elig = ids[: min(k, n)]
    try:
        s = calculate_settlement(r, "cy", ids, ids[0], AUC, discount=D, eligible_for_dividend=elig)
    except FinancialEngineError:
        return                      # invalid configurations are rejected, never partially produced
    assert check_settlement(s, r) == []
    assert all(not m.is_negative for m in [*s.dividends.values(), *s.net_contributions.values()])
    assert sum(x.minor for x in s.net_contributions.values()) == (s.winner_payout + s.commission + s.rounding_remainder).minor
    assert (s.rounding_remainder.minor > 0) == any(a.calculation == "DIVIDEND_SPLIT" for a in s.adjustments)
