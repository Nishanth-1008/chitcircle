"""Mandate tests (§13, adr/0007): tampered params hash, expired/consumed mandate,
engine amount recompute mismatch, kill switch, recipient self-approval prevention."""

from datetime import datetime, timedelta, timezone

import pytest

from app import db
from app.errors import Conflict, Forbidden
from app.models import AgentMandate, FeatureFlag, Member, ProposedActionRow, SettlementRow
from app.services import financial_service as svc
from app.services.gateway import MockGateway
from .test_api_integration import env as env_fixture, ORG, to_settlement


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _session():
    return db.SessionLocal()


def _winner_payout_minor(session, settlement_id: str) -> int:
    """Read the actual winner payout minor units from the stored settlement."""
    row = session.get(SettlementRow, settlement_id)
    return row.data["settlement"]["winner_payout"]["minor"]


def _create_proposal_and_mandate(s, circle_id, actor_id, member_id, amount_minor,
                                 cycle_id, settlement_id=None, cap_minor=None):
    """Helper: propose → approve → return (proposal_id, mandate_id)."""
    params = {
        "kind": "payout",
        "member_id": member_id,
        "amount_minor": amount_minor,
        "currency": "INR",
        "cycle_id": cycle_id,
    }
    if settlement_id:
        params["settlement_id"] = settlement_id

    result = svc.create_proposal(s, circle_id, actor_id, "payout", params,
                                 "test mandate", 60)
    proposal_id = result["proposal_id"]

    result = svc.approve_proposal(s, proposal_id, actor_id, "BIOMETRIC", None, cap_minor)
    mandate_id = result["mandate_id"]
    s.commit()
    return proposal_id, mandate_id


# ------------------------------------------------------------------ tampered params hash

def test_tampered_params_hash_aborts_before_gateway_call(env_fixture):
    """Changing mandate params after approval must abort execution with no provider call."""
    c = env_fixture
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    member_id = circle["members"][1]["id"]
    with _session() as s:
        _, mandate_id = _create_proposal_and_mandate(
            s, circle["id"], ORG["X-Actor-Id"], member_id, 300_000,
            cy["id"], st["id"])

        # Tamper: replace the params dict with a different amount (not an in-place tweak,
        # so SQLAlchemy's dirty tracking definitely persists it).
        mandate = s.get(AgentMandate, mandate_id)
        mandate.params = {**mandate.params, "amount_minor": 999_999}
        s.commit()

    gw = MockGateway()
    with pytest.raises(Conflict) as exc:
        with _session() as s:
            svc.execute_mandate(s, mandate_id, ORG["X-Actor-Id"], gw)
    assert "tampered" in str(exc.value)
    assert gw.calls == 0  # no provider call was made


# ------------------------------------------------------------------ expired mandate

def test_expired_mandate_cannot_execute(env_fixture):
    """A mandate whose expiry has passed cannot execute."""
    c = env_fixture
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    member_id = circle["members"][1]["id"]
    with _session() as s:
        _, mandate_id = _create_proposal_and_mandate(
            s, circle["id"], ORG["X-Actor-Id"], member_id, 300_000,
            cy["id"], st["id"])
        mandate = s.get(AgentMandate, mandate_id)
        mandate.expires_at = _now() - timedelta(minutes=5)
        s.commit()

    gw = MockGateway()
    with pytest.raises(Conflict) as exc:
        with _session() as s:
            svc.execute_mandate(s, mandate_id, ORG["X-Actor-Id"], gw)
    assert "expired" in str(exc.value).lower()
    assert gw.calls == 0


# ------------------------------------------------------------------ consumed mandate (double execution)

def test_consumed_mandate_cannot_execute_twice(env_fixture):
    """A mandate is single-use: the second execution attempt is rejected."""
    c = env_fixture
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    member_id = circle["members"][1]["id"]
    with _session() as s:
        amount_minor = _winner_payout_minor(s, st["id"])
        _, mandate_id = _create_proposal_and_mandate(
            s, circle["id"], ORG["X-Actor-Id"], member_id, amount_minor,
            cy["id"], st["id"])

    gw = MockGateway()
    # First execution succeeds.
    with _session() as s:
        result = svc.execute_mandate(s, mandate_id, ORG["X-Actor-Id"], gw)
    assert result["outcome"]["status"] == "SUBMITTED"
    assert gw.calls == 1

    # Second execution must fail — mandate is no longer MANDATE_ISSUED.
    with pytest.raises(Conflict) as exc:
        with _session() as s:
            svc.execute_mandate(s, mandate_id, ORG["X-Actor-Id"], gw)
    assert "not executable" in str(exc.value)
    assert gw.calls == 1  # no second provider call


