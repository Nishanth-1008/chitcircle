"""Transparent rule-based risk indicators. Advisory only: they cannot move money, change contributions,
alter auction outcomes, waive security or bypass approval."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .obligations import SecurityStatus


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True)
class PaymentRecord:
    delay_days: int
    settled: bool = True


@dataclass(frozen=True)
class RiskAssessment:
    indicator: RiskLevel
    points: int
    factors: tuple
    required_security_level: str
    organizer_alert: bool
    review_recommendation: str
    disclaimer: str = "Rule-based indicator; not a statistically validated default prediction."


def assess_risk(records: list, remaining_obligations: int, completed_cycles: int,
                security_status: SecurityStatus, has_won: bool) -> RiskAssessment:
    points, factors = 0, []
    n = len(records)
    if n:
        avg = sum(r.delay_days for r in records) / n
        on_time = sum(1 for r in records if r.delay_days == 0 and r.settled) / n
        recent = records[-3:]
        recent_avg = sum(r.delay_days for r in recent) / len(recent)
        if avg > 7:
            points += 2; factors.append(f"average payment delay {avg:.1f} days (> 7)")
        elif avg > 2:
            points += 1; factors.append(f"average payment delay {avg:.1f} days (> 2)")
        if on_time < 0.5:
            points += 3; factors.append(f"on-time share {on_time:.0%} (< 50%)")
        elif on_time < 0.8:
            points += 1; factors.append(f"on-time share {on_time:.0%} (< 80%)")
        if len(records) > 3 and recent_avg > avg + 2:
            points += 1; factors.append("recent payments are later than the member's overall average")
        if any(not r.settled for r in records):
            points += 1; factors.append("at least one obligation is still unpaid")
    else:
        factors.append("no payment history yet")
    if has_won and remaining_obligations > 0:
        points += 1; factors.append(f"{remaining_obligations} contribution(s) remain after payout")
        if security_status != SecurityStatus.VERIFIED:
            points += 2; factors.append("guarantor/collateral not verified")
    if completed_cycles == 0:
        points += 1; factors.append("no completed circle history")
    level = RiskLevel.LOW if points <= 1 else RiskLevel.MEDIUM if points <= 3 else RiskLevel.HIGH
    sec = {RiskLevel.LOW: "STANDARD", RiskLevel.MEDIUM: "GUARANTOR", RiskLevel.HIGH: "COLLATERAL"}[level]
    rec = {RiskLevel.LOW: "No review needed", RiskLevel.MEDIUM: "Organizer review suggested",
           RiskLevel.HIGH: "Manual review recommended before payout"}[level]
    return RiskAssessment(level, points, tuple(factors), sec, level != RiskLevel.LOW, rec)
