import pytest

from financial_engine.contributions import ContributionNotDivisibleError, compute_contributions
from financial_engine.obligations import MemberObligation
from datetime import datetime, timezone
from .conftest import make_rules, members


def test_even_split():
    plan = compute_contributions(make_rules(), members(), "cy1")
    assert all(m.minor == 500_000 for m in plan.contributions.values()) and not plan.adjustments


def test_non_divisible_rejected_by_default():
    with pytest.raises(ContributionNotDivisibleError):
        compute_contributions(make_rules(total_chit_value=10_000_001), members(), "cy1")


def test_spread_policy_is_explicit_and_reconciles():
    r = make_rules(total_chit_value=10_000_003,
                   rounding=dict(contribution_remainder="SPREAD_BY_MEMBER_ORDER", remainder_destination=None))
    plan = compute_contributions(r, members(), "cy1")
    assert sum(m.minor for m in plan.contributions.values()) == 10_000_003
    assert plan.adjustments[0].amount.minor == 3 and plan.adjustments[0].calculation == "CONTRIBUTION_SPLIT"


def test_dividend_credit_is_not_cash():
    ob = MemberObligation("m1", "cy", "INR", 500_000, datetime(2026, 11, 1, tzinfo=timezone.utc))
    ob.dividend_credit = 35_000
    assert ob.net_payable == 465_000 and ob.confirmed_paid == 0 and ob.outstanding == 465_000
    ob.confirmed_paid = 465_000
    assert ob.outstanding == 0
