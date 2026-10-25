"""Bid validation and winner selection."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Mapping, Optional, Sequence

from .errors import FinancialEngineError
from .money import Money
from .rules import AUCTION_MODES, NoBidFallback, PayoutMethod, Ruleset, TieBreak


class AuctionError(FinancialEngineError):
    pass


class RejectReason(str, Enum):
    NOT_AN_AUCTION = "NOT_AN_AUCTION"
    AUCTION_NOT_OPEN = "AUCTION_NOT_OPEN"
    NOT_ELIGIBLE_MEMBER = "NOT_ELIGIBLE_MEMBER"
    ALREADY_WON = "ALREADY_WON"
    ARREARS_PAST_GRACE = "ARREARS_PAST_GRACE"
    WRONG_CURRENCY = "WRONG_CURRENCY"
    DISCOUNT_NOT_POSITIVE = "DISCOUNT_NOT_POSITIVE"
    DISCOUNT_ABOVE_CAP = "DISCOUNT_ABOVE_CAP"
    BELOW_MINIMUM = "BELOW_MINIMUM"
    INCREMENT_VIOLATION = "INCREMENT_VIOLATION"
    NOT_HIGHER_THAN_CURRENT = "NOT_HIGHER_THAN_CURRENT"
    DUPLICATE_SEALED_BID = "DUPLICATE_SEALED_BID"


@dataclass(frozen=True)
class Bid:
    bid_id: str
    member_id: str
    discount: Money
    submitted_at: datetime


@dataclass(frozen=True)
class MemberStanding:
    member_id: str
    position: int
    has_won: bool = False
    oldest_unpaid_due: Optional[datetime] = None   # due date of oldest obligation with money outstanding
    exception_granted: bool = False                # permitted dispute/exception state


@dataclass(frozen=True)
class AuctionState:
    is_open: bool
    accepted_bids: tuple = ()


def grace_deadline(due: datetime, grace_days: int) -> datetime:
    return due + timedelta(days=grace_days)


def in_arrears_past_grace(s: MemberStanding, rules: Ruleset, now: datetime) -> bool:
    """Ineligible only once the deadline has strictly passed and money is still owed."""
    if s.exception_granted or s.oldest_unpaid_due is None:
        return False
    return now > grace_deadline(s.oldest_unpaid_due, rules.grace_period_days)


def discount_violations(rules: Ruleset, discount: Money) -> list:
    out = []
    if discount.currency != rules.currency:
        return [RejectReason.WRONG_CURRENCY]
    a = rules.auction
    if discount.minor <= 0:
        out.append(RejectReason.DISCOUNT_NOT_POSITIVE)
    if discount.minor > rules.discount_cap_minor():
        out.append(RejectReason.DISCOUNT_ABOVE_CAP)
    if a is not None:
        if discount.minor < a.min_discount:
            out.append(RejectReason.BELOW_MINIMUM)
        elif a.increment > 0 and (discount.minor - a.min_discount) % a.increment != 0:
            out.append(RejectReason.INCREMENT_VIOLATION)
    return out


def validate_bid(rules: Ruleset, state: AuctionState, bid: Bid,
                 standing: Optional[MemberStanding], now: datetime) -> list:
    if rules.payout_mode not in AUCTION_MODES or rules.auction is None:
        return [RejectReason.NOT_AN_AUCTION]
    reasons = []
    if not state.is_open:
        reasons.append(RejectReason.AUCTION_NOT_OPEN)
    if standing is None:
        reasons.append(RejectReason.NOT_ELIGIBLE_MEMBER)
    else:
        if rules.one_win_per_member and standing.has_won:
            reasons.append(RejectReason.ALREADY_WON)
        if in_arrears_past_grace(standing, rules, now):
            reasons.append(RejectReason.ARREARS_PAST_GRACE)
    reasons += discount_violations(rules, bid.discount)
    if bid.discount.currency == rules.currency:
        if rules.payout_mode == PayoutMethod.SEALED_BID_AUCTION:
            if any(b.member_id == bid.member_id for b in state.accepted_bids):
                reasons.append(RejectReason.DUPLICATE_SEALED_BID)
        elif state.accepted_bids:
            top = max(b.discount.minor for b in state.accepted_bids)
            if bid.discount.minor < top + max(rules.auction.increment, 1):
                reasons.append(RejectReason.NOT_HIGHER_THAN_CURRENT)
    return reasons


@dataclass(frozen=True)
class AuctionOutcome:
    status: str                                  # "WON" | "NO_BIDS"
    winner_member_id: Optional[str]
    discount: Optional[Money]
    tie_break_applied: bool
    tied_member_ids: tuple
    fallback: Optional[NoBidFallback]
    trace: tuple


def _seeded_index(seed: str, ids: Sequence[str]) -> int:
    h = hashlib.sha256(f"{seed}|{','.join(sorted(ids))}".encode()).hexdigest()
    return int(h, 16) % len(ids)


def select_winner(rules: Ruleset, bids: Sequence[Bid], standings: Mapping[str, MemberStanding],
                  seed: Optional[str] = None) -> AuctionOutcome:
    """Highest valid discount wins; ties use the configured tie-break; no bids -> fallback."""
    if rules.auction is None:
        raise AuctionError("ruleset has no auction rules")
    if not bids:
        return AuctionOutcome("NO_BIDS", None, None, False, (), rules.auction.no_bid_fallback,
                              ("no valid bids; configured fallback applies",))
    top = max(b.discount.minor for b in bids)
    tied = [b for b in bids if b.discount.minor == top]
    members = tuple(sorted({b.member_id for b in tied}))
    trace = [f"highest valid discount {top} minor units"]
    if len(members) == 1:
        winner = min(tied, key=lambda b: (b.submitted_at, b.bid_id))
        return AuctionOutcome("WON", winner.member_id, winner.discount, False, members, None, tuple(trace))
    tb = rules.auction.tie_break
    trace.append(f"tie between {len(members)} members; tie-break {tb.value}")
    if tb == TieBreak.EARLIEST_BID:
        winner = min(tied, key=lambda b: (b.submitted_at, b.bid_id)).member_id
    elif tb == TieBreak.LOWEST_POSITION:
        winner = min(members, key=lambda m: standings[m].position)
    else:
        if not seed:
            raise AuctionError("SEEDED_RANDOM tie-break requires a recorded seed")
        winner = sorted(members)[_seeded_index(seed, members)]
    return AuctionOutcome("WON", winner, Money(top, rules.currency), True, members, None, tuple(trace))
