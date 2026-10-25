"""Member obligations, payout holds."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

from .rules import Ruleset


class SecurityStatus(str, Enum):
    NONE = "NONE"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"


@dataclass
class MemberObligation:
    member_id: str
    cycle_id: str
    currency: str
    gross_due: int
    due_date: datetime
    dividend_credit: int = 0
    adjustments: int = 0
    confirmed_paid: int = 0       # cash actually confirmed by the provider

    @property
    def net_payable(self) -> int:
        return self.gross_due + self.adjustments - self.dividend_credit

    @property
    def outstanding(self) -> int:
        return max(0, self.net_payable - self.confirmed_paid)

    @property
    def overpaid(self) -> int:
        return max(0, self.confirmed_paid - self.net_payable)

    def grace_deadline(self, grace_days: int) -> datetime:
        return self.due_date + timedelta(days=grace_days)

    def in_arrears_past_grace(self, grace_days: int, now: datetime) -> bool:
        return self.outstanding > 0 and now > self.grace_deadline(grace_days)


@dataclass
class MemberProfile:
    member_id: str
    has_won: bool = False
    completed_cycles: int = 0
    remaining_contributions: int = 0
    security_status: SecurityStatus = SecurityStatus.NONE
    open_disputes: int = 0


def payout_hold_reasons(profile: MemberProfile, rules: Ruleset) -> list[str]:
    """Reasons a payout must be held. A low risk score never waives these."""
    reasons = []
    if rules.require_security and profile.security_status != SecurityStatus.VERIFIED:
        reasons.append("SECURITY_NOT_VERIFIED")
    if profile.open_disputes > 0:
        reasons.append("OPEN_DISPUTE")
    return reasons
