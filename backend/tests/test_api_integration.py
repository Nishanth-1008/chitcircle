import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from app.models import LedgerEventRow, LedgerImmutableError, Obligation, SettlementRow
from app.services.gateway import MockGateway, get_gateway
from financial_engine.reconciliation import HmacVerifier
from .conftest import rules_dict

SECRET = "test-secret"
ORG = {"X-Actor-Id": "org1", "X-Actor-Role": "organizer"}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    db.init_db("sqlite://")
    app = create_app()
    gw = MockGateway()
    app.dependency_overrides[get_gateway] = lambda: gw
    client = TestClient(app)
    client.gw = gw
    yield client
    db.engine.dispose()


def ruleset(n=4, V=400_000, **over):
    d = rules_dict(total_chit_value=V, member_count=n, **over)
    for k in ("circle_id", "version"):
        d.pop(k)
    return d


def setup_circle(c, n=4, V=400_000, **over):
    r = c.post("/circles", json={"name": "Test", "ruleset": ruleset(n, V, **over),
                                 "members": [f"member{i}" for i in range(n)]}, headers=ORG)
    assert r.status_code == 201, r.text
    circle = r.json()
    cy = c.post(f"/circles/{circle['id']}/cycles",
                json={"due_date": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, headers=ORG)
    assert cy.status_code == 201, cy.text
    return circle, cy.json()


def member_h(mid):
    return {"X-Actor-Id": mid, "X-Actor-Role": "member"}


def webhook(c, payload, sign=True):
    body = json.dumps(payload).encode()
    h = {"Content-Type": "application/json"}
    if sign:
        h["X-Signature"] = HmacVerifier(SECRET).sign(body)
    return c.post("/webhooks/provider", content=body, headers=h)


def pay(c, cycle_id, member_id, amount, txn):
    return webhook(c, dict(provider_txn_id=txn, kind="PAYMENT", status="COMPLETED", amount=amount,
                           currency="INR", cycle_id=cycle_id, member_id=member_id))


def run_auction(c, circle, cy, bids):
    cid = cy["id"]
    assert c.post(f"/cycles/{cid}/open", headers=ORG).status_code == 200
    assert c.post(f"/cycles/{cid}/auction/open", headers=ORG).status_code == 200
    ms = circle["members"]
    for idx, amt in bids:
        r = c.post(f"/cycles/{cid}/auction/bids", json={"member_id": ms[idx]["id"], "discount": amt},
                   headers=member_h(ms[idx]["id"]))
        assert r.status_code == 200 and r.json()["accepted"], r.json()
    return c.post(f"/cycles/{cid}/auction/close", headers=ORG)


def to_settlement(c, n=4, V=400_000, bids=((1, 120_000), (2, 100_000)), **over):
    circle, cy = setup_circle(c, n, V, **over)
    assert run_auction(c, circle, cy, bids).status_code == 200
    r = c.post(f"/cycles/{cy['id']}/settlement", headers=ORG)
    assert r.status_code == 201, r.text
    return circle, cy, r.json()


def collect(c, circle, cy, settlement):
    for m in circle["members"]:
        net = settlement["settlement"]["net_contributions"][m["id"]]["minor"]
        assert pay(c, cy["id"], m["id"], net, f"pay-{m['id']}").status_code == 200


def approve_and_pay(c, st):
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=ORG).status_code == 200
    return c.post(f"/settlements/{st['id']}/payout", headers=ORG)


def payout_callback(c, st, amount, txn="payout-1", status="COMPLETED"):
    return webhook(c, dict(provider_txn_id=txn, kind="PAYOUT", status=status, amount=amount, currency="INR",
                           payout_reference=st["payout_reference"]))


