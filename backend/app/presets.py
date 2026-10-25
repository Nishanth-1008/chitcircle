"""Preset rulesets for common chit circle configurations."""

from datetime import date
from financial_engine.rules import Ruleset, PayoutMethod, DividendAllocation, RemainderDestination, ContributionRemainder
from financial_engine.auction import NoBidFallback, TieBreak
from financial_engine.money import Money


def indian_auction_chit(
    circle_id: str,
    total_chit_value: int = 1_000_000,
    member_count: int = 20,
    commission_rate: float = 0.05,  # 5%
    grace_period_days: int = 3,
) -> Ruleset:
    """Indian-style auction chit fund (classic chit fund)."""
    return Ruleset.from_dict({
        "circle_id": circle_id,
        "version": 1,
        "status": "ACTIVE",
        "total_chit_value": total_chit_value,
        "member_count": member_count,
        "currency": "INR",
        "payout_mode": PayoutMethod.SEALED_BID_AUCTION.value,
        "effective_date": date.today().isoformat(),
        "auction": {
            "max_discount_rate": "0.30",
            "tie_break": TieBreak.EARLIEST_BID.value,
            "no_bid_fallback": NoBidFallback.FIXED_ROTATION.value,
            "min_discount": 0,
            "increment": 10000,
        },
        "dividend": {
            "allocation": DividendAllocation.ELIGIBLE_MEMBERS.value,
        },
        "grace_period_days": grace_period_days,
        "commission": {"base": "PERCENT_OF_CHIT_VALUE", "rate": commission_rate, "rounding": "HALF_UP"},
        "rounding": {
            "contribution_remainder": ContributionRemainder.REJECT.value,
            "remainder_destination": RemainderDestination.ORGANIZER.value,
        },
        "one_win_per_member": True,
        "require_full_collection_before_payout": True,
        "required_approvals": 2,
        "no_bid_fallback": NoBidFallback.FIXED_ROTATION.value,
        "jurisdiction_profile": "INDIA_CHA",
        "allow_agreed_discount": True,
        "require_security": False,
        "early_payout_min_consent_rate": "0.75",
    })


def tanda_rotation(
    circle_id: str,
    total_chit_value: int = 10_000,
    member_count: int = 10,
    commission_rate: float = 0.0,
    grace_period_days: int = 7,
) -> Ruleset:
    """Tanda / ROSCA - fixed rotation, no auction."""
    return Ruleset.from_dict({
        "circle_id": circle_id,
        "version": 1,
        "status": "ACTIVE",
        "total_chit_value": total_chit_value,
        "member_count": member_count,
        "currency": "USD",
        "payout_mode": PayoutMethod.FIXED_ROTATION.value,
        "effective_date": date.today().isoformat(),
        "dividend": {
            "allocation": DividendAllocation.ALL_MEMBERS.value,
        },
        "grace_period_days": grace_period_days,
        "commission": {"base": "PERCENT_OF_CHIT_VALUE", "rate": commission_rate, "rounding": "HALF_UP"},
        "rounding": {
            "contribution_remainder": ContributionRemainder.REJECT.value,
            "remainder_destination": RemainderDestination.ORGANIZER.value,
        },
        "one_win_per_member": True,
        "require_full_collection_before_payout": True,
        "required_approvals": 1,
        "no_bid_fallback": NoBidFallback.FIXED_ROTATION.value,
        "jurisdiction_profile": "US_ROSCA",
        "allow_agreed_discount": False,
        "require_security": False,
    })


def agreed_discount_early_payout(
    circle_id: str,
    total_chit_value: int = 50_000,
    member_count: int = 10,
    commission_rate: float = 0.02,  # 2%
    grace_period_days: int = 5,
) -> Ruleset:
    """Agreed-discount early payout model (circle uses fixed rotation, early payout requested per cycle)."""
    return Ruleset.from_dict({
        "circle_id": circle_id,
        "version": 1,
        "status": "ACTIVE",
        "total_chit_value": total_chit_value,
        "member_count": member_count,
        "currency": "USD",
        "payout_mode": PayoutMethod.FIXED_ROTATION.value,
        "effective_date": date.today().isoformat(),
        "auction": {
            "max_discount_rate": "0.30",
            "tie_break": TieBreak.EARLIEST_BID.value,
            "no_bid_fallback": NoBidFallback.FIXED_ROTATION.value,
            "min_discount": 0,
            "increment": 1000,
        },
        "dividend": {
            "allocation": DividendAllocation.ELIGIBLE_MEMBERS.value,
        },
        "grace_period_days": grace_period_days,
        "commission": {"base": "PERCENT_OF_CHIT_VALUE", "rate": commission_rate, "rounding": "HALF_UP"},
        "rounding": {
            "contribution_remainder": ContributionRemainder.REJECT.value,
            "remainder_destination": RemainderDestination.ORGANIZER.value,
        },
        "one_win_per_member": False,
        "require_full_collection_before_payout": False,
        "required_approvals": 1,
        "no_bid_fallback": NoBidFallback.FIXED_ROTATION.value,
        "jurisdiction_profile": "US_AGREED_DISCOUNT",
        "allow_agreed_discount": True,
        "require_security": False,
        "early_payout_min_consent_rate": "0.75",
    })


def demo_presets() -> dict[str, callable]:
    """Return all demo presets as a dictionary."""
    return {
        "indian_auction_chit": indian_auction_chit,
        "tanda_rotation": tanda_rotation,
        "agreed_discount_early_payout": agreed_discount_early_payout,
    }