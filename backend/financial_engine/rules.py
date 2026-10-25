"""Versioned, immutable financial rulesets."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum
from fractions import Fraction
from typing import Any, Optional

from .errors import FinancialEngineError
from .money import CURRENCY_EXPONENTS, RoundingMode


class RulesetError(FinancialEngineError, ValueError):
    pass


class PayoutMethod(str, Enum):
    FIXED_ROTATION = "FIXED_ROTATION"
    LOTTERY = "LOTTERY"
    SEALED_BID_AUCTION = "SEALED_BID_AUCTION"
    OPEN_BID_AUCTION = "OPEN_BID_AUCTION"
    AGREED_DISCOUNT = "AGREED_DISCOUNT"


AUCTION_MODES = {PayoutMethod.SEALED_BID_AUCTION, PayoutMethod.OPEN_BID_AUCTION}
DISCOUNT_FUNDED = AUCTION_MODES | {PayoutMethod.AGREED_DISCOUNT}


class CommissionBase(str, Enum):
    PERCENT_OF_CHIT_VALUE = "PERCENT_OF_CHIT_VALUE"
    PERCENT_OF_DISCOUNT = "PERCENT_OF_DISCOUNT"
    FIXED_AMOUNT = "FIXED_AMOUNT"


class DividendAllocation(str, Enum):
    ALL_MEMBERS = "ALL_MEMBERS"
    ELIGIBLE_MEMBERS = "ELIGIBLE_MEMBERS"


class RemainderDestination(str, Enum):
    ORGANIZER = "ORGANIZER"
    CIRCLE_RESERVE = "CIRCLE_RESERVE"


class ContributionRemainder(str, Enum):
    REJECT = "REJECT"
    SPREAD_BY_MEMBER_ORDER = "SPREAD_BY_MEMBER_ORDER"


class TieBreak(str, Enum):
    EARLIEST_BID = "EARLIEST_BID"
    LOWEST_POSITION = "LOWEST_POSITION"
    SEEDED_RANDOM = "SEEDED_RANDOM"


class NoBidFallback(str, Enum):
    FIXED_ROTATION = "FIXED_ROTATION"
    LOTTERY = "LOTTERY"
    HOLD = "HOLD"


class RulesetStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class CommissionConfig:
    base: CommissionBase
    rounding: RoundingMode                      # required: no silent default
    rate: Optional[Decimal] = None
    fixed_amount: Optional[int] = None          # minor units
    min_amount: Optional[int] = None
    max_amount: Optional[int] = None


@dataclass(frozen=True)
class DividendConfig:
    allocation: DividendAllocation


@dataclass(frozen=True)
class AuctionRules:
    max_discount_rate: Decimal                  # cap as fraction of chit value
    tie_break: TieBreak
    no_bid_fallback: NoBidFallback
    min_discount: int = 0                       # minor units
    increment: int = 0                          # minor units; 0 = none


@dataclass(frozen=True)
class RoundingPolicy:
    contribution_remainder: ContributionRemainder = ContributionRemainder.REJECT
    # Open decision in the spec: left unset unless the circle configures it.
    remainder_destination: Optional[RemainderDestination] = None


@dataclass(frozen=True)
class Ruleset:
    circle_id: str
    version: int
    currency: str
    total_chit_value: int
    member_count: int
    payout_mode: PayoutMethod
    commission: CommissionConfig
    dividend: DividendConfig
    grace_period_days: int                      # required: engine never invents one
    rounding: RoundingPolicy
    required_approvals: int
    jurisdiction_profile: str
    effective_date: date
    auction: Optional[AuctionRules] = None
    contribution_schedule: dict = field(default_factory=lambda: {"frequency": "MONTHLY"})
    require_security: bool = True
    status: RulesetStatus = RulesetStatus.DRAFT
    allow_agreed_discount: bool = False
    early_payout_min_consent_rate: Optional[Decimal] = None
    require_full_collection_before_payout: bool = True
    one_win_per_member: bool = True

    def __post_init__(self) -> None:
        errs: list[str] = []
        if self.currency not in CURRENCY_EXPONENTS:
            errs.append(f"unsupported currency {self.currency}")
        if self.version < 1:
            errs.append("version must be >= 1")
        if self.total_chit_value <= 0:
            errs.append("total_chit_value must be positive")
        if self.member_count < 2:
            errs.append("member_count must be >= 2")
        if self.payout_mode == PayoutMethod.AGREED_DISCOUNT:
            errs.append("AGREED_DISCOUNT is a per-cycle request, not a circle payout mode")
        if self.grace_period_days < 0:
            errs.append("grace_period_days must be >= 0")
        if self.required_approvals < 1:
            errs.append("required_approvals must be >= 1 (approval cannot be bypassed)")
        c = self.commission
        if c.base == CommissionBase.FIXED_AMOUNT:
            if c.fixed_amount is None or c.fixed_amount < 0:
                errs.append("FIXED_AMOUNT commission needs fixed_amount >= 0")
        else:
            if c.rate is None or not (Decimal(0) <= c.rate <= Decimal(1)):
                errs.append("percentage commission needs 0 <= rate <= 1")
        if c.min_amount is not None and c.max_amount is not None and c.min_amount > c.max_amount:
            errs.append("commission min_amount > max_amount")
        if (self.payout_mode in AUCTION_MODES or self.allow_agreed_discount) and self.auction is None:
            errs.append("auction rules are required for auctions and agreed-discount payouts")
        if self.auction and not (Decimal(0) < self.auction.max_discount_rate < Decimal(1)):
            errs.append("auction.max_discount_rate must be in (0, 1)")
        if self.auction and (self.auction.min_discount < 0 or self.auction.increment < 0):
            errs.append("auction min_discount/increment must be >= 0")
        if self.allow_agreed_discount:
            r = self.early_payout_min_consent_rate
            if r is None or not (Decimal(0) < r <= Decimal(1)):
                errs.append("agreed-discount payouts need early_payout_min_consent_rate in (0, 1]")
        if errs:
            raise RulesetError("; ".join(errs))

    # serialisation ----------------------------------------------------
    def to_dict(self) -> dict:
        def conv(o: Any) -> Any:
            if isinstance(o, Enum):
                return o.value
            if isinstance(o, Decimal):
                return str(o)
            if isinstance(o, date):
                return o.isoformat()
            if hasattr(o, "__dataclass_fields__"):
                return {k: conv(getattr(o, k)) for k in o.__dataclass_fields__}
            if isinstance(o, dict):
                return {k: conv(v) for k, v in o.items()}
            return o
        return conv(self)

    def fingerprint(self) -> str:
        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()

    @classmethod
    def from_dict(cls, d: dict) -> "Ruleset":
        def dec(v: Any) -> Optional[Decimal]:
            return None if v is None else Decimal(str(v))
        try:
            c = d["commission"]
            commission = CommissionConfig(
                base=CommissionBase(c["base"]), rounding=RoundingMode(c["rounding"]),
                rate=dec(c.get("rate")), fixed_amount=c.get("fixed_amount"),
                min_amount=c.get("min_amount"), max_amount=c.get("max_amount"))
            a = d.get("auction")
            auction = None if a is None else AuctionRules(
                max_discount_rate=Decimal(str(a["max_discount_rate"])),
                tie_break=TieBreak(a["tie_break"]), no_bid_fallback=NoBidFallback(a["no_bid_fallback"]),
                min_discount=a.get("min_discount", 0), increment=a.get("increment", 0))
            r = d.get("rounding") or {}
            rd = r.get("remainder_destination")
            rounding = RoundingPolicy(
                ContributionRemainder(r.get("contribution_remainder", "REJECT")),
                RemainderDestination(rd) if rd else None)
            kwargs = dict(
                circle_id=d["circle_id"], version=d["version"], currency=d["currency"],
                total_chit_value=d["total_chit_value"], member_count=d["member_count"],
                payout_mode=PayoutMethod(d["payout_mode"]), commission=commission,
                dividend=DividendConfig(DividendAllocation(d["dividend"]["allocation"])),
                grace_period_days=d["grace_period_days"], rounding=rounding,
                required_approvals=d["required_approvals"],
                jurisdiction_profile=d["jurisdiction_profile"],
                effective_date=date.fromisoformat(str(d["effective_date"])), auction=auction)
            for k in ("contribution_schedule", "require_security", "allow_agreed_discount",
                      "require_full_collection_before_payout", "one_win_per_member"):
                if k in d:
                    kwargs[k] = d[k]
            if "status" in d:
                kwargs["status"] = RulesetStatus(d["status"])
            if d.get("early_payout_min_consent_rate") is not None:
                kwargs["early_payout_min_consent_rate"] = dec(d["early_payout_min_consent_rate"])
            return cls(**kwargs)
        except RulesetError:
            raise
        except (KeyError, ValueError, TypeError, ArithmeticError) as exc:
            raise RulesetError(f"invalid ruleset: {exc!r}") from exc

    # helpers ----------------------------------------------------------
    def discount_cap_minor(self) -> int:
        """Largest permitted discount (floor of rate * chit value)."""
        from .money import round_fraction
        if self.auction is None:
            return self.total_chit_value
        return round_fraction(Fraction(self.total_chit_value) * Fraction(self.auction.max_discount_rate),
                              RoundingMode.DOWN)


def commission_fraction(rate: Decimal) -> Fraction:
    return Fraction(rate)