# --------------------------------------------------------------------------
def test_full_cycle_worked_example_20_members(env):
    c = env
    circle, cy, st = to_settlement(c, n=20, V=10_000_000, bids=((3, 1_200_000), (5, 1_000_000)))
    s = st["settlement"]
    assert s["winner_payout"]["minor"] == 8_800_000 and s["commission"]["minor"] == 500_000
    assert s["dividend_pool"]["minor"] == 700_000
    assert {v["minor"] for v in s["dividends"].values()} == {35_000}
    assert {v["minor"] for v in s["net_contributions"].values()} == {465_000}
    assert s["winner_member_id"] == circle["members"][3]["id"]
    # dividend credit is not cash
    detail = c.get(f"/cycles/{cy['id']}", headers=ORG).json()
    assert all(o["confirmed_paid"] == 0 and o["net_payable"] == 465_000 for o in detail["obligations"])
    collect(c, circle, cy, st)
    r = approve_and_pay(c, st)
    assert r.json()["outcome"] == "SUBMITTED"
    assert payout_callback(c, st, 8_800_000).json()["applied"] == "CONFIRMED"
    f = c.post(f"/settlements/{st['id']}/finalize", headers=ORG)
    assert f.status_code == 200, f.text
    assert c.get(f"/cycles/{cy['id']}", headers=ORG).json()["state"] == "FINALIZED"
    assert c.post(f"/settlements/{st['id']}/finalize", headers=ORG).json()["code"] == "ALREADY_FINALIZED"
    types = [e["type"] for e in c.get(f"/cycles/{cy['id']}/ledger", headers=ORG).json()]
    assert types.count("CONTRIBUTION_DUE") == 20 and types.count("PAYMENT_CONFIRMED") == 20
    assert types.count("DIVIDEND_CREDITED") == 20 and "SETTLEMENT_FINALIZED" in types
    assert c.get(f"/circles/{circle['id']}", headers=ORG).json()["members"][3]["has_won"] is True
    # next cycle can start and the winner can no longer bid
    cy2 = c.post(f"/circles/{circle['id']}/cycles",
                 json={"due_date": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()}, headers=ORG)
    assert cy2.status_code == 201 and cy2.json()["number"] == 2


def test_unsigned_or_badly_signed_webhook_rejected(env, monkeypatch):
    c = env
    circle, cy = setup_circle(c)
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    m = circle["members"][0]["id"]
    payload = dict(provider_txn_id="x", kind="PAYMENT", status="COMPLETED", amount=1, currency="INR",
                   cycle_id=cy["id"], member_id=m)
    assert webhook(c, payload, sign=False).status_code == 401
    body = json.dumps(payload).encode()
    assert c.post("/webhooks/provider", content=body, headers={"X-Signature": "00" * 32}).status_code == 401
    monkeypatch.delenv("WEBHOOK_SECRET")
    assert webhook(c, payload).status_code == 503
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    assert c.get(f"/cycles/{cy['id']}", headers=ORG).json()["obligations"][0]["confirmed_paid"] == 0


def test_duplicate_payment_callback_ignored(env):
    c = env
    circle, cy = setup_circle(c)
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    m = circle["members"][0]["id"]
    assert pay(c, cy["id"], m, 50_000, "t1").json()["duplicate"] is False
    assert pay(c, cy["id"], m, 50_000, "t1").json()["duplicate"] is True
    ob = next(o for o in c.get(f"/cycles/{cy['id']}", headers=ORG).json()["obligations"] if o["member_id"] == m)
    assert ob["confirmed_paid"] == 50_000
    ledger = c.get(f"/cycles/{cy['id']}/ledger", headers=ORG).json()
    assert sum(e["type"] == "PAYMENT_CONFIRMED" for e in ledger) == 1


def test_partial_payments_and_wrong_currency(env):
    c = env
    circle, cy = setup_circle(c)
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    m = circle["members"][0]["id"]
    pay(c, cy["id"], m, 30_000, "a")
    pay(c, cy["id"], m, 20_000, "b")
    ob = next(o for o in c.get(f"/cycles/{cy['id']}", headers=ORG).json()["obligations"] if o["member_id"] == m)
    assert ob["confirmed_paid"] == 50_000 and ob["outstanding"] == 50_000
    bad = webhook(c, dict(provider_txn_id="c", kind="PAYMENT", status="COMPLETED", amount=5, currency="USD",
                          cycle_id=cy["id"], member_id=m))
    assert bad.status_code == 422 and bad.json()["code"] == "CURRENCY_MISMATCH"