# ------------------------------------------------------------------ kill switch

def test_kill_switch_blocks_execution(env_fixture):
    """AGENT_EXECUTION_ENABLED=false refuses every execution, even for a valid mandate."""
    c = env_fixture
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    member_id = circle["members"][1]["id"]
    with _session() as s:
        amount_minor = _winner_payout_minor(s, st["id"])
        _, mandate_id = _create_proposal_and_mandate(
            s, circle["id"], ORG["X-Actor-Id"], member_id, amount_minor,
            cy["id"], st["id"])
        s.add(FeatureFlag(key="AGENT_EXECUTION_ENABLED", value=False))
        s.commit()

    gw = MockGateway()
    with pytest.raises(Forbidden) as exc:
        with _session() as s:
            svc.execute_mandate(s, mandate_id, ORG["X-Actor-Id"], gw)
    assert "agent execution is disabled" in str(exc.value)
    assert gw.calls == 0


# ------------------------------------------------------------------ engine amount recompute mismatch

def test_amount_recompute_mismatch_aborts(env_fixture):
    """execute_mandate recomputes the payout from the stored settlement and rejects drift."""
    c = env_fixture
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    member_id = circle["members"][1]["id"]
    with _session() as s:
        amount_minor = _winner_payout_minor(s, st["id"])
        _, mandate_id = _create_proposal_and_mandate(
            s, circle["id"], ORG["X-Actor-Id"], member_id, amount_minor + 1,  # wrong amount
            cy["id"], st["id"])

    gw = MockGateway()
    with pytest.raises(Conflict) as exc:
        with _session() as s:
            svc.execute_mandate(s, mandate_id, ORG["X-Actor-Id"], gw)
    assert "recompute" in str(exc.value)
    assert gw.calls == 0


# ------------------------------------------------------------------ recipient self-approval prevention

def test_payout_recipient_cannot_approve_own_payout(env_fixture):
    """Tier 2: the payout recipient may not approve their own payout mandate."""
    c = env_fixture
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    member_id = circle["members"][1]["id"]  # the payout recipient
    with _session() as s:
        result = svc.create_proposal(
            s, circle["id"], ORG["X-Actor-Id"], "payout",
            {"kind": "payout", "member_id": member_id, "amount_minor": 300_000,
             "currency": "INR", "cycle_id": cy["id"], "settlement_id": st["id"]},
            "test payout", 60)
        proposal_id = result["proposal_id"]

        # The recipient tries to approve their own payout.
        with pytest.raises(Forbidden) as exc:
            svc.approve_proposal(s, proposal_id, member_id, "BIOMETRIC", None, 300_000)
    assert "recipient cannot approve their own payout" in str(exc.value)


# ------------------------------------------------------------------ happy path (valid mandate executes)

def test_valid_mandate_executes(env_fixture):
    """A well-formed, unexpired, unused mandate executes through the gateway exactly once."""
    c = env_fixture
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    member_id = circle["members"][1]["id"]
    with _session() as s:
        amount_minor = _winner_payout_minor(s, st["id"])
        _, mandate_id = _create_proposal_and_mandate(
            s, circle["id"], ORG["X-Actor-Id"], member_id, amount_minor,
            cy["id"], st["id"])

    gw = MockGateway()
    with _session() as s:
        result = svc.execute_mandate(s, mandate_id, ORG["X-Actor-Id"], gw)
    assert result["outcome"]["status"] == "SUBMITTED"
    assert gw.calls == 1

    with _session() as s:
        mandate = s.get(AgentMandate, mandate_id)
        assert mandate.state == "EXECUTED"
        assert mandate.executed_by == ORG["X-Actor-Id"]
