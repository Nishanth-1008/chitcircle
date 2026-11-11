"""Sandbox tools: simulate provider confirmations locally, where PayPal webhooks cannot reach.

The simulated callback goes through the same two-phase path as a real one (persist the raw event, then
apply it under the cycle lock), so the ledger, obligations and reconciliation behave exactly as they would
with a provider event. Rows are recorded with provider "sandbox" and signature_ok=False so they can never
be mistaken for verified provider evidence. Disabled in production.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import config
from ..errors import Conflict, Forbidden, NotFound, ServiceError, Unprocessable
from ..models import Member, Obligation
from . import accounts as A
from .financial_service import (_apply_provider_row, _circle, _cycle, _ingest_provider_event, _mo, _rules,
                                _set_provider_state, _settlement, _stored)
from financial_engine.states import CycleState as S


def _require_enabled() -> None:
    if not config.sandbox_tools_enabled():
        raise Forbidden("sandbox tools are disabled in this environment")


def _ingest_and_apply(session: Session, payload: dict) -> dict:
    ingested = _ingest_provider_event(session, payload, json.dumps(payload), False, provider="sandbox")
    if ingested["duplicate"]:
        return ingested
    try:
        return {"duplicate": False, "sandbox": True, **_apply_provider_row(session, ingested["id"])}
    except ServiceError as exc:
        session.rollback()
        _set_provider_state(session, ingested["id"],
                            "REJECTED" if isinstance(exc, Unprocessable) else "PARKED", f"{exc.code}: {exc.detail}")
        raise


def simulate_payment(session: Session, cycle_id: str, actor_id: str, member_id: str,
                     amount: int | None = None, status: str = "COMPLETED") -> dict:
    _require_enabled()
    if status not in ("COMPLETED", "FAILED"):
        raise Unprocessable("status must be COMPLETED or FAILED")
    cycle = _cycle(session, cycle_id)
    circle = _circle(session, cycle.circle_id)
    seat = session.get(Member, member_id)
    if seat is None or seat.circle_id != circle.id:
        raise NotFound("member not found in this circle")
    if actor_id != circle.organizer_id and not A.acts_for(seat, actor_id):
        raise Forbidden("only the member or the organizer can record a sandbox payment")
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    ob = session.scalar(select(Obligation).where(Obligation.cycle_id == cycle.id, Obligation.member_id == member_id))
    if ob is None:
        raise Conflict("this round has no contribution due for that member yet")
    outstanding = _mo(ob, rules.currency).outstanding
    amount = outstanding if amount is None else amount
    if amount <= 0:
        raise Unprocessable("nothing is outstanding for this member")
    txn = f"SBX-PAY-{uuid.uuid4().hex[:12].upper()}"
    return _ingest_and_apply(session, {
        "event_id": f"sandbox:{txn}", "provider_txn_id": txn, "kind": "PAYMENT", "status": status,
        "amount": amount, "currency": rules.currency, "cycle_id": cycle.id, "member_id": member_id,
        "sandbox": True})


def simulate_payout(session: Session, settlement_id: str, actor_id: str, status: str = "COMPLETED") -> dict:
    _require_enabled()
    if status not in ("COMPLETED", "FAILED"):
        raise Unprocessable("status must be COMPLETED or FAILED")
    row = _settlement(session, settlement_id)
    cycle = _cycle(session, row.cycle_id)
    circle = _circle(session, cycle.circle_id)
    if actor_id != circle.organizer_id:
        raise Forbidden("only the organizer can record a sandbox payout confirmation")
    if S(cycle.state) not in (S.PAYOUT_PENDING, S.PAYOUT_SUBMITTED):
        raise Conflict("no payout is in flight for this settlement")
    s, _ = _stored(row)
    txn = f"SBX-PO-{uuid.uuid4().hex[:12].upper()}"
    return _ingest_and_apply(session, {
        "event_id": f"sandbox:{txn}", "provider_txn_id": txn, "kind": "PAYOUT", "status": status,
        "amount": s.winner_payout.minor, "currency": s.winner_payout.currency,
        "payout_reference": row.payout_idempotency_key, "sandbox": True})
