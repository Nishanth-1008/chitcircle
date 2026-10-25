"""Fixed rotation, lottery, and agreed-discount early payout."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Mapping, Optional, Sequence

from .auction import (AuctionOutcome, MemberStanding, RejectReason, discount_violations,
                      in_arrears_past_grace)
from .errors import FinancialEngineError
from .money import Money
from .rules import Ruleset


class PayoutModeError(FinancialEngineError):
    pass


class NoEligibleMembersError(PayoutModeError):
    pass


class EarlyPayoutRejected(PayoutModeError):
    def __init__(self, reasons: Sequence[str]):
        self.reasons = list(reasons)
        super().__init__("early payout rejected: " + ", ".join(self.reasons))


# fixed rotation ---------------------------------------------------------
def rotation_recipient(order: Sequence[str], cycle_number: int, prior_winners: frozenset,
                       one_win_per_member: bool = True) -> str:
    if not 1 <= cycle_number <= len(order):
        raise PayoutModeError("cycle number is outside the agreed rotation order")
    recipient = order[cycle_number - 1]
    if one_win_per_member and recipient in prior_winners:
        raise PayoutModeError("scheduled recipient has already received a payout")
    return recipient


# lottery ----------------------------------------------------------------
ALGORITHM = "SHA256_MOD_V1"


@dataclass(frozen=True)
class LotteryRecord:
    cycle_id: str
    ruleset_version: int
    eligible_member_ids: tuple
    seed_commitment: str
    seed: str
    winner_member_id: str
    algorithm: str = ALGORITHM

    def to_dict(self) -> dict:
        return {**self.__dict__, "eligible_member_ids": list(self.eligible_member_ids)}


def commit_seed(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def _draw(cycle_id: str, eligible: Sequence[str], seed: str) -> str:
    h = hashlib.sha256(f"{seed}|{cycle_id}|{','.join(eligible)}".encode()).hexdigest()
    return eligible[int(h, 16) % len(eligible)]


def eligible_for_lottery(rules: Ruleset, standings: Mapping[str, MemberStanding], now: datetime) -> list:
    return sorted(m for m, s in standings.items()
                  if not (rules.one_win_per_member and s.has_won)
                  and not in_arrears_past_grace(s, rules, now))


def run_lottery(cycle_id: str, rules: Ruleset, eligible: Sequence[str], seed: str) -> LotteryRecord:
    ids = tuple(sorted(eligible))
    if not ids:
        raise NoEligibleMembersError("no eligible members for the draw")
    if not seed:
        raise PayoutModeError("a seed is required")
    return LotteryRecord(cycle_id, rules.version, ids, commit_seed(seed), seed, _draw(cycle_id, ids, seed))


def verify_lottery(rec: LotteryRecord) -> bool:
    return (rec.algorithm == ALGORITHM and rec.seed_commitment == commit_seed(rec.seed)
            and rec.winner_member_id == _draw(rec.cycle_id, list(rec.eligible_member_ids), rec.seed))


# agreed-discount early payout ---------------------------------------------
@dataclass(frozen=True)
class EarlyPayoutRequest:
    requester_id: str
    discount: Money
    consenting_member_ids: frozenset
    requested_at: datetime


def evaluate_early_payout(rules: Ruleset, req: EarlyPayoutRequest, member_ids: Sequence[str],
                          standings: Mapping[str, MemberStanding], now: datetime) -> AuctionOutcome:
    """Treat the agreed discount as an uncontested bid, after eligibility and consent checks."""
    if not rules.allow_agreed_discount:
        raise EarlyPayoutRejected(["NOT_ENABLED"])
    reasons: list = []
    s = standings.get(req.requester_id)
    if s is None:
        reasons.append(RejectReason.NOT_ELIGIBLE_MEMBER.value)
    else:
        if rules.one_win_per_member and s.has_won:
            reasons.append(RejectReason.ALREADY_WON.value)
        if in_arrears_past_grace(s, rules, now):
            reasons.append(RejectReason.ARREARS_PAST_GRACE.value)
    known = set(member_ids)
    if not req.consenting_member_ids <= known:
        reasons.append("UNKNOWN_CONSENTING_MEMBER")
    rate = Fraction(len(req.consenting_member_ids & known), rules.member_count)
    if rate < Fraction(rules.early_payout_min_consent_rate):
        reasons.append("INSUFFICIENT_CONSENT")
    reasons += [r.value for r in discount_violations(rules, req.discount)]
    if reasons:
        raise EarlyPayoutRejected(reasons)
    return AuctionOutcome("WON", req.requester_id, req.discount, False, (req.requester_id,), None,
                          (f"agreed discount accepted with consent {len(req.consenting_member_ids)}/{rules.member_count}",))
