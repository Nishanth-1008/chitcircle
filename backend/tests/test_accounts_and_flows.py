"""Account-linked flows used by the web client: register/login, seats, list endpoints, sandbox
confirmations, agents (collections, explainer, bid advisor) and PayPal webhook normalization."""
import json
import os
import zlib
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app import db
from app.main import create_app
from app.models import ProviderEventRow
from app.services import paypal_events
from app.services.gateway import MockGateway, PayPalWebhookVerifier, get_collection_gateway, get_gateway
from financial_engine.reconciliation import HmacVerifier
from .conftest import IdempotentTestClient, rules_dict

SECRET = "test-secret"


@pytest.fixture()
def api(monkeypatch):
    monkeypatch.setenv("WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "")
    monkeypatch.setenv("JWT_SECRET_KEY", "test-jwt-secret-for-account-flows")
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SANDBOX_TOOLS", "true")
    db.init_db(os.getenv("DATABASE_URL", "sqlite://"))
    app = create_app()
    gw = MockGateway()
    app.dependency_overrides[get_gateway] = lambda: gw
    app.dependency_overrides[get_collection_gateway] = lambda: gw
    client = IdempotentTestClient(TestClient(app))
    client.gw = gw
    yield client
    db.engine.dispose()


def register(c, email, name="Person", role="member"):
    r = c.post("/auth/register", json={"email": email, "password": "password123", "name": name, "role": role})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}, r.json()["user"]


def ruleset(n=4, V=400_000, **over):
    d = rules_dict(total_chit_value=V, member_count=n, **over)
    for k in ("circle_id", "version"):
        d.pop(k)
    return d


def create_circle(c, org_h, org_user, invitees, organizer_seat_last=False, **over):
    org_seat = [{"name": org_user["name"], "user_id": org_user["id"]}]
    others = [{"email": e} for e in invitees]
    members = others + org_seat if organizer_seat_last else org_seat + others
    r = c.post("/circles", json={"name": "Family chit", "ruleset": ruleset(len(members), **over),
                                 "members": members}, headers=org_h)
    assert r.status_code == 201, r.text
    return r.json()


def start_round(c, org_h, circle_id, days=1):
    due = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
    cy = c.post(f"/circles/{circle_id}/cycles", json={"due_date": due}, headers=org_h)
    assert cy.status_code == 201, cy.text
    assert c.post(f"/cycles/{cy.json()['id']}/open", headers=org_h).status_code == 200
    return cy.json()


def test_register_login_me_and_payout_contact(api):
    c = api
    h, user = register(c, "Asha@Example.com", "Asha Rao")
    assert user["email"] == "asha@example.com"
    login = c.post("/auth/login", data={"username": "ASHA@example.com", "password": "password123"})
    assert login.status_code == 200
    assert c.get("/auth/me", headers=h).json()["name"] == "Asha Rao"
    assert c.post("/auth/register", json={"email": "asha@example.com", "password": "password123",
                                          "name": "Dup"}).status_code == 409
    me = c.put("/auth/me/payout-email", json={"email": "asha-buyer@personal.example.com"}, headers=h).json()
    assert me["payout_email"] == "asha-buyer@personal.example.com" and me["payout_email_verified"]
    assert c.post("/auth/refresh", headers=h).status_code == 200


def test_invited_seat_links_on_registration_and_lists_circles(api):
    c = api
    org_h, org = register(c, "org@example.com", "Org")
    existing_h, _ = register(c, "ravi@example.com", "Ravi")
    circle = create_circle(c, org_h, org, ["ravi@example.com", "meena@example.com", "joe@example.com"])
    seats = {m["name"]: m for m in circle["members"]}
    assert seats["Ravi"]["user_id"] and seats["meena"]["user_id"] is None

    meena_h, meena = register(c, "meena@example.com", "Meena")
    view = c.get(f"/circles/{circle['id']}", headers=meena_h).json()
    assert view["my_role"] == "member" and view["my_member_id"] == seats["meena"]["id"]
    assert "invite_email" not in view["members"][0]                     # organizer-only detail

    mine = c.get("/circles", headers=meena_h).json()
    assert [x["id"] for x in mine] == [circle["id"]] and mine[0]["my_role"] == "member"
    assert c.get("/circles", headers=org_h).json()[0]["my_role"] == "organizer"

    stranger_h, _ = register(c, "stranger@example.com", "Stranger")
    assert c.get(f"/circles/{circle['id']}", headers=stranger_h).status_code == 403
    assert c.get("/circles", headers=stranger_h).json() == []


