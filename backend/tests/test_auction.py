from datetime import datetime, timedelta, timezone

import pytest

from financial_engine.auction import (AuctionError, AuctionState, Bid, MemberStanding, RejectReason,
                                      select_winner, validate_bid)
from financial_engine.money import Money
from financial_engine.payout_modes import (EarlyPayoutRejected, EarlyPayoutRequest, NoEligibleMembersError,
                                           PayoutModeError, evaluate_early_payout, rotation_recipient,
                                           run_lottery, verify_lottery)
from .conftest import make_rules, members

T0 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
INR = lambda n: Money(n, "INR")  # noqa: E731


def standings(**over):
    d = {m: MemberStanding(m, i + 1) for i, m in enumerate(members())}
    d.update(over)
    return d


def bid(i, m, amt, dt=0):
    return Bid(f"b{i}", m, INR(amt), T0 + timedelta(seconds=dt))


def test_bid_rejections():
    r = make_rules(auction=dict(max_discount_rate="0.40", min_discount=100_000, increment=50_000,
                                tie_break="EARLIEST_BID", no_bid_fallback="HOLD"))
    st = standings(m02=MemberStanding("m02", 2, has_won=True))
    open_ = AuctionState(True)
    assert validate_bid(r, open_, bid(1, "m01", 1_200_000), st["m01"], T0) == []
    assert RejectReason.AUCTION_NOT_OPEN in validate_bid(r, AuctionState(False), bid(1, "m01", 1_200_000), st["m01"], T0)
    assert RejectReason.ALREADY_WON in validate_bid(r, open_, bid(1, "m02", 1_200_000), st["m02"], T0)
    assert RejectReason.NOT_ELIGIBLE_MEMBER in validate_bid(r, open_, bid(1, "zz", 1_200_000), None, T0)
    assert RejectReason.DISCOUNT_ABOVE_CAP in validate_bid(r, open_, bid(1, "m01", 4_000_050), st["m01"], T0)
    assert RejectReason.BELOW_MINIMUM in validate_bid(r, open_, bid(1, "m01", 50_000), st["m01"], T0)
    assert RejectReason.INCREMENT_VIOLATION in validate_bid(r, open_, bid(1, "m01", 120_001), st["m01"], T0)
    assert RejectReason.DISCOUNT_NOT_POSITIVE in validate_bid(r, open_, bid(1, "m01", 0), st["m01"], T0)
    wrong = Bid("x", "m01", Money(1_200_000, "USD"), T0)
    assert validate_bid(r, open_, wrong, st["m01"], T0) == [RejectReason.WRONG_CURRENCY]


def test_grace_period_boundary():
    r = make_rules(grace_period_days=5)
    due = T0
    s = MemberStanding("m01", 1, oldest_unpaid_due=due)
    deadline = due + timedelta(days=5)
    b = bid(1, "m01", 1_000_000)
    assert validate_bid(r, AuctionState(True), b, s, deadline) == []                                  # at deadline: eligible
    assert RejectReason.ARREARS_PAST_GRACE in validate_bid(r, AuctionState(True), b, s, deadline + timedelta(microseconds=1))
    exempt = MemberStanding("m01", 1, oldest_unpaid_due=due, exception_granted=True)
    assert validate_bid(r, AuctionState(True), b, exempt, deadline + timedelta(days=9)) == []


def test_sealed_duplicates_and_open_increment():
    sealed = make_rules()
    prior = bid(1, "m01", 1_000_000)
    assert RejectReason.DUPLICATE_SEALED_BID in validate_bid(
        sealed, AuctionState(True, (prior,)), bid(2, "m01", 1_100_000), standings()["m01"], T0)
    open_ = make_rules(payout_mode="OPEN_BID_AUCTION")
    assert RejectReason.NOT_HIGHER_THAN_CURRENT in validate_bid(
        open_, AuctionState(True, (prior,)), bid(2, "m02", 1_000_000), standings()["m02"], T0)
    assert validate_bid(open_, AuctionState(True, (prior,)), bid(2, "m02", 1_000_001), standings()["m02"], T0) == []


def test_not_an_auction():
    r = make_rules(payout_mode="FIXED_ROTATION", auction=None)
    assert validate_bid(r, AuctionState(True), bid(1, "m01", 1), standings()["m01"], T0) == [RejectReason.NOT_AN_AUCTION]


def test_winner_selection_and_tiebreaks():
    st = standings()
    bids = [bid(1, "m05", 1_000_000, 5), bid(2, "m03", 1_200_000, 9), bid(3, "m07", 1_200_000, 2)]
    o = select_winner(make_rules(), bids, st)
    assert o.winner_member_id == "m07" and o.tie_break_applied            # EARLIEST_BID
    lp = make_rules(auction=dict(max_discount_rate="0.4", tie_break="LOWEST_POSITION", no_bid_fallback="HOLD"))
    assert select_winner(lp, bids, st).winner_member_id == "m03"
    rnd = make_rules(auction=dict(max_discount_rate="0.4", tie_break="SEEDED_RANDOM", no_bid_fallback="HOLD"))
    w1 = select_winner(rnd, bids, st, seed="s").winner_member_id
    assert w1 == select_winner(rnd, list(reversed(bids)), st, seed="s").winner_member_id   # deterministic
    with pytest.raises(AuctionError):
        select_winner(rnd, bids, st)
    assert select_winner(make_rules(), bids[:2], st).winner_member_id == "m03" and not select_winner(make_rules(), bids[:2], st).tie_break_applied


def test_no_bid_fallback():
    o = select_winner(make_rules(auction=dict(max_discount_rate="0.4", tie_break="EARLIEST_BID",
                                              no_bid_fallback="LOTTERY")), [], standings())
    assert o.status == "NO_BIDS" and o.fallback.value == "LOTTERY"


def test_rotation():
    order = members(4)
    assert rotation_recipient(order, 2, frozenset({"m01"})) == "m02"
    with pytest.raises(PayoutModeError):
        rotation_recipient(order, 1, frozenset({"m01"}))
    with pytest.raises(PayoutModeError):
        rotation_recipient(order, 5, frozenset())


def test_lottery_is_auditable():
    r = make_rules(payout_mode="LOTTERY", auction=None)
    rec = run_lottery("cy1", r, members(), "seed-1")
    assert verify_lottery(rec)
    assert not verify_lottery(type(rec)(**{**rec.__dict__, "winner_member_id": "m99"}))
    assert rec.winner_member_id == run_lottery("cy1", r, list(reversed(members())), "seed-1").winner_member_id
    with pytest.raises(NoEligibleMembersError):
        run_lottery("cy1", r, [], "s")


def test_early_payout():
    r = make_rules(allow_agreed_discount=True, early_payout_min_consent_rate="0.75")
    st = standings()
    ok = EarlyPayoutRequest("m01", INR(1_200_000), frozenset(members()[:15]), T0)
    o = evaluate_early_payout(r, ok, members(), st, T0)
    assert o.winner_member_id == "m01" and o.discount == INR(1_200_000)
    low = EarlyPayoutRequest("m01", INR(1_200_000), frozenset(members()[:14]), T0)
    with pytest.raises(EarlyPayoutRejected) as e:
        evaluate_early_payout(r, low, members(), st, T0)
    assert "INSUFFICIENT_CONSENT" in e.value.reasons
    with pytest.raises(EarlyPayoutRejected):
        evaluate_early_payout(make_rules(), ok, members(), st, T0)       # not enabled
