import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from financial_engine.rules import Ruleset  # noqa: E402

BASE = dict(
    circle_id="c1", version=1, currency="INR", total_chit_value=10_000_000, member_count=20,
    payout_mode="SEALED_BID_AUCTION",
    commission=dict(base="PERCENT_OF_CHIT_VALUE", rate="0.05", rounding="HALF_UP"),
    dividend=dict(allocation="ALL_MEMBERS"),
    auction=dict(max_discount_rate="0.40", min_discount=0, increment=0,
                 tie_break="EARLIEST_BID", no_bid_fallback="HOLD"),
    grace_period_days=5, rounding=dict(contribution_remainder="REJECT", remainder_destination=None),
    required_approvals=1, require_security=False, jurisdiction_profile="IN-SANDBOX",
    effective_date="2026-10-22", status="ACTIVE",
)


def rules_dict(**over):
    d = copy.deepcopy(BASE)
    d.update(over)
    return d


def make_rules(**over) -> Ruleset:
    return Ruleset.from_dict(rules_dict(**over))


def members(n=20):
    return [f"m{i:02d}" for i in range(1, n + 1)]