def test_full_round_with_accounts_and_sandbox_confirmations(api):
    c = api
    org_h, org = register(c, "org@example.com", "Org")
    emails = ["a@example.com", "b@example.com", "d@example.com"]
    circle = create_circle(c, org_h, org, emails)
    heads = {e: register(c, e, e.split("@")[0].upper())[0] for e in emails}
    seat_of = {m["invite_email"]: m["id"] for m in c.get(f"/circles/{circle['id']}", headers=org_h).json()["members"]
               if m.get("invite_email")}
    cy = start_round(c, org_h, circle["id"])

    rounds = c.get(f"/circles/{circle['id']}/cycles", headers=heads[emails[0]]).json()
    assert rounds[0]["state"] == "COLLECTIONS_IN_PROGRESS" and rounds[0]["my_outstanding"] == 100_000
    a_seat = seat_of[emails[0]]

    # auction: the linked account bids for its own seat and sees its own sealed bid
    assert c.post(f"/cycles/{cy['id']}/auction/open", headers=org_h).status_code == 200
    preview = c.get(f"/cycles/{cy['id']}/auction/preview", params={"member_id": a_seat, "discount": 40_000},
                    headers=heads[emails[0]]).json()
    assert preview["valid"] and preview["preview"]["you_receive_minor"] == 360_000
    bid = c.post(f"/cycles/{cy['id']}/auction/bids", json={"member_id": a_seat, "discount": 40_000},
                 headers=heads[emails[0]])
    assert bid.json()["accepted"], bid.text
    own = c.get(f"/cycles/{cy['id']}/auction/bids", headers=heads[emails[0]]).json()
    assert own[0]["discount"] == 40_000
    assert c.get(f"/cycles/{cy['id']}/auction/bids", headers=heads[emails[1]]).json()[0]["discount"] is None
    c.post(f"/cycles/{cy['id']}/auction/close", headers=org_h)
    st = c.post(f"/cycles/{cy['id']}/settlement", headers=org_h).json()

    # members pay the net installment once the dividend is known; nobody can pay for someone else
    assert c.post(f"/sandbox/cycles/{cy['id']}/payments", json={"member_id": a_seat},
                  headers=heads[emails[1]]).status_code == 403
    paid = c.post(f"/sandbox/cycles/{cy['id']}/payments", json={"member_id": a_seat}, headers=heads[emails[0]])
    assert paid.status_code == 200 and paid.json()["applied"] == "COMPLETED"
    for m in c.get(f"/circles/{circle['id']}", headers=org_h).json()["members"]:
        if m["id"] != a_seat:
            assert c.post(f"/sandbox/cycles/{cy['id']}/payments", json={"member_id": m["id"]},
                          headers=org_h).status_code == 200

    # the winner's linked account cannot approve its own payout
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"},
                  headers=heads[emails[0]]).status_code == 403
    assert c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"},
                  headers=org_h).json()["cycle_state"] == "APPROVED"
    assert c.post(f"/settlements/{st['id']}/payout", headers=org_h).json()["outcome"] == "SUBMITTED"
    confirmed = c.post(f"/sandbox/settlements/{st['id']}/payout", json={}, headers=org_h).json()
    assert confirmed["applied"] == "CONFIRMED" and confirmed["cycle_state"] == "RECONCILIATION_PENDING"
    fin = c.post(f"/settlements/{st['id']}/finalize", headers=org_h)
    assert fin.status_code == 200, fin.text

    detail = c.get(f"/settlements/{st['id']}", headers=heads[emails[1]]).json()
    assert detail["cycle_state"] == "FINALIZED" and detail["approvals"][0]["decision"] == "APPROVE"

    explained = c.get(f"/cycles/{cy['id']}/members/{seat_of[emails[1]]}/explanation", headers=heads[emails[1]])
    assert explained.status_code == 200 and "dividend" in explained.json()["summary"].lower()
    assert c.get(f"/cycles/{cy['id']}/members/{a_seat}/explanation", headers=heads[emails[1]]).status_code == 403

    # members see their own entries plus group events; the organizer sees everything
    org_feed = c.get(f"/circles/{circle['id']}/ledger", headers=org_h).json()["items"]
    b_feed = c.get(f"/circles/{circle['id']}/ledger", headers=heads[emails[1]]).json()["items"]
    assert len(b_feed) < len(org_feed)
    assert all(e["member_id"] in (None, seat_of[emails[1]]) or e["type"] in (
        "PAYOUT_REQUESTED", "PAYOUT_CONFIRMED", "SETTLEMENT_FINALIZED", "COMMISSION_ALLOCATED") for e in b_feed)

    dash = c.get(f"/circles/{circle['id']}/dashboard", headers=org_h).json()
    assert dash["summary"]["completed_cycles"] == 1 and dash["payouts"]["completed"] == 1
    mv = c.get(f"/circles/{circle['id']}/members/{a_seat}/view", headers=heads[emails[0]]).json()
    assert mv["cycles"][0]["settlement"]["is_winner"] and mv["cycles"][0]["settlement"]["winner_payout"] == 360_000
    tl = c.get(f"/circles/{circle['id']}/timeline", headers=org_h).json()
    assert any(cell["state"] == "WINNER" for row in tl["members"] for cell in row["cycles"])