def test_duplicate_settlement_request_is_idempotent(env):
    c = env
    circle, cy, st = to_settlement(c)
    before = len(c.get(f"/cycles/{cy['id']}/ledger", headers=ORG).json())
    again = c.post(f"/cycles/{cy['id']}/settlement", headers=ORG).json()
    assert again["already_calculated"] is True and again["id"] == st["id"]
    assert len(c.get(f"/cycles/{cy['id']}/ledger", headers=ORG).json()) == before
    with db.SessionLocal() as s:
        assert len(s.query(SettlementRow).all()) == 1


def test_invalid_settlement_leaves_no_partial_writes(env):
    c = env
    circle, cy = setup_circle(c, commission=dict(base="FIXED_AMOUNT", fixed_amount=150_000, rounding="DOWN"))
    run_auction(c, circle, cy, [(1, 100_000)])               # commission 150k > discount 100k
    with db.SessionLocal() as s:
        events_before = s.query(LedgerEventRow).count()
    r = c.post(f"/cycles/{cy['id']}/settlement", headers=ORG)
    assert r.status_code == 422 and r.json()["code"] == "CommissionNotFundableError"
    with db.SessionLocal() as s:
        assert s.query(SettlementRow).count() == 0 and s.query(LedgerEventRow).count() == events_before
        assert all(o.dividend_credit == 0 for o in s.query(Obligation).all())
    assert c.get(f"/cycles/{cy['id']}", headers=ORG).json()["state"] == "AUCTION_CLOSED"


def test_payout_blocked_until_collection_complete_and_approval(env):
    c = env
    circle, cy, st = to_settlement(c)
    r = c.post(f"/settlements/{st['id']}/payout", headers=ORG)
    assert r.status_code == 409                                    # not approved yet
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=ORG).status_code == 200
    r = c.post(f"/settlements/{st['id']}/payout", headers=ORG)
    assert r.status_code == 409 and r.json()["code"] == "COLLECTIONS_INCOMPLETE"
    assert c.gw.calls == 0


def test_payout_is_never_issued_twice(env):
    c = env
    circle, cy, st = to_settlement(c)
    collect(c, circle, cy, st)
    assert approve_and_pay(c, st).json()["outcome"] == "SUBMITTED"
    again = c.post(f"/settlements/{st['id']}/payout", headers=ORG).json()
    assert again["outcome"] == "ALREADY_REQUESTED"
    assert c.gw.calls == 1 and len(c.gw.submissions) == 1
    with db.SessionLocal() as s:
        assert s.query(LedgerEventRow).filter_by(event_type="PAYOUT_REQUESTED").count() == 1


def test_provider_timeout_is_unresolved_not_success_or_failure(env):
    c = env
    circle, cy, st = to_settlement(c)
    collect(c, circle, cy, st)
    c.gw.mode = "timeout"
    r = approve_and_pay(c, st).json()
    assert r["outcome"] == "UNRESOLVED" and r["cycle_state"] == "PAYOUT_PENDING"
    assert c.post(f"/settlements/{st['id']}/finalize", headers=ORG).status_code == 409
    c.gw.mode = "ok"
    assert c.post(f"/settlements/{st['id']}/payout", headers=ORG).json()["outcome"] == "SUBMITTED"
    assert c.gw.calls == 2 and len(c.gw.submissions) == 1       # same idempotency key reused


def test_failed_payout_moves_to_failed(env):
    c = env
    circle, cy, st = to_settlement(c)
    collect(c, circle, cy, st)
    c.gw.mode = "fail"
    r = approve_and_pay(c, st).json()
    assert r["outcome"] == "FAILED" and r["cycle_state"] == "FAILED"


