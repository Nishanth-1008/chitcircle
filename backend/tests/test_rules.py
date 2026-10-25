import pytest

from financial_engine.rules import Ruleset, RulesetError
from .conftest import make_rules, rules_dict


def test_roundtrip_and_stable_fingerprint():
    r = make_rules()
    assert Ruleset.from_dict(r.to_dict()) == r
    assert r.fingerprint() == make_rules().fingerprint()
    assert r.fingerprint() != make_rules(grace_period_days=6).fingerprint()


@pytest.mark.parametrize("over", [
    dict(currency="XXX"), dict(total_chit_value=0), dict(member_count=1), dict(required_approvals=0),
    dict(grace_period_days=-1), dict(auction=None),
    dict(commission=dict(base="PERCENT_OF_CHIT_VALUE", rate="1.5", rounding="HALF_UP")),
    dict(commission=dict(base="FIXED_AMOUNT", rounding="HALF_UP")),
    dict(commission=dict(base="PERCENT_OF_CHIT_VALUE", rate="0.05", rounding="HALF_UP",
                         min_amount=10, max_amount=5)),
    dict(payout_mode="AGREED_DISCOUNT"), dict(allow_agreed_discount=True),
])
def test_invalid_rulesets_rejected(over):
    with pytest.raises(RulesetError):
        make_rules(**over)


def test_missing_required_field_rejected():
    d = rules_dict()
    del d["grace_period_days"]       # engine must not invent a grace period
    with pytest.raises(RulesetError):
        Ruleset.from_dict(d)


def test_rotation_ruleset_needs_no_auction():
    assert make_rules(payout_mode="FIXED_ROTATION", auction=None).auction is None