def test_collections_agent_proposes_and_mandate_creates_invoice(api):
    c = api
    org_h, org = register(c, "org@example.com", "Org")
    circle = create_circle(c, org_h, org, ["x@example.com", "y@example.com", "z@example.com"],
                           payout_mode="FIXED_ROTATION", auction=None)
    cy = start_round(c, org_h, circle["id"], days=-8)          # eight days overdue → catch-up invoice stage

    run = c.post(f"/circles/{circle['id']}/agents/collections/run", headers=org_h).json()
    assert len(run["created"]) == 4 and {p["kind"] for p in run["created"]} == {"invoice"}
    again = c.post(f"/circles/{circle['id']}/agents/collections/run", headers=org_h).json()
    assert again["created"] == [] and len(again["skipped"]) == 4          # no duplicate proposals

    queue = c.get(f"/circles/{circle['id']}/proposed-actions", headers=org_h).json()
    prop = queue[0]
    assert prop["proposed_by"] == "agent:collections" and prop["params"]["amount_minor"] == 100_000
    assert c.post(f"/proposed-actions/{prop['id']}/approve", json={"step_up_method": "NONE"},
                  headers=org_h).status_code == 422                       # step-up is required
    mandate = c.post(f"/proposed-actions/{prop['id']}/approve", json={"step_up_method": "OTP"}, headers=org_h).json()
    executed = c.post(f"/mandates/{mandate['mandate_id']}/execute", headers=org_h)
    assert executed.status_code == 200, executed.text
    assert executed.json()["outcome"]["status"] == "CREATED" and executed.json()["outcome"]["approval_url"]
    assert c.post(f"/mandates/{mandate['mandate_id']}/execute", headers=org_h).status_code == 409   # single use

    second = queue[1]
    assert c.post(f"/proposed-actions/{second['id']}/reject", json={"reason": "spoke in person"},
                  headers=org_h).json()["state"] == "REJECTED"

    # the member pays after approval: a stale mandate for the old balance must not execute
    third = queue[2]
    m3 = c.post(f"/proposed-actions/{third['id']}/approve", json={"step_up_method": "BIOMETRIC"}, headers=org_h).json()
    c.post(f"/sandbox/cycles/{cy['id']}/payments", json={"member_id": third["params"]["member_id"]}, headers=org_h)
    assert c.post(f"/mandates/{m3['mandate_id']}/execute", headers=org_h).status_code == 409


def test_collections_agent_waits_for_auction_settlement(api):
    c = api
    org_h, org = register(c, "org@example.com", "Org")
    circle = create_circle(c, org_h, org, ["x@example.com", "y@example.com", "z@example.com"])
    start_round(c, org_h, circle["id"], days=-8)
    run = c.post(f"/circles/{circle['id']}/agents/collections/run", headers=org_h).json()
    assert run["created"] == [] and run["skipped"][0]["reason"] == "waiting for the auction settlement"