def test_finalize_requires_verified_payout_and_clean_reconciliation(env):
    c = env
    circle, cy, st = to_settlement(c)
    collect(c, circle, cy, st)
    approve_and_pay(c, st)
    blocked = c.post(f"/settlements/{st['id']}/finalize", headers=ORG)
    assert blocked.status_code == 409                              # payout request is not proof of payout
    assert payout_callback(c, st, 1, txn="bad").json()["applied"] == "MISMATCH_HELD"
    assert c.get(f"/cycles/{cy['id']}", headers=ORG).json()["state"] == "ON_HOLD"
    assert c.post(f"/cycles/{cy['id']}/resume", json={"reason": "checked with provider"}, headers=ORG).status_code == 200
    assert payout_callback(c, st, 280_000, txn="good").json()["applied"] == "CONFIRMED"
    assert payout_callback(c, st, 280_000, txn="good").json()["duplicate"] is True
    assert c.post(f"/settlements/{st['id']}/finalize", headers=ORG).status_code == 200


def test_overpayment_blocks_finalization_until_refunded(env):
    c = env
    circle, cy, st = to_settlement(c)
    ms = circle["members"]
    for i, m in enumerate(ms):                  # member 0 pays the gross contribution, ignoring the dividend credit
        net = st["settlement"]["net_contributions"][m["id"]]["minor"]
        pay(c, cy["id"], m["id"], 100_000 if i == 0 else net, f"p{i}")
    approve_and_pay(c, st)
    payout_callback(c, st, 280_000)
    r = c.post(f"/settlements/{st['id']}/finalize", headers=ORG)
    codes = {d["code"] for d in r.json()["reconciliation"]["payments"]["discrepancies"]}
    assert r.status_code == 409 and "OVERPAID" in codes
    ref = webhook(c, dict(provider_txn_id="refund-1", kind="REFUND", status="COMPLETED", amount=25_000,
                          currency="INR", cycle_id=cy["id"], member_id=ms[0]["id"]))
    assert ref.status_code == 200
    assert c.post(f"/settlements/{st['id']}/finalize", headers=ORG).status_code == 200


def test_ruleset_versions_are_pinned_to_cycles(env):
    c = env
    circle, cy = setup_circle(c)
    new_rules = ruleset(commission=dict(base="PERCENT_OF_CHIT_VALUE", rate="0.10", rounding="HALF_UP"))
    r = c.post(f"/circles/{circle['id']}/rulesets", json={"ruleset": new_rules, "reason": "raise fee"}, headers=ORG)
    assert r.status_code == 201 and r.json()["version"] == 2
    assert c.post(f"/circles/{circle['id']}/rulesets", json={"ruleset": new_rules, "reason": " "},
                  headers=ORG).status_code == 422
    run_auction(c, circle, cy, [(1, 120_000)])
    st = c.post(f"/cycles/{cy['id']}/settlement", headers=ORG).json()
    assert st["ruleset_version"] == 1 and st["settlement"]["commission"]["minor"] == 20_000   # 5%, not 10%
    info = c.get(f"/circles/{circle['id']}", headers=ORG).json()["rulesets"]
    assert [x["status"] for x in info] == ["SUPERSEDED", "ACTIVE"]


def test_authorization_rules(env):
    c = env
    circle, cy = setup_circle(c)
    ms = circle["members"]
    assert c.post(f"/cycles/{cy['id']}/open", headers=member_h(ms[0]["id"])).status_code == 403
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    c.post(f"/cycles/{cy['id']}/auction/open", headers=ORG)
    assert c.post(f"/cycles/{cy['id']}/auction/bids", json={"member_id": ms[1]["id"], "discount": 100_000},
                  headers=member_h(ms[0]["id"])).status_code == 403
    assert c.post(f"/cycles/{cy['id']}/auction/bids", json={"member_id": ms[1]["id"], "discount": 100.5},
                  headers=ORG).status_code == 422                   # floats rejected
    run = c.post(f"/cycles/{cy['id']}/auction/bids", json={"member_id": ms[1]["id"], "discount": 100_000},
                 headers=member_h(ms[1]["id"]))
    assert run.json()["accepted"]
    c.post(f"/cycles/{cy['id']}/auction/close", headers=ORG)
    st = c.post(f"/cycles/{cy['id']}/settlement", headers=ORG).json()
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"},
                  headers=member_h(ms[0]["id"])).status_code == 403
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"},
                  headers={"X-Actor-Id": ms[1]["id"], "X-Actor-Role": "approver"}).status_code == 403   # winner