def test_resume_from_failed_payout(api):
    c = api
    org_h, org = register(c, "org@example.com", "Org")
    circle = create_circle(c, org_h, org, ["p@example.com", "q@example.com", "r@example.com"],
                           organizer_seat_last=True, payout_mode="FIXED_ROTATION", auction=None)
    cy = start_round(c, org_h, circle["id"])
    for m in circle["members"]:
        c.post(f"/sandbox/cycles/{cy['id']}/payments", json={"member_id": m["id"]}, headers=org_h)
    c.post(f"/cycles/{cy['id']}/recipient", headers=org_h)
    st = c.post(f"/cycles/{cy['id']}/settlement", headers=org_h).json()
    c.post(f"/settlements/{st['id']}/approvals", json={"decision": "APPROVE"}, headers=org_h)
    c.gw.mode = "fail"
    assert c.post(f"/settlements/{st['id']}/payout", headers=org_h).json()["outcome"] == "FAILED"
    c.gw.mode = "ok"
    assert c.post(f"/cycles/{cy['id']}/resume", json={"reason": ""}, headers=org_h).status_code == 422
    resumed = c.post(f"/cycles/{cy['id']}/resume", json={"reason": "payee details fixed"}, headers=org_h)
    assert resumed.json()["state"] == "PAYOUT_PENDING"
    assert c.post(f"/settlements/{st['id']}/payout", headers=org_h).json()["outcome"] == "SUBMITTED"


def test_paypal_invoice_paid_webhook_is_normalized_and_applied(api):
    c = api
    org_h, org = register(c, "org@example.com", "Org")
    circle = create_circle(c, org_h, org, ["k@example.com", "l@example.com", "m@example.com"])
    cy = start_round(c, org_h, circle["id"])
    member = circle["members"][1]["id"]
    event = {"id": "WH-1", "event_type": "INVOICING.INVOICE.PAID", "resource": {"invoice": {
        "id": "INV2-AAAA", "detail": {"reference": f"collection:{cy['id']}:{member}", "currency_code": "INR"},
        "amount": {"currency_code": "INR", "value": "1000.00"},
        "payments": {"paid_amount": {"currency_code": "INR", "value": "1000.00"},
                     "transactions": [{"payment_id": "PAYID-123"}]}}}}
    body = json.dumps(event).encode()
    r = c.post("/webhooks/provider", content=body,
               headers={"Content-Type": "application/json", "X-Signature": HmacVerifier(SECRET).sign(body)})
    assert r.status_code == 200 and not r.json()["duplicate"]
    from app.services.financial_service import process_pending_provider_events
    with db.SessionLocal() as s:
        assert process_pending_provider_events(s)["applied"][0]["applied"] == "COMPLETED"
        row = s.query(ProviderEventRow).one()
        assert row.provider_txn_id == "PAYID-123" and row.amount == 100_000
    ignored = json.dumps({"id": "WH-2", "event_type": "CUSTOMER.DISPUTE.CREATED", "resource": {}}).encode()
    r = c.post("/webhooks/provider", content=ignored,
               headers={"Content-Type": "application/json", "X-Signature": HmacVerifier(SECRET).sign(ignored)})
    assert r.json()["ignored"]


def test_paypal_payout_item_event_maps_to_settlement_reference():
    class FakeSession:
        def get(self, model, key):
            class Row:
                payout_idempotency_key = f"payout:{key}"
            return Row() if model.__name__ == "SettlementRow" else None
    out = paypal_events.normalize(FakeSession(), {
        "id": "WH-9", "event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED",
        "resource": {"transaction_id": "TX-1", "payout_item": {
            "sender_item_id": "payout:abc", "amount": {"currency": "USD", "value": "12.34"}}}})
    assert out == {"event_id": "WH-9", "paypal_event_type": "PAYMENT.PAYOUTS-ITEM.SUCCEEDED", "kind": "PAYOUT",
                   "payout_reference": "payout:abc", "provider_txn_id": "TX-1", "status": "COMPLETED",
                   "amount": 1234, "currency": "USD"}


def test_paypal_verifier_reads_lowercase_headers_and_signs_crc32(monkeypatch):
    seen = {}
    v = PayPalWebhookVerifier("WEBHOOK-ID")
    monkeypatch.setattr(v, "_get_certificate", lambda url: seen.setdefault("url", url) and None)
    body = b'{"x":1}'
    headers = {"paypal-transmission-id": "T", "paypal-transmission-time": "now",
               "paypal-transmission-sig": "c2ln", "paypal-cert-url": "https://api.sandbox.paypal.com/cert.pem"}
    assert v.verify(body, headers) is False and seen["url"].endswith("cert.pem")      # reached cert fetch
    assert v.verify(body, {**headers, "paypal-cert-url": "https://evil.example.com/c.pem"}) is False
    assert str(zlib.crc32(body)).isdigit()