def test_two_approvals_required(env):
    c = env
    circle, cy, st = to_settlement(c, required_approvals=2)
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=ORG).json()["cycle_state"] == "AWAITING_APPROVAL"
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=ORG).status_code == 409
    second = {"X-Actor-Id": "approver2", "X-Actor-Role": "approver"}
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=second).json()["cycle_state"] == "APPROVED"


def test_security_hold_blocks_payout_until_verified(env):
    c = env
    circle, cy, st = to_settlement(c, require_security=True)
    collect(c, circle, cy, st)
    c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=ORG)
    held = c.post(f"/settlements/{st['id']}/payout", headers=ORG).json()
    assert held["outcome"] == "HELD" and "SECURITY_NOT_VERIFIED" in held["reasons"] and c.gw.calls == 0
    winner = st["settlement"]["winner_member_id"]
    assert c.put(f"/circles/{circle['id']}/members/{winner}/security", json={"status": "VERIFIED"},
                 headers=ORG).status_code == 200
    assert c.post(f"/cycles/{cy['id']}/resume", json={"reason": "guarantor verified"}, headers=ORG).json()["state"] == "APPROVED"
    assert c.post(f"/settlements/{st['id']}/payout", headers=ORG).json()["outcome"] == "SUBMITTED"


def test_sealed_bids_hidden_until_close(env):
    c = env
    circle, cy = setup_circle(c)
    ms = circle["members"]
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    c.post(f"/cycles/{cy['id']}/auction/open", headers=ORG)
    c.post(f"/cycles/{cy['id']}/auction/bids", json={"member_id": ms[1]["id"], "discount": 120_000}, headers=member_h(ms[1]["id"]))
    seen = c.get(f"/cycles/{cy['id']}/auction/bids", headers=member_h(ms[2]["id"])).json()
    assert seen[0]["discount"] is None
    assert c.get(f"/cycles/{cy['id']}/auction/bids", headers=member_h(ms[1]["id"])).json()[0]["discount"] == 120_000
    c.post(f"/cycles/{cy['id']}/auction/close", headers=ORG)
    assert c.get(f"/cycles/{cy['id']}/auction/bids", headers=member_h(ms[2]["id"])).json()[0]["discount"] == 120_000


def test_bid_rejected_after_grace_period_and_is_traceable(env):
    c = env
    circle, cy = setup_circle(c)
    # a cycle whose due date is far in the past => every member is past the 5-day grace period
    with db.SessionLocal() as s:
        from app.models import Cycle
        row = s.get(Cycle, cy["id"])
        row.due_date = datetime.now(timezone.utc) - timedelta(days=30)
        s.commit()
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    c.post(f"/cycles/{cy['id']}/auction/open", headers=ORG)
    m = circle["members"][1]["id"]
    r = c.post(f"/cycles/{cy['id']}/auction/bids", json={"member_id": m, "discount": 100_000}, headers=member_h(m)).json()
    assert r["accepted"] is False and r["reasons"] == ["ARREARS_PAST_GRACE"]
    assert c.get(f"/cycles/{cy['id']}/auction/bids", headers=member_h(m)).json()[0]["accepted"] is False
    out = c.post(f"/cycles/{cy['id']}/auction/close", headers=ORG).json()
    assert out["status"] == "NO_BIDS" and out["fallback"] == "HOLD" and out["cycle"]["state"] == "ON_HOLD"


def test_ledger_is_append_only_and_corrections_are_linked(env):
    c = env
    circle, cy = setup_circle(c)
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    m = circle["members"][0]["id"]
    pay(c, cy["id"], m, 40_000, "t1")
    ev = next(e for e in c.get(f"/cycles/{cy['id']}/ledger", headers=ORG).json() if e["type"] == "PAYMENT_CONFIRMED")
    with db.SessionLocal() as s:
        row = s.get(LedgerEventRow, ev["id"])
        row.amount = 1
        with pytest.raises(LedgerImmutableError):
            s.commit()
        s.rollback()
    r = c.post(f"/ledger/{ev['id']}/reversal", json={"reason": "wrong member"}, headers=ORG)
    assert r.status_code == 200
    assert c.post(f"/ledger/{ev['id']}/reversal", json={"reason": "again"}, headers=ORG).status_code == 409
    ledger = c.get(f"/cycles/{cy['id']}/ledger", headers=ORG).json()
    rev = next(e for e in ledger if e["reverses"] == ev["id"])
    assert rev["amount"] == -40_000 and any(e["id"] == ev["id"] and e["amount"] == 40_000 for e in ledger)
    ob = next(o for o in c.get(f"/cycles/{cy['id']}", headers=ORG).json()["obligations"] if o["member_id"] == m)
    assert ob["confirmed_paid"] == 0


def test_fixed_rotation_cycle(env):
    c = env
    circle, cy = setup_circle(c, payout_mode="FIXED_ROTATION", auction=None)
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    r = c.post(f"/cycles/{cy['id']}/recipient", headers=ORG).json()
    assert r["winner_member_id"] == circle["members"][0]["id"]
    st = c.post(f"/cycles/{cy['id']}/settlement", headers=ORG).json()["settlement"]
    assert st["winner_payout"]["minor"] == 380_000 and st["dividend_pool"]["minor"] == 0
    assert c.post(f"/cycles/{cy['id']}/recipient", headers=ORG).status_code == 409


def test_lottery_cannot_be_rerun(env):
    c = env
    circle, cy = setup_circle(c, payout_mode="LOTTERY", auction=None)
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    r = c.post(f"/cycles/{cy['id']}/recipient", headers=ORG).json()
    assert r["winner_member_id"] in {m["id"] for m in circle["members"]} and r["lottery"]["seed_commitment"]
    again = c.post(f"/cycles/{cy['id']}/recipient", headers=ORG)
    assert again.status_code == 409


def test_agreed_discount_early_payout(env):
    c = env
    circle, cy = setup_circle(c, payout_mode="FIXED_ROTATION", allow_agreed_discount=True,
                              early_payout_min_consent_rate="0.75")
    ms = [m["id"] for m in circle["members"]]
    c.post(f"/cycles/{cy['id']}/open", headers=ORG)
    low = c.post(f"/cycles/{cy['id']}/early-payout", json={"requester_id": ms[2], "discount": 120_000,
                 "consenting_member_ids": ms[:2]}, headers=member_h(ms[2]))
    assert low.status_code == 422 and "INSUFFICIENT_CONSENT" in low.json()["detail"]
    ok = c.post(f"/cycles/{cy['id']}/early-payout", json={"requester_id": ms[2], "discount": 120_000,
                "consenting_member_ids": ms[:3]}, headers=member_h(ms[2])).json()
    assert ok["member_receives"]["minor"] == 280_000 and ok["member_net_contribution"]["minor"] == 75_000
    st = c.post(f"/cycles/{cy['id']}/settlement", headers=ORG).json()
    assert st["settlement"]["payout_method"] == "AGREED_DISCOUNT" and st["status"] == "CALCULATED"


def test_dispute_round_trip_and_risk_endpoint(env):
    c = env
    circle, cy, st = to_settlement(c)
    d = c.post(f"/cycles/{cy['id']}/disputes", json={"reason": "member says paid"}, headers=ORG).json()
    assert d["state"] == "DISPUTED" and d["prior_state"] == "AWAITING_APPROVAL"
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=ORG).status_code == 409
    assert c.post(f"/cycles/{cy['id']}/disputes/resolve", json={"reason": "settled"}, headers=ORG).json()["state"] == "AWAITING_APPROVAL"
    risk = c.get(f"/circles/{circle['id']}/members/{circle['members'][0]['id']}/risk", headers=ORG).json()
    assert risk["indicator"] in ("LOW", "MEDIUM", "HIGH") and "disclaimer" in risk
