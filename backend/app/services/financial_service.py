"""Service layer: coordinates the database and the pure financial engine.

Order of operations: calculate -> validate -> approve -> execute payment -> reconcile -> finalize.
Every public function commits once at the end; any exception leaves nothing written.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from financial_engine import ledger as L
from financial_engine.auction import (AuctionState, Bid, MemberStanding, RejectReason, select_winner,
                                      validate_bid)
from financial_engine.contributions import compute_contributions
from financial_engine.errors import FinancialEngineError
from financial_engine.money import Money
from financial_engine.obligations import (MemberObligation, MemberProfile, SecurityStatus,
                                          payout_hold_reasons)
from financial_engine.payout_modes import (EarlyPayoutRequest, NoEligibleMembersError, eligible_for_lottery,
                                           evaluate_early_payout, rotation_recipient, run_lottery)
from financial_engine.reconciliation import (ProviderTxn, TxnKind, reconcile_payments, reconcile_payout)
from financial_engine.risk import PaymentRecord, assess_risk
from financial_engine.rules import (AUCTION_MODES, NoBidFallback, PayoutMethod, Ruleset)
from financial_engine.settlement import Settlement, calculate_settlement
from financial_engine.states import EXCEPTION_STATES, CycleState as S, ensure_transition
from financial_engine.validation import check_settlement

from .. import config
from . import accounts as A
from ..errors import Conflict, Forbidden, NotFound, ServiceError, Unprocessable
from ..models import (ApprovalRow, AgentMandate, BidRow, Circle, Cycle, FeatureFlag,
                      LedgerEventRow, LotteryRow, Member, Obligation, ProposedActionRow,
                      ProviderEventRow, RulesetRow, SettlementRow, StateTransition, OutboxRow)
from .gateway import PayoutGateway, PayoutStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- helpers
def _circle(session: Session, circle_id: str) -> Circle:
    c = session.get(Circle, circle_id)
    if c is None:
        raise NotFound("circle not found")
    return c


def _cycle(session: Session, cycle_id: str, lock: bool = False) -> Cycle:
    c = session.get(Cycle, cycle_id, with_for_update=lock)
    if c is None:
        raise NotFound("cycle not found")
    return c


def _settlement(session: Session, sid: str, lock: bool = False) -> SettlementRow:
    s = session.get(SettlementRow, sid, with_for_update=lock)
    if s is None:
        raise NotFound("settlement not found")
    return s


def _rules(session: Session, circle_id: str, version: int) -> Ruleset:
    row = session.scalar(select(RulesetRow).where(RulesetRow.circle_id == circle_id, RulesetRow.version == version))
    if row is None:
        raise NotFound("ruleset version not found")
    return Ruleset.from_dict(row.data)


def _members(session: Session, circle_id: str) -> list:
    return list(session.scalars(select(Member).where(Member.circle_id == circle_id).order_by(Member.position)))


def _require_organizer(circle: Circle, actor_id: str) -> None:
    if circle.organizer_id != actor_id:
        raise Forbidden("only the circle organizer may perform this action")


def _mo(o: Obligation, currency: str) -> MemberObligation:
    return MemberObligation(o.member_id, o.cycle_id, currency, o.gross_due, as_utc(o.due_date),
                            o.dividend_credit, o.adjustments, o.confirmed_paid)


def _transition(session: Session, cycle: Cycle, target: S, actor: str, reason: Optional[str] = None) -> None:
    cur = S(cycle.state)
    resume = S(cycle.prior_state) if cycle.prior_state else None
    ensure_transition(cur, target, resume)
    if target in EXCEPTION_STATES and cur not in EXCEPTION_STATES:
        cycle.prior_state = cur.value
    elif target not in EXCEPTION_STATES:
        cycle.prior_state = None
    session.add(StateTransition(cycle_id=cycle.id, from_state=cur.value, to_state=target.value,
                                actor=actor, reason=reason, at=_now()))
    cycle.state = target.value


def _emit(session: Session, *, circle_id: str, event_type: L.EventType, amount: Money, actor: str,
          ruleset_version: int, cycle_id: Optional[str] = None, member_id: Optional[str] = None,
          settlement_id: Optional[str] = None, provider_ref: Optional[str] = None,
          idempotency_key: Optional[str] = None, reverses: Optional[str] = None, reason: Optional[str] = None,
          approval: Optional[dict] = None, journal: Optional[L.Journal] = None) -> LedgerEventRow:
    if journal is not None:
        journal.assert_balanced()
    if idempotency_key:
        existing = session.scalar(select(LedgerEventRow).where(LedgerEventRow.idempotency_key == idempotency_key))
        if existing is not None:
            return existing
    row = LedgerEventRow(
        id=str(uuid.uuid4()), circle_id=circle_id, cycle_id=cycle_id, member_id=member_id,
        event_type=event_type.value, amount=amount.minor, currency=amount.currency, timestamp=_now(),
        actor=actor, ruleset_version=ruleset_version, settlement_id=settlement_id, provider_ref=provider_ref,
        idempotency_key=idempotency_key, reverses_event_id=reverses, reason=reason, approval=approval,
        journal=journal.to_dict() if journal else None)
    session.add(row)
    session.flush()

    # Increment circle ledger_seq for cache versioning/ETags
    circle = session.get(Circle, circle_id)
    if circle:
        circle.ledger_seq = (circle.ledger_seq or 0) + 1

    # Write to outbox for async consumers (projections, notifications, agents)
    outbox_payload = {
        "event_id": row.id,
        "circle_id": circle_id,
        "cycle_id": cycle_id,
        "member_id": member_id,
        "event_type": event_type.value,
        "amount": amount.minor,
        "currency": amount.currency,
        "timestamp": row.timestamp.isoformat(),
        "actor": actor,
        "ruleset_version": ruleset_version,
        "settlement_id": settlement_id,
        "provider_ref": provider_ref,
        "idempotency_key": idempotency_key,
        "reverses_event_id": reverses,
        "reason": reason,
        "approval": approval,
        "journal": journal.to_dict() if journal else None,
    }
    session.add(OutboxRow(
        aggregate_type="ledger_event",
        aggregate_id=row.id,
        event_type=f"ledger.{event_type.value}",
        payload=outbox_payload,
    ))

    return row


def _standings(session: Session, cycle: Cycle, rules: Ruleset) -> dict:
    members = _members(session, cycle.circle_id)
    obs = session.scalars(select(Obligation).join(Cycle, Cycle.id == Obligation.cycle_id)
                          .where(Cycle.circle_id == cycle.circle_id))
    oldest: dict = {}
    for o in obs:
        if _mo(o, rules.currency).outstanding > 0:
            d = as_utc(o.due_date)
            oldest[o.member_id] = min(d, oldest[o.member_id]) if o.member_id in oldest else d
    return {m.id: MemberStanding(m.id, m.position, m.has_won, oldest.get(m.id)) for m in members}


def _view_cycle(c: Cycle) -> dict:
    return {"id": c.id, "circle_id": c.circle_id, "number": c.number, "ruleset_version": c.ruleset_version,
            "state": c.state, "prior_state": c.prior_state, "due_date": as_utc(c.due_date).isoformat(),
            "payout_method": c.payout_method, "winner_member_id": c.winner_member_id, "discount": c.discount}


def _view_settlement(row: SettlementRow) -> dict:
    return {"id": row.id, "cycle_id": row.cycle_id, "status": row.status, "ruleset_version": row.ruleset_version,
            "settlement": row.data["settlement"], "provider_payout_ref": row.provider_payout_ref,
            "payout_reference": row.payout_idempotency_key,
            "payout_requested_at": row.payout_requested_at.isoformat() if row.payout_requested_at else None,
            "finalized_at": row.finalized_at.isoformat() if row.finalized_at else None}


# ---------------------------------------------------------------- circles & rulesets
def create_circle(session: Session, actor_id: str, name: str, ruleset_data: dict, member_specs: list) -> dict:
    cid = str(uuid.uuid4())
    rules = Ruleset.from_dict({**ruleset_data, "circle_id": cid, "version": 1, "status": "ACTIVE"})
    if len(member_specs) != rules.member_count:
        raise Unprocessable("number of members must equal ruleset member_count")
    members = A.build_seats(session, cid, actor_id, member_specs)
    session.add(Circle(id=cid, name=name, organizer_id=actor_id))
    session.add(RulesetRow(circle_id=cid, version=1, data=rules.to_dict(), fingerprint=rules.fingerprint(),
                           status="ACTIVE", reason="initial ruleset", created_by=actor_id))
    for m in members:
        m.id = str(uuid.uuid4())
    session.add_all(members)
    session.commit()
    return {"id": cid, "name": name, "organizer_id": actor_id, "ruleset_version": 1,
            "members": [{"id": m.id, "name": m.name, "position": m.position, "user_id": m.user_id}
                        for m in members]}


def _active_ruleset_row(session: Session, circle_id: str) -> RulesetRow:
    rows = list(session.scalars(select(RulesetRow).where(RulesetRow.circle_id == circle_id)
                                .order_by(RulesetRow.version)))
    active = [r for r in rows if r.status == "ACTIVE"]
    return (active or rows)[-1]


def get_circle(session: Session, circle_id: str, actor_id: Optional[str] = None,
               actor_role: str = "member") -> dict:
    c = _circle(session, circle_id)
    role = A.require_circle_access(session, c, actor_id, actor_role) if actor_id else "organizer"
    versions = list(session.scalars(select(RulesetRow).where(RulesetRow.circle_id == circle_id)
                                    .order_by(RulesetRow.version)))
    active = _active_ruleset_row(session, circle_id)
    mine = A.seat_for(session, circle_id, actor_id) if actor_id else None
    members = []
    for m in _members(session, circle_id):
        view = {"id": m.id, "name": m.name, "position": m.position, "has_won": m.has_won,
                "security_status": m.security_status, "user_id": m.user_id,
                "linked": m.user_id is not None}
        if role == "organizer":
            view["invite_email"] = m.invite_email
        members.append(view)
    return {"id": c.id, "name": c.name, "organizer_id": c.organizer_id,
            "created_at": as_utc(c.created_at).isoformat() if c.created_at else None,
            "my_role": role, "my_member_id": mine.id if mine else None,
            "currency": active.data.get("currency"), "ruleset_version": active.version,
            "ruleset": active.data, "members": members,
            "rulesets": [{"version": r.version, "status": r.status, "fingerprint": r.fingerprint,
                          "reason": r.reason, "created_at": as_utc(r.created_at).isoformat() if r.created_at else None}
                         for r in versions]}


def add_ruleset_version(session: Session, circle_id: str, actor_id: str, ruleset_data: dict, reason: str) -> dict:
    """A rule change creates a NEW version. Existing cycles keep the version they started with."""
    circle = _circle(session, circle_id)
    _require_organizer(circle, actor_id)
    if not reason or not reason.strip():
        raise Unprocessable("a recorded reason is required for a rule change")
    rows = list(session.scalars(select(RulesetRow).where(RulesetRow.circle_id == circle_id)))
    version = max(r.version for r in rows) + 1
    rules = Ruleset.from_dict({**ruleset_data, "circle_id": circle_id, "version": version, "status": "ACTIVE"})
    if rules.member_count != len(_members(session, circle_id)):
        raise Unprocessable("member_count cannot differ from the circle's member count")
    for r in rows:
        if r.status == "ACTIVE":
            r.status = "SUPERSEDED"
    session.add(RulesetRow(circle_id=circle_id, version=version, data=rules.to_dict(),
                           fingerprint=rules.fingerprint(), status="ACTIVE", reason=reason, created_by=actor_id))
    session.commit()
    return {"circle_id": circle_id, "version": version, "fingerprint": rules.fingerprint()}


def set_security_status(session: Session, circle_id: str, member_id: str, actor_id: str, status: str) -> dict:
    circle = _circle(session, circle_id)
    _require_organizer(circle, actor_id)
    m = session.get(Member, member_id)
    if m is None or m.circle_id != circle_id:
        raise NotFound("member not found")
    try:
        m.security_status = SecurityStatus(status).value
    except ValueError:
        raise Unprocessable("invalid security status")
    session.commit()
    return {"member_id": m.id, "security_status": m.security_status}


# ---------------------------------------------------------------- cycles
def create_cycle(session: Session, circle_id: str, actor_id: str, due_date: datetime,
                 ruleset_version: Optional[int] = None) -> dict:
    circle = _circle(session, circle_id)
    _require_organizer(circle, actor_id)
    cycles = list(session.scalars(select(Cycle).where(Cycle.circle_id == circle_id)))
    if any(c.state != S.FINALIZED.value for c in cycles):
        raise Conflict("another cycle in this circle is not finalized yet", "ACTIVE_CYCLE_EXISTS")
    if ruleset_version is None:
        ruleset_version = max(r.version for r in session.scalars(
            select(RulesetRow).where(RulesetRow.circle_id == circle_id, RulesetRow.status == "ACTIVE")))
    rules = _rules(session, circle_id, ruleset_version)
    number = len(cycles) + 1
    if rules.one_win_per_member and number > rules.member_count:
        raise Conflict("all members have already received a payout")
    cycle = Cycle(circle_id=circle_id, number=number, ruleset_version=ruleset_version, due_date=as_utc(due_date))
    session.add(cycle)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise Conflict("cycle number already exists (concurrent request)")
    return _view_cycle(cycle)


def get_cycle(session: Session, cycle_id: str, actor_id: Optional[str] = None, actor_role: str = "member") -> dict:
    c = _cycle(session, cycle_id)
    if actor_id:
        A.require_circle_access(session, _circle(session, c.circle_id), actor_id, actor_role)
    rules = _rules(session, c.circle_id, c.ruleset_version)
    settlement = session.scalar(select(SettlementRow).where(SettlementRow.cycle_id == c.id))
    out = _view_cycle(c)
    out["currency"] = rules.currency
    out["payout_mode"] = rules.payout_mode.value
    out["settlement_id"] = settlement.id if settlement else None
    out["settlement_status"] = settlement.status if settlement else None
    out["obligations"] = [{"member_id": o.member_id, "gross_due": o.gross_due, "dividend_credit": o.dividend_credit,
                           "adjustments": o.adjustments,
                           "net_payable": o.gross_due + o.adjustments - o.dividend_credit,
                           "confirmed_paid": o.confirmed_paid,
                           "outstanding": _mo(o, rules.currency).outstanding}
                          for o in session.scalars(select(Obligation).where(Obligation.cycle_id == cycle_id))]
    out["transitions"] = [{"from": t.from_state, "to": t.to_state, "actor": t.actor, "reason": t.reason,
                           "at": as_utc(t.at).isoformat()}
                          for t in session.scalars(select(StateTransition).where(StateTransition.cycle_id == cycle_id)
                                                   .order_by(StateTransition.id))]
    return out


def open_cycle(session: Session, cycle_id: str, actor_id: str) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    circle = _circle(session, cycle.circle_id)
    _require_organizer(circle, actor_id)
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    members = _members(session, cycle.circle_id)
    plan = compute_contributions(rules, [m.id for m in members], cycle.id)
    _transition(session, cycle, S.OPEN, actor_id)
    for m in members:
        amt = plan.contributions[m.id]
        session.add(Obligation(cycle_id=cycle.id, member_id=m.id, gross_due=amt.minor, due_date=cycle.due_date))
        _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, member_id=m.id,
              event_type=L.EventType.CONTRIBUTION_DUE, amount=amt, actor=actor_id,
              ruleset_version=rules.version, idempotency_key=f"due:{cycle.id}:{m.id}",
              journal=L.contribution_due_journal(m.id, amt))
    for adj in plan.adjustments:
        _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, event_type=L.EventType.ADJUSTMENT_RECORDED,
              amount=adj.amount, actor="system", ruleset_version=rules.version,
              idempotency_key=f"adj:{cycle.id}:{adj.calculation}", reason=adj.reason)
    _transition(session, cycle, S.COLLECTIONS_IN_PROGRESS, actor_id)
    session.commit()
    return _view_cycle(cycle)


# ---------------------------------------------------------------- payments (provider-verified only)
PROVIDER_MAX_ATTEMPTS = 5


def provider_backoff(attempts: int) -> int:
    """Exponential backoff in seconds for a parked provider event: 5, 10, 20, ... capped at an hour."""
    return min(5 * (2 ** max(0, attempts - 1)), 3600)


def provider_event_id(provider: str, p: dict) -> str:
    """Ingress dedupe key.

    PayPal's event id when the payload carries one, otherwise a deterministic key derived from the
    business fields. Deriving it keeps the legacy shape (no event id) idempotent on redelivery while
    still letting a genuine state change on the same transaction through as its own event.
    """
    for k in ("event_id", "webhook_id", "notification_id"):
        if p.get(k):
            return str(p[k])
    return f"{p.get('kind')}:{p.get('provider_txn_id')}:{p.get('status')}"


def _ingest_provider_event(session: Session, p: dict, raw_body: str, signature_ok: bool,
                           provider: str = "paypal") -> dict:
    """Phase A: persist the raw callback. No business logic, no locks, no failures after commit."""
    txn_id = p.get("provider_txn_id")
    if not txn_id:
        raise Unprocessable("provider_txn_id is required")
    try:
        kind = TxnKind(p["kind"])
    except (KeyError, ValueError):
        raise Unprocessable("unknown provider event kind")
    if p.get("amount") is None or p["amount"] < 0:
        raise Unprocessable("amount must not be negative")
    event_id = provider_event_id(provider, p)
    existing = session.scalar(select(ProviderEventRow).where(ProviderEventRow.provider == provider,
                                                             ProviderEventRow.provider_event_id == event_id))
    if existing is not None:
        return {"duplicate": True, "provider_event_id": event_id, "state": existing.state,
                "provider_txn_id": existing.provider_txn_id}
    row = ProviderEventRow(provider=provider, provider_event_id=event_id, provider_txn_id=txn_id,
                           kind=kind.value, status=p.get("status", ""), state="RECEIVED",
                           raw=p, raw_body=raw_body, signature_ok=signature_ok, attempts=0)
    session.add(row)
    session.commit()                                   # durable before anything is applied
    return {"duplicate": False, "provider_event_id": event_id, "id": row.id}


def _set_provider_state(session: Session, row_id: int, state: str, error: Optional[str] = None) -> None:
    row = session.get(ProviderEventRow, row_id, with_for_update=True)
    if row is None:
        return
    row.state, row.last_error = state, error
    if state == "PROCESSED":
        row.processed_at = _now()
    session.commit()


def _apply_provider_row(session: Session, row_id: int) -> dict:
    """Phase B: apply one durable row. Locks the event and the cycle, commits atomically."""
    event_row = session.get(ProviderEventRow, row_id, with_for_update=True)
    if event_row is None:
        raise NotFound("provider event not found")
    if event_row.state == "PROCESSED":
        return {"duplicate": True, "provider_txn_id": event_row.provider_txn_id}
    p = event_row.raw
    if TxnKind(event_row.kind) == TxnKind.PAYOUT:
        result = _apply_payout_event(session, p, event_row)
    else:
        result = _apply_payment_event(session, p, TxnKind(event_row.kind), event_row)
    _set_provider_state(session, row_id, "PROCESSED")
    return result


def receive_provider_event(session: Session, p: dict, raw_body: str, signature_ok: bool) -> dict:
    """Durable receive: persist first, apply second, never lose the event.

    A permanent validation error is recorded as REJECTED and re-raised (4xx to the provider, and the
    worker will not touch it again). Anything else is parked for retry and re-raised, so the caller
    still sees the failure while the row waits for the worker.
    """
    ingested = _ingest_provider_event(session, p, raw_body, signature_ok)
    if ingested["duplicate"]:
        return ingested
    try:
        return {"duplicate": False, **_apply_provider_row(session, ingested["id"])}
    except ServiceError as exc:
        session.rollback()
        _set_provider_state(session, ingested["id"],
                            "REJECTED" if isinstance(exc, Unprocessable) else "PARKED",
                            f"{exc.code}: {exc.detail}")
        raise
    except Exception as exc:                            # noqa: BLE001 - parked, logged, retried by the worker
        session.rollback()
        _set_provider_state(session, ingested["id"], "PARKED", str(exc))
        raise


def apply_provider_event(session: Session, p: dict, raw_body: str = "",
                         signature_ok: bool = True) -> dict:
    """Backwards-compatible entry point: ingest + apply in one call."""
    return receive_provider_event(session, p, raw_body, signature_ok)


def process_pending_provider_events(session: Session, limit: int = 100) -> dict:
    """Worker step: re-apply anything RECEIVED or PARKED below the attempt ceiling.

    This is what makes a crash harmless — the event is already on disk, so the next pass finishes it.
    """
    rows = []
    now = _now()
    pending = (ProviderEventRow.state.in_(["RECEIVED", "PARKED"]) &
               (ProviderEventRow.attempts < PROVIDER_MAX_ATTEMPTS))
    # backoff is per-row (the payload carries no job to update), so the eligible window is computed here
    for row in session.scalars(select(ProviderEventRow).where(pending).order_by(ProviderEventRow.id).limit(limit)):
        if row.attempts:                                # an untried event is eligible immediately
            due_from = row.last_attempt_at or row.received_at
            if as_utc(due_from) + timedelta(seconds=provider_backoff(row.attempts)) > now:
                continue
        rows.append(row)
    applied, failed = [], []
    for row in rows:
        row_id = row.id
        try:
            applied.append({"id": row_id, **_apply_provider_row(session, row_id)})
        except Exception as exc:                        # noqa: BLE001 - a parked row must not stop the pass
            # _apply_provider_row mutated the row in place before failing, so discard it and re-read
            session.rollback()
            fresh = session.get(ProviderEventRow, row_id, with_for_update=True)
            attempts = (fresh.attempts or 0) + 1
            fresh.attempts, fresh.last_attempt_at = attempts, _now()
            state = "DEAD" if attempts >= PROVIDER_MAX_ATTEMPTS else "PARKED"
            _set_provider_state(session, row_id, state, str(exc))
            error_code = getattr(exc, "code", "UNKNOWN_ERROR")
            failed.append({"id": row_id, "attempts": attempts, "state": state, "error": str(exc), "code": error_code})
    return {"scanned": len(rows), "applied": applied, "failed": failed}


def _apply_payment_event(session: Session, p: dict, kind: TxnKind, event_row: ProviderEventRow) -> dict:
    cycle = _cycle(session, p["cycle_id"], lock=True)
    if S(cycle.state) == S.DRAFT:
        raise Conflict("cycle has not been opened")
    ob = session.scalar(select(Obligation).where(Obligation.cycle_id == cycle.id,
                                                 Obligation.member_id == p.get("member_id")))
    if ob is None:
        raise NotFound("no obligation for that member in this cycle")
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    if p["currency"] != rules.currency:
        raise Unprocessable("currency does not match the circle's settlement currency", "CURRENCY_MISMATCH")
    if S(cycle.state) == S.FINALIZED and kind != TxnKind.REFUND:
        raise Conflict("cycle is finalized; only refunds are accepted")
    amt = Money(p["amount"], p["currency"])
    status = p["status"]
    # the ingest row already exists; it is enriched with what phase B resolved
    event_row.cycle_id, event_row.member_id, event_row.status = cycle.id, ob.member_id, status
    event_row.amount, event_row.currency = amt.minor, amt.currency
    common = dict(circle_id=cycle.circle_id, cycle_id=cycle.id, member_id=ob.member_id, amount=amt,
                  actor="provider", ruleset_version=rules.version, provider_ref=p["provider_txn_id"],
                  idempotency_key=f"provider:{p['provider_txn_id']}")
    if status == "COMPLETED" and kind == TxnKind.PAYMENT:
        ob.confirmed_paid += amt.minor
        _emit(session, event_type=L.EventType.PAYMENT_CONFIRMED, journal=L.payment_confirmed_journal(ob.member_id, amt), **common)
    elif status == "COMPLETED" and kind == TxnKind.REFUND:
        if amt.minor > ob.confirmed_paid:
            raise Unprocessable("refund exceeds confirmed payments")
        ob.confirmed_paid -= amt.minor
        _emit(session, event_type=L.EventType.REFUND_CONFIRMED, journal=L.refund_confirmed_journal(ob.member_id, amt), **common)
    elif status == "FAILED" and kind == TxnKind.PAYMENT:
        _emit(session, event_type=L.EventType.PAYMENT_FAILED, **common)
    return {"duplicate": False, "applied": status, "kind": kind.value, "member_id": ob.member_id,
            "confirmed_paid": ob.confirmed_paid}


# ---------------------------------------------------------------- auction & payout-mode selection
def open_auction(session: Session, cycle_id: str, actor_id: str) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    _require_organizer(_circle(session, cycle.circle_id), actor_id)
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    if rules.payout_mode not in AUCTION_MODES:
        raise Conflict("this circle does not use auctions")
    if cycle.winner_member_id:
        raise Conflict("a winner is already selected for this cycle")
    _transition(session, cycle, S.AUCTION_OPEN, actor_id)
    session.commit()
    return _view_cycle(cycle)


def submit_bid(session: Session, cycle_id: str, actor_id: str, member_id: str, discount_minor: int) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    circle = _circle(session, cycle.circle_id)
    seat = session.get(Member, member_id)
    if seat is not None and seat.circle_id != circle.id:
        seat = None                       # the engine rejects it as NOT_ELIGIBLE_MEMBER, traceably
    if actor_id != circle.organizer_id and not A.acts_for(seat, actor_id) and actor_id != member_id:
        raise Forbidden("a bid may only be placed by the member or the organizer")
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    now = _now()
    standing = _standings(session, cycle, rules).get(member_id)
    accepted = [Bid(b.id, b.member_id, Money(b.discount, rules.currency), as_utc(b.submitted_at))
                for b in session.scalars(select(BidRow).where(BidRow.cycle_id == cycle.id, BidRow.accepted.is_(True)))]
    state = AuctionState(S(cycle.state) == S.AUCTION_OPEN, tuple(accepted))
    bid_id = str(uuid.uuid4())
    reasons = validate_bid(rules, state, Bid(bid_id, member_id, Money(discount_minor, rules.currency), now),
                           standing, now)
    session.add(BidRow(id=bid_id, cycle_id=cycle.id, member_id=member_id, discount=discount_minor, submitted_at=now,
                       accepted=not reasons, reasons=[r.value for r in reasons]))
    session.commit()                      # rejections are traceable too (no financial effect)
    return {"bid_id": bid_id, "accepted": not reasons, "reasons": [r.value for r in reasons]}


def list_bids(session: Session, cycle_id: str, actor_id: str) -> list:
    cycle = _cycle(session, cycle_id)
    circle = _circle(session, cycle.circle_id)
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    sealed_hidden = (rules.payout_mode == PayoutMethod.SEALED_BID_AUCTION
                     and S(cycle.state) in (S.COLLECTIONS_IN_PROGRESS, S.AUCTION_OPEN))
    seat = A.seat_for(session, circle.id, actor_id)
    own_ids = {actor_id} | ({seat.id} if seat else set())
    rows = session.scalars(select(BidRow).where(BidRow.cycle_id == cycle_id).order_by(BidRow.submitted_at))
    out = []
    for b in rows:
        own = b.member_id in own_ids
        if sealed_hidden and not own and actor_id != "system":
            out.append({"bid_id": b.id, "member_id": b.member_id, "accepted": b.accepted, "discount": None,
                        "sealed": True, "submitted_at": as_utc(b.submitted_at).isoformat()})
        else:
            out.append({"bid_id": b.id, "member_id": b.member_id, "discount": b.discount, "accepted": b.accepted,
                        "reasons": b.reasons, "submitted_at": as_utc(b.submitted_at).isoformat()})
    return out


def close_auction(session: Session, cycle_id: str, actor_id: str) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    _require_organizer(_circle(session, cycle.circle_id), actor_id)
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    standings = _standings(session, cycle, rules)
    bids = [Bid(b.id, b.member_id, Money(b.discount, rules.currency), as_utc(b.submitted_at))
            for b in session.scalars(select(BidRow).where(BidRow.cycle_id == cycle.id, BidRow.accepted.is_(True)))]
    cycle.tie_seed = secrets.token_hex(16)
    outcome = select_winner(rules, bids, standings, seed=cycle.tie_seed)
    _transition(session, cycle, S.AUCTION_CLOSED, actor_id, "auction closed; bids revealed")
    result = {"status": outcome.status, "trace": list(outcome.trace)}
    if outcome.status == "WON":
        cycle.winner_member_id, cycle.discount = outcome.winner_member_id, outcome.discount.minor
        cycle.payout_method = rules.payout_mode.value
        result.update(winner_member_id=outcome.winner_member_id, discount=outcome.discount.minor,
                      tie_break_applied=outcome.tie_break_applied)
    else:
        fb = outcome.fallback
        if fb == NoBidFallback.HOLD:
            _transition(session, cycle, S.ON_HOLD, actor_id, "no bids; ruleset fallback is HOLD")
            result["fallback"] = "HOLD"
        else:
            winner, method, extra = _fallback_recipient(session, cycle, rules, standings, fb, actor_id)
            cycle.winner_member_id, cycle.payout_method, cycle.discount = winner, method.value, None
            result.update(fallback=fb.value, winner_member_id=winner, **extra)
    session.commit()
    return {**result, "cycle": _view_cycle(cycle)}


def _fallback_recipient(session, cycle, rules, standings, fb, actor_id):
    if fb == NoBidFallback.FIXED_ROTATION:
        order = [m.id for m in _members(session, cycle.circle_id)]
        won = frozenset(m for m, s in standings.items() if s.has_won)
        return rotation_recipient(order, cycle.number, won, rules.one_win_per_member), PayoutMethod.FIXED_ROTATION, {}
    return _draw_lottery(session, cycle, rules, standings)


def _draw_lottery(session, cycle, rules, standings):
    if session.scalar(select(LotteryRow).where(LotteryRow.cycle_id == cycle.id)):
        raise Conflict("a draw was already recorded for this cycle; reruns are not permitted", "LOTTERY_ALREADY_DRAWN")
    eligible = eligible_for_lottery(rules, standings, _now())
    rec = run_lottery(cycle.id, rules, eligible, secrets.token_hex(32))
    session.add(LotteryRow(cycle_id=cycle.id, record=rec.to_dict()))
    return rec.winner_member_id, PayoutMethod.LOTTERY, {"lottery": {
        "seed_commitment": rec.seed_commitment, "eligible_member_ids": list(rec.eligible_member_ids)}}


def select_recipient(session: Session, cycle_id: str, actor_id: str) -> dict:
    """Fixed-rotation or lottery recipient selection (no auction)."""
    cycle = _cycle(session, cycle_id, lock=True)
    _require_organizer(_circle(session, cycle.circle_id), actor_id)
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    if S(cycle.state) != S.COLLECTIONS_IN_PROGRESS:
        raise Conflict("recipient can only be selected while collections are in progress")
    if cycle.winner_member_id:
        raise Conflict("recipient already selected for this cycle")
    standings = _standings(session, cycle, rules)
    if rules.payout_mode == PayoutMethod.FIXED_ROTATION:
        order = [m.id for m in _members(session, cycle.circle_id)]
        won = frozenset(m for m, s in standings.items() if s.has_won)
        winner, method, extra = rotation_recipient(order, cycle.number, won, rules.one_win_per_member), PayoutMethod.FIXED_ROTATION, {}
    elif rules.payout_mode == PayoutMethod.LOTTERY:
        try:
            winner, method, extra = _draw_lottery(session, cycle, rules, standings)
        except NoEligibleMembersError:
            _transition(session, cycle, S.ON_HOLD, actor_id, "lottery has no eligible members")
            session.commit()
            return {"status": "ON_HOLD", "cycle": _view_cycle(cycle)}
    else:
        raise Conflict("this circle uses auctions; close the auction instead")
    cycle.winner_member_id, cycle.payout_method = winner, method.value
    session.commit()
    return {"winner_member_id": winner, "payout_method": method.value, **extra}


def preview_settlement_for(session, cycle, rules, eligible=None) -> Settlement:
    members = [m.id for m in _members(session, cycle.circle_id)]
    prior = frozenset(m.id for m in _members(session, cycle.circle_id) if m.has_won)
    method = PayoutMethod(cycle.payout_method)
    discount = Money(cycle.discount, rules.currency) if cycle.discount else None
    return calculate_settlement(rules, cycle.id, members, cycle.winner_member_id, method, discount, eligible, prior)


def early_payout(session: Session, cycle_id: str, actor_id: str, requester_id: str, discount_minor: int,
                 consenting_ids: list) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    circle = _circle(session, cycle.circle_id)
    if actor_id not in (requester_id, circle.organizer_id):
        raise Forbidden("only the requesting member or organizer may submit an early payout request")
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    if S(cycle.state) != S.COLLECTIONS_IN_PROGRESS or cycle.winner_member_id:
        raise Conflict("early payout is only possible before a recipient is selected")
    standings = _standings(session, cycle, rules)
    now = _now()
    outcome = evaluate_early_payout(
        rules, EarlyPayoutRequest(requester_id, Money(discount_minor, rules.currency), frozenset(consenting_ids), now),
        [m.id for m in _members(session, cycle.circle_id)], standings, now)
    cycle.winner_member_id, cycle.discount = outcome.winner_member_id, outcome.discount.minor
    cycle.payout_method = PayoutMethod.AGREED_DISCOUNT.value
    preview = preview_settlement_for(session, cycle, rules, _dividend_eligible(rules, standings, now))
    session.commit()
    return {"cycle": _view_cycle(cycle), "preview": preview.to_dict(),
            "member_receives": preview.winner_payout.to_dict(),
            "member_net_contribution": preview.net_contributions[requester_id].to_dict()}


# ---------------------------------------------------------------- settlement
def _dividend_eligible(rules, standings, now):
    from financial_engine.auction import in_arrears_past_grace
    return [m for m, s in standings.items() if not in_arrears_past_grace(s, rules, now)]


def calculate_cycle_settlement(session: Session, cycle_id: str, actor_id: str) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    _require_organizer(_circle(session, cycle.circle_id), actor_id)
    existing = session.scalar(select(SettlementRow).where(SettlementRow.cycle_id == cycle.id))
    if existing is not None:
        return {**_view_settlement(existing), "already_calculated": True}
    if S(cycle.state) not in (S.COLLECTIONS_IN_PROGRESS, S.AUCTION_CLOSED) or not cycle.winner_member_id:
        raise Conflict("a recipient must be selected before settlement can be calculated")
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    standings = _standings(session, cycle, rules)
    s = preview_settlement_for(session, cycle, rules, _dividend_eligible(rules, standings, _now()))
    row = SettlementRow(cycle_id=cycle.id, circle_id=cycle.circle_id, ruleset_version=rules.version,
                        data={"settlement": s.to_dict(), "ruleset": rules.to_dict()})
    row.id = str(uuid.uuid4())
    row.payout_idempotency_key = f"payout:{row.id}"
    session.add(row)
    obs = {o.member_id: o for o in session.scalars(select(Obligation).where(Obligation.cycle_id == cycle.id))}
    for m in s.member_order:
        obs[m].dividend_credit = s.dividends[m].minor
    for spec in L.settlement_journals(s):
        _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, member_id=spec.member_id,
              event_type=spec.event_type, amount=spec.amount, actor="system", ruleset_version=rules.version,
              settlement_id=row.id, reason=spec.reason, journal=spec.journal,
              idempotency_key=f"settle:{row.id}:{spec.event_type.value}:{spec.member_id or 'circle'}")
    _transition(session, cycle, S.SETTLEMENT_CALCULATED, actor_id)
    _transition(session, cycle, S.AWAITING_APPROVAL, "system")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = session.scalar(select(SettlementRow).where(SettlementRow.cycle_id == cycle_id))
        if existing is None:
            raise
        return {**_view_settlement(existing), "already_calculated": True}
    return {**_view_settlement(row), "already_calculated": False}


def get_settlement(session: Session, settlement_id: str, actor_id: Optional[str] = None,
                   actor_role: str = "member") -> dict:
    row = _settlement(session, settlement_id)
    if actor_id is None:
        return _view_settlement(row)
    cycle = _cycle(session, row.cycle_id)
    circle = _circle(session, cycle.circle_id)
    A.require_circle_access(session, circle, actor_id, actor_role)
    rules = row.data["ruleset"]
    winner = session.get(Member, row.data["settlement"]["winner_member_id"])
    approvals = list(session.scalars(select(ApprovalRow).where(ApprovalRow.settlement_id == row.id)
                                     .order_by(ApprovalRow.id)))
    last = session.scalar(select(StateTransition).where(StateTransition.cycle_id == cycle.id)
                          .order_by(StateTransition.id.desc()).limit(1))
    return {**_view_settlement(row), "circle_id": circle.id, "circle_name": circle.name,
            "organizer_id": circle.organizer_id, "cycle_number": cycle.number, "cycle_state": cycle.state,
            "prior_state": cycle.prior_state, "state_reason": last.reason if last else None,
            "required_approvals": rules.get("required_approvals", 1),
            "require_security": rules.get("require_security", False),
            "require_full_collection_before_payout": rules.get("require_full_collection_before_payout", True),
            "winner_security_status": winner.security_status if winner else None,
            "approvals": [{"approver_id": a.approver_id, "decision": a.decision, "reason": a.reason,
                           "created_at": as_utc(a.created_at).isoformat() if a.created_at else None}
                          for a in approvals]}


def _stored(row: SettlementRow):
    return Settlement.from_dict(row.data["settlement"]), Ruleset.from_dict(row.data["ruleset"])


def approve_settlement(session: Session, settlement_id: str, actor_id: str, actor_role: str, decision: str,
                       reason: Optional[str]) -> dict:
    row = _settlement(session, settlement_id, lock=True)
    cycle = _cycle(session, row.cycle_id, lock=True)
    circle = _circle(session, cycle.circle_id)
    if actor_id != circle.organizer_id and actor_role != "approver":
        raise Forbidden("only the organizer or a designated approver may approve")
    s, rules = _stored(row)
    if A.acts_for(session.get(Member, s.winner_member_id), actor_id) or actor_id == s.winner_member_id:
        raise Forbidden("the payout recipient cannot approve their own payout")
    if S(cycle.state) != S.AWAITING_APPROVAL:
        raise Conflict("settlement is not awaiting approval")
    if decision not in ("APPROVE", "REJECT"):
        raise Unprocessable("decision must be APPROVE or REJECT")
    violations = check_settlement(s, rules, frozenset(m.id for m in _members(session, cycle.circle_id) if m.has_won))
    if violations:
        raise Unprocessable("stored settlement fails validation: " + ", ".join(violations))
    session.add(ApprovalRow(settlement_id=row.id, approver_id=actor_id, decision=decision, reason=reason))
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        raise Conflict("this approver has already recorded a decision")
    if decision == "REJECT":
        _transition(session, cycle, S.ON_HOLD, actor_id, f"approval rejected: {reason or ''}")
    else:
        n = len(list(session.scalars(select(ApprovalRow).where(ApprovalRow.settlement_id == row.id,
                                                                ApprovalRow.decision == "APPROVE"))))
        if n >= rules.required_approvals:
            row.status = "APPROVED"
            _transition(session, cycle, S.APPROVED, actor_id, f"{n}/{rules.required_approvals} approvals")
    session.commit()
    return {"settlement_id": row.id, "cycle_state": cycle.state, "decision": decision}


# ---------------------------------------------------------------- payout execution
def _profile(session: Session, member: Member, circle_id: str) -> MemberProfile:
    return MemberProfile(member.id, member.has_won, 0, 0, SecurityStatus(member.security_status), 0)


def execute_payout(session: Session, settlement_id: str, actor_id: str, gateway: PayoutGateway) -> dict:
    row = _settlement(session, settlement_id, lock=True)
    cycle = _cycle(session, row.cycle_id, lock=True)
    circle = _circle(session, cycle.circle_id)
    _require_organizer(circle, actor_id)
    s, rules = _stored(row)
    state = S(cycle.state)
    if state in (S.PAYOUT_SUBMITTED, S.PAYOUT_CONFIRMED, S.RECONCILIATION_PENDING, S.FINALIZED):
        return {"outcome": "ALREADY_REQUESTED", "settlement": _view_settlement(row)}     # never pay twice
    if state == S.APPROVED:
        winner = session.get(Member, s.winner_member_id)
        holds = payout_hold_reasons(_profile(session, winner, cycle.circle_id), rules)
        if holds:
            _transition(session, cycle, S.ON_HOLD, actor_id, "payout held: " + ", ".join(holds))
            session.commit()
            return {"outcome": "HELD", "reasons": holds}
        obs = [_mo(o, rules.currency) for o in session.scalars(select(Obligation).where(Obligation.cycle_id == cycle.id))]
        short = [o.member_id for o in obs if o.outstanding > 0]
        if rules.require_full_collection_before_payout and short:
            raise Conflict("collections are incomplete", "COLLECTIONS_INCOMPLETE", {"members_outstanding": short})
        _transition(session, cycle, S.PAYOUT_PENDING, actor_id)
        row.payout_requested_at = _now()
        _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, member_id=s.winner_member_id,
              event_type=L.EventType.PAYOUT_REQUESTED, amount=s.winner_payout, actor=actor_id,
              ruleset_version=rules.version, settlement_id=row.id,
              idempotency_key=f"payout-request:{row.id}", journal=L.payout_requested_journal(s.winner_payout),
              approval={"approvals": [a.approver_id for a in session.scalars(
                  select(ApprovalRow).where(ApprovalRow.settlement_id == row.id, ApprovalRow.decision == "APPROVE"))]})
        session.commit()                 # persist intent BEFORE calling the provider
    elif state != S.PAYOUT_PENDING:
        raise Conflict(f"settlement cannot be paid out from state {state.value}")
    result = gateway.submit_payout(idempotency_key=row.payout_idempotency_key,
                                   member_id=s.winner_member_id, amount=s.winner_payout,
                                   session=session)
    return _apply_gateway_result(session, row, cycle, result, actor_id)


def _apply_gateway_result(session, row, cycle, result, actor_id) -> dict:
    if result.status == PayoutStatus.SUBMITTED:
        row.provider_payout_ref = result.provider_ref
        if S(cycle.state) == S.PAYOUT_PENDING:
            _transition(session, cycle, S.PAYOUT_SUBMITTED, actor_id, f"provider ref {result.provider_ref}")
        out = {"outcome": "SUBMITTED", "provider_ref": result.provider_ref}
    elif result.status == PayoutStatus.CONFIRMED:
        row.provider_payout_ref = result.provider_ref
        if S(cycle.state) == S.PAYOUT_PENDING:
            _transition(session, cycle, S.PAYOUT_SUBMITTED, actor_id)
        out = {"outcome": "SUBMITTED", "provider_ref": result.provider_ref,
               "note": "awaiting verified confirmation callback"}
    elif result.status == PayoutStatus.FAILED:
        _transition(session, cycle, S.FAILED, actor_id, f"payout failed: {result.detail}")
        out = {"outcome": "FAILED", "detail": result.detail}
    else:   # UNKNOWN: a timeout is neither success nor failure
        out = {"outcome": "UNRESOLVED", "detail": result.detail}
    session.commit()
    return {**out, "cycle_state": cycle.state}


def check_payout(session: Session, settlement_id: str, actor_id: str, gateway: PayoutGateway) -> dict:
    row = _settlement(session, settlement_id, lock=True)
    cycle = _cycle(session, row.cycle_id, lock=True)
    _require_organizer(_circle(session, cycle.circle_id), actor_id)
    if S(cycle.state) not in (S.PAYOUT_PENDING, S.PAYOUT_SUBMITTED):
        raise Conflict("no payout is in flight for this settlement")
    return _apply_gateway_result(session, row, cycle, gateway.lookup_payout(row.payout_idempotency_key), actor_id)


def _apply_payout_event(session: Session, p: dict, event_row: ProviderEventRow) -> dict:
    row = session.scalar(select(SettlementRow).where(SettlementRow.payout_idempotency_key == p.get("payout_reference")))
    if row is None:
        raise NotFound("no settlement matches that payout reference")
    cycle = _cycle(session, row.cycle_id, lock=True)
    s, rules = _stored(row)
    amt = Money(p["amount"], p["currency"])
    matches = amt == s.winner_payout
    # a COMPLETED callback with the wrong amount is stored as MISMATCH: it holds the cycle for human review
    # and is never counted as the confirmed payout
    stored_status = "MISMATCH" if (p["status"] == "COMPLETED" and not matches) else p["status"]
    event_row.cycle_id, event_row.member_id, event_row.settlement_id = cycle.id, s.winner_member_id, row.id
    event_row.status, event_row.amount, event_row.currency = stored_status, amt.minor, amt.currency
    if S(cycle.state) not in (S.PAYOUT_PENDING, S.PAYOUT_SUBMITTED):
        session.flush()
        return {"duplicate": False, "applied": "RECORDED_ONLY", "cycle_state": cycle.state}
    if p["status"] == "FAILED":
        _transition(session, cycle, S.FAILED, "provider", "payout failed per provider callback")
        return {"duplicate": False, "applied": "FAILED", "cycle_state": cycle.state}
    if p["status"] != "COMPLETED":
        return {"duplicate": False, "applied": "PENDING", "cycle_state": cycle.state}
    if not matches:
        _transition(session, cycle, S.ON_HOLD, "provider", "payout amount/currency mismatch with settlement")
        return {"duplicate": False, "applied": "MISMATCH_HELD", "cycle_state": cycle.state}
    if S(cycle.state) == S.PAYOUT_PENDING:
        _transition(session, cycle, S.PAYOUT_SUBMITTED, "provider")
    row.provider_payout_ref = p["provider_txn_id"]
    _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, member_id=s.winner_member_id,
          event_type=L.EventType.PAYOUT_CONFIRMED, amount=amt, actor="provider", ruleset_version=rules.version,
          settlement_id=row.id, provider_ref=p["provider_txn_id"], idempotency_key=f"provider:{p['provider_txn_id']}",
          journal=L.payout_confirmed_journal(amt))
    _transition(session, cycle, S.PAYOUT_CONFIRMED, "provider")
    _transition(session, cycle, S.RECONCILIATION_PENDING, "system")
    return {"duplicate": False, "applied": "CONFIRMED", "cycle_state": cycle.state}


# ---------------------------------------------------------------- reconciliation & finalization
def _reconcile(session: Session, row: SettlementRow, cycle: Cycle, s: Settlement, rules: Ruleset) -> dict:
    cur = rules.currency
    obs = list(session.scalars(select(Obligation).where(Obligation.cycle_id == cycle.id)))
    events = list(session.scalars(select(LedgerEventRow).where(LedgerEventRow.cycle_id == cycle.id)))
    ledger_paid: dict = {}
    for e in events:
        if e.event_type == "PAYMENT_CONFIRMED":
            ledger_paid[e.member_id] = ledger_paid.get(e.member_id, 0) + e.amount
        elif e.event_type == "REFUND_CONFIRMED":
            ledger_paid[e.member_id] = ledger_paid.get(e.member_id, 0) - e.amount
    problems = []
    for o in obs:
        if ledger_paid.get(o.member_id, 0) != o.confirmed_paid:
            problems.append({"code": "LEDGER_OBLIGATION_MISMATCH", "member_id": o.member_id})
    internal = {o.member_id: Money(ledger_paid.get(o.member_id, 0), cur) for o in obs}
    provider = [ProviderTxn(p.provider_txn_id, TxnKind(p.kind), p.status, Money(p.amount, p.currency), p.member_id)
                for p in session.scalars(select(ProviderEventRow).where(ProviderEventRow.cycle_id == cycle.id,
                                                                        ProviderEventRow.state == "PROCESSED"))]
    pay_rep = reconcile_payments(internal, provider, s.net_contributions)
    payout_txn = next((t for t in provider if t.kind == TxnKind.PAYOUT and t.status == "COMPLETED"), None)
    out_rep = reconcile_payout(s.winner_payout, payout_txn)
    pool = 0
    for e in events:
        if e.journal:
            pool += sum(p["credit"] - p["debit"] for p in e.journal["postings"] if p["account"] == L.POOL)
            if not L.Journal.from_dict(e.journal).is_balanced:
                problems.append({"code": "UNBALANCED_JOURNAL", "event_id": e.id})
    if pool != 0:
        problems.append({"code": "POOL_NOT_ZERO", "detail": f"circle pool balance is {pool}"})
    clean = pay_rep.is_clean and out_rep.is_clean and not problems
    return {"is_clean": clean, "payments": pay_rep.to_dict(), "payout": out_rep.to_dict(), "ledger_problems": problems}


def finalize_settlement(session: Session, settlement_id: str, actor_id: str) -> dict:
    row = _settlement(session, settlement_id, lock=True)
    cycle = _cycle(session, row.cycle_id, lock=True)
    circle = _circle(session, cycle.circle_id)
    _require_organizer(circle, actor_id)
    if row.status == "FINALIZED":
        raise Conflict("settlement is already finalized", "ALREADY_FINALIZED")
    if S(cycle.state) != S.RECONCILIATION_PENDING:
        raise Conflict(f"settlement cannot be finalized from state {cycle.state}")
    s, rules = _stored(row)
    failures = []
    prior = frozenset(m.id for m in _members(session, cycle.circle_id) if m.has_won and m.id != s.winner_member_id)
    failures += check_settlement(s, rules, prior)
    approvals = len(list(session.scalars(select(ApprovalRow).where(
        ApprovalRow.settlement_id == row.id, ApprovalRow.decision == "APPROVE"))))
    if approvals < rules.required_approvals:
        failures.append("APPROVALS_MISSING")
    winner = session.get(Member, s.winner_member_id)
    failures += payout_hold_reasons(_profile(session, winner, cycle.circle_id), rules)
    report = _reconcile(session, row, cycle, s, rules)
    if failures or not report["is_clean"]:
        raise Conflict("finalization checks failed; settlement remains pending", "FINALIZATION_BLOCKED",
                       {"failures": failures, "reconciliation": report})
    _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, member_id=s.winner_member_id,
          event_type=L.EventType.SETTLEMENT_FINALIZED, amount=s.winner_payout, actor=actor_id,
          ruleset_version=rules.version, settlement_id=row.id, idempotency_key=f"finalized:{row.id}")
    _transition(session, cycle, S.FINALIZED, actor_id)
    row.status, row.finalized_at = "FINALIZED", _now()
    winner.has_won = True
    session.commit()
    return {"settlement": _view_settlement(row), "reconciliation": report}


def reconciliation_report(session: Session, settlement_id: str) -> dict:
    row = _settlement(session, settlement_id)
    cycle = _cycle(session, row.cycle_id)
    s, rules = _stored(row)
    return _reconcile(session, row, cycle, s, rules)


# ---------------------------------------------------------------- ledger, corrections, disputes
def list_ledger(session: Session, cycle_id: str, cursor: Optional[str] = None, limit: Optional[int] = 50,
                actor_id: Optional[str] = None, actor_role: str = "member") -> dict:
    """Cursor-paginated ledger listing. Never uses OFFSET; pages by (timestamp, id) tuple."""
    q = select(LedgerEventRow).where(LedgerEventRow.cycle_id == cycle_id)
    if actor_id:
        from .queries import visible_ledger_filter
        cycle = _cycle(session, cycle_id)
        visible = visible_ledger_filter(session, _circle(session, cycle.circle_id), actor_id, actor_role)
        if visible is not None:
            q = q.where(visible)
    if cursor:
        ts_str, id_str = cursor.split("|", 1)
        cursor_ts = datetime.fromisoformat(ts_str)
        q = q.where(
            (LedgerEventRow.timestamp > cursor_ts) |
            ((LedgerEventRow.timestamp == cursor_ts) & (LedgerEventRow.id > id_str))
        )
    q = q.order_by(LedgerEventRow.timestamp, LedgerEventRow.id)
    if limit is not None:
        q = q.limit(limit + 1)  # fetch one extra to detect a next page
    rows = list(session.scalars(q))
    has_more = len(rows) > (limit if limit is not None else len(rows))
    if has_more:
        rows = rows[:limit]
    next_cursor = f"{as_utc(rows[-1].timestamp).isoformat()}|{rows[-1].id}" if rows else None
    return {
        "items": [{"id": e.id, "type": e.event_type, "member_id": e.member_id, "amount": e.amount, "currency": e.currency,
                   "timestamp": as_utc(e.timestamp).isoformat(), "actor": e.actor, "ruleset_version": e.ruleset_version,
                   "settlement_id": e.settlement_id, "provider_ref": e.provider_ref, "reverses": e.reverses_event_id,
                   "reason": e.reason, "journal": e.journal} for e in rows],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


def reverse_event(session: Session, event_id: str, actor_id: str, reason: str) -> dict:
    """Corrections are linked reversal events; the original entry is never edited or deleted."""
    orig = session.get(LedgerEventRow, event_id)
    if orig is None:
        raise NotFound("ledger event not found")
    _require_organizer(_circle(session, orig.circle_id), actor_id)
    if not reason or not reason.strip():
        raise Unprocessable("a reason is required for a correction")
    if session.scalar(select(LedgerEventRow).where(LedgerEventRow.reverses_event_id == event_id)):
        raise Conflict("event has already been reversed")
    if orig.event_type in ("SETTLEMENT_FINALIZED", "DISPUTE_OPENED", "DISPUTE_RESOLVED") or orig.reverses_event_id:
        raise Unprocessable("this event type cannot be reversed")
    journal = L.Journal.from_dict(orig.journal).mirrored() if orig.journal else None
    rev = _emit(session, circle_id=orig.circle_id, cycle_id=orig.cycle_id, member_id=orig.member_id,
                event_type=L.EventType.ADJUSTMENT_RECORDED, amount=Money(-orig.amount, orig.currency),
                actor=actor_id, ruleset_version=orig.ruleset_version, settlement_id=orig.settlement_id,
                reverses=orig.id, reason=reason, journal=journal, idempotency_key=f"reversal:{orig.id}")
    # keep derived balances consistent with the ledger
    if orig.cycle_id and orig.member_id and orig.event_type in ("PAYMENT_CONFIRMED", "REFUND_CONFIRMED"):
        ob = session.scalar(select(Obligation).where(Obligation.cycle_id == orig.cycle_id,
                                                     Obligation.member_id == orig.member_id))
        ob.confirmed_paid += -orig.amount if orig.event_type == "PAYMENT_CONFIRMED" else orig.amount
    session.commit()
    return {"reversal_event_id": rev.id, "reverses": orig.id}


def resume_cycle(session: Session, cycle_id: str, actor_id: str, reason: str) -> dict:
    """Leave ON_HOLD/FAILED only by returning to the state recorded when the hold began."""
    cycle = _cycle(session, cycle_id, lock=True)
    _require_organizer(_circle(session, cycle.circle_id), actor_id)
    if S(cycle.state) not in (S.ON_HOLD, S.FAILED) or not cycle.prior_state:
        raise Conflict("cycle is not on hold")
    if not reason or not reason.strip():
        raise Unprocessable("a recorded reason is required to resume")
    _transition(session, cycle, S(cycle.prior_state), actor_id, reason)
    session.commit()
    return _view_cycle(cycle)


def open_dispute(session: Session, cycle_id: str, actor_id: str, reason: str) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    _transition(session, cycle, S.DISPUTED, actor_id, reason)
    _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, event_type=L.EventType.DISPUTE_OPENED,
          amount=Money.zero(rules.currency), actor=actor_id, ruleset_version=rules.version, reason=reason)
    session.commit()
    return _view_cycle(cycle)


def resolve_dispute(session: Session, cycle_id: str, actor_id: str, reason: str) -> dict:
    cycle = _cycle(session, cycle_id, lock=True)
    _require_organizer(_circle(session, cycle.circle_id), actor_id)
    if S(cycle.state) != S.DISPUTED or not cycle.prior_state:
        raise Conflict("cycle is not in dispute")
    rules = _rules(session, cycle.circle_id, cycle.ruleset_version)
    _transition(session, cycle, S(cycle.prior_state), actor_id, reason)
    _emit(session, circle_id=cycle.circle_id, cycle_id=cycle.id, event_type=L.EventType.DISPUTE_RESOLVED,
          amount=Money.zero(rules.currency), actor=actor_id, ruleset_version=rules.version, reason=reason)
    session.commit()
    return _view_cycle(cycle)


# ---------------------------------------------------------------- risk (advisory only)
def member_risk(session: Session, circle_id: str, member_id: str) -> dict:
    circle = _circle(session, circle_id)
    m = session.get(Member, member_id)
    if m is None or m.circle_id != circle_id:
        raise NotFound("member not found")
    version = max(r.version for r in session.scalars(select(RulesetRow).where(RulesetRow.circle_id == circle_id)))
    rules = _rules(session, circle_id, version)
    cycles = {c.id: c for c in session.scalars(select(Cycle).where(Cycle.circle_id == circle_id))}
    obs = sorted(session.scalars(select(Obligation).where(Obligation.member_id == member_id)),
                 key=lambda o: as_utc(o.due_date))
    pays = list(session.scalars(select(LedgerEventRow).where(
        LedgerEventRow.member_id == member_id, LedgerEventRow.event_type == "PAYMENT_CONFIRMED")
        .order_by(LedgerEventRow.timestamp)))
    now, records = _now(), []
    for o in obs:
        need = o.gross_due + o.adjustments - o.dividend_credit
        cum, done_at = 0, None
        for e in pays:
            if e.cycle_id == o.cycle_id:
                cum += e.amount
                if cum >= need:
                    done_at = as_utc(e.timestamp)
                    break
        due = as_utc(o.due_date)
        ref = done_at or now
        records.append(PaymentRecord(max(0, (ref - due).days), settled=done_at is not None))
    finalized = len([c for c in cycles.values() if c.state == "FINALIZED"])
    remaining = (rules.member_count - finalized) if m.has_won else 0
    ra = assess_risk(records, remaining, finalized if m.has_won else 0, SecurityStatus(m.security_status), m.has_won)
    return {"member_id": member_id, "indicator": ra.indicator.value, "points": ra.points, "factors": list(ra.factors),
            "required_security_level": ra.required_security_level, "organizer_alert": ra.organizer_alert,
            "review_recommendation": ra.review_recommendation, "disclaimer": ra.disclaimer}


# ---------------------------------------------------------------- agent mandates (§13, adr/0007)
#
# The agent may only *propose*. A human approves with step-up, which issues a single-use,
# hash-locked mandate. `execute_mandate` takes the id alone, re-reads everything from the DB,
# verifies hash/expiry/unused/proposal state, recomputes the amount with the engine, takes the
# cycle lock, then calls the gateway outside the transaction. Nothing about the action can drift
# after approval.

def _canonical_params(params: dict) -> str:
    """Deterministic JSON serialization for hash-locking mandate parameters."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))


def _params_hash(params: dict) -> str:
    return hashlib.sha256(_canonical_params(params).encode()).hexdigest()


def _feature_flag(session: Session, key: str) -> bool:
    """Resolve a feature flag: DB row wins; absent → env-configured default."""
    row = session.get(FeatureFlag, key)
    if row is not None:
        return bool(row.value)
    default = {"AGENT_PROPOSAL_ENABLED": True, "AGENT_EXECUTION_ENABLED": True}.get(key, False)
    return bool(default)


def _require_proposal_params(params: dict) -> None:
    """Validate that proposal params contain the minimum fields every action needs."""
    required = {"kind", "member_id", "amount_minor", "currency", "cycle_id"}
    missing = required - set(params.keys())
    if missing:
        raise Unprocessable(f"proposal params missing: {', '.join(sorted(missing))}")
    if not isinstance(params["amount_minor"], int) or isinstance(params["amount_minor"], bool):
        raise Unprocessable("amount_minor must be an integer number of minor units")
    if params["amount_minor"] <= 0:
        raise Unprocessable("amount_minor must be positive")


def create_proposal(session: Session, circle_id: str, actor_id: str, kind: str,
                    params: dict, rationale: Optional[str],
                    expires_in_minutes: int = 60) -> dict:
    """Agent proposes an action. Returns the proposal id; nothing can execute yet.

    The agent supplies exact structured parameters. Deterministic code validates them; the
    LLM never supplies execution parameters at execute time.
    """
    if not _feature_flag(session, "AGENT_PROPOSAL_ENABLED"):
        raise Forbidden("agent proposals are disabled by feature flag")
    circle = _circle(session, circle_id)
    if not actor_id.startswith("agent:") and actor_id != "system":
        _require_organizer(circle, actor_id)
    if kind not in MANDATE_KINDS:
        raise Unprocessable(f"kind must be one of: {', '.join(MANDATE_KINDS)}")
    _require_proposal_params(params)
    params["kind"] = kind
    proposal = ProposedActionRow(
        id=str(uuid.uuid4()), circle_id=circle_id, kind=kind, params=params,
        rationale=rationale, state="PROPOSED", proposed_by=actor_id, created_at=_now())
    session.add(proposal)
    session.commit()
    return {"proposal_id": proposal.id, "state": "PROPOSED",
            "expires_at": (_now() + timedelta(minutes=expires_in_minutes)).isoformat()}


def approve_proposal(session: Session, proposal_id: str, actor_id: str,
                     step_up_method: str, step_up_evidence: Optional[dict],
                     cap_minor: Optional[int] = None) -> dict:
    """Human approves a proposal with step-up auth. Issues a single-use, hash-locked mandate.

    The approval screen must show the exact amount and recipient in plain language. The mandate
    locks the params, a hard cap, currency, circle, cycle, recipient, action kind and a short
    expiry. Only an ISSUED mandate can execute, and only once.
    """
    if not _feature_flag(session, "AGENT_PROPOSAL_ENABLED"):
        raise Forbidden("agent proposals are disabled by feature flag")
    proposal = session.get(ProposedActionRow, proposal_id)
    if proposal is None:
        raise NotFound("proposal not found")
    if proposal.state != "PROPOSED":
        raise Conflict(f"proposal is already {proposal.state}")
    params = dict(proposal.params)
    amount_minor = params["amount_minor"]
    cap = cap_minor if cap_minor is not None else amount_minor
    if cap < amount_minor:
        raise Unprocessable("cap must be at least the proposed amount")
    # Tier 2 (§13.4): the payout recipient can never approve their own payout.
    if params.get("kind") == "payout":
        member = session.get(Member, params["member_id"])
        if A.acts_for(member, actor_id):
            raise Forbidden("the payout recipient cannot approve their own payout")
    circle = _circle(session, proposal.circle_id)
    if actor_id != circle.organizer_id:
        raise Forbidden("only the circle organizer may approve a proposed action")
    if step_up_method not in ("BIOMETRIC", "OTP"):
        raise Unprocessable("step-up verification (BIOMETRIC or OTP) is required to approve")
    mandate_id = str(uuid.uuid4())
    idempotency_key = f"mandate:{mandate_id}"
    mandate = AgentMandate(
        id=mandate_id, proposal_id=proposal.id, circle_id=proposal.circle_id,
        kind=proposal.kind, params=params, params_hash=_params_hash(params),
        cap_minor=cap, currency=params["currency"],
        expires_at=_now() + timedelta(minutes=30),   # short expiry per §13.1
        state="MANDATE_ISSUED", issued_by=actor_id,
        step_up={"method": step_up_method, "evidence": step_up_evidence or {}},
        idempotency_key=idempotency_key)
    session.add(mandate)
    proposal.state = "APPROVED"
    proposal.decided_by = actor_id
    proposal.decided_at = _now()
    session.commit()
    return {"mandate_id": mandate.id, "idempotency_key": idempotency_key,
            "expires_at": mandate.expires_at.isoformat(), "state": "MANDATE_ISSUED"}


MANDATE_KINDS = ("payout", "invoice", "reminder")


def execute_mandate(session: Session, mandate_id: str, actor_id: str,
                    gateway: PayoutGateway, collection_gateway=None) -> dict:
    """Execute a mandate. Takes the id alone — the LLM supplies no execution parameters.

    Re-reads params from the DB, verifies hash/expiry/unused/proposal state, recomputes the
    amount with the engine, takes the cycle lock, then calls the gateway outside the transaction
    with idempotency key `mandate:{id}`. Any mismatch aborts with no gateway call.
    """
    if not _feature_flag(session, "AGENT_EXECUTION_ENABLED"):
        raise Forbidden("agent execution is disabled by feature flag")
    mandate = session.get(AgentMandate, mandate_id, with_for_update=True)
    if mandate is None:
        raise NotFound("mandate not found")
    if actor_id != "system":
        _require_organizer(_circle(session, mandate.circle_id), actor_id)
    if mandate.state != "MANDATE_ISSUED":
        raise Conflict(f"mandate is {mandate.state}, not executable")
    if _now() > as_utc(mandate.expires_at):
        mandate.state = "EXPIRED"
        session.commit()
        raise Conflict("mandate has expired")
    # Re-verify the params hash — any tampering aborts before any provider call.
    if mandate.params_hash != _params_hash(mandate.params):
        mandate.state = "FAILED"
        mandate.outcome = {"error": "params_hash_mismatch"}
        session.commit()
        raise Conflict("mandate parameters have been tampered with")
    params = mandate.params
    amount_minor = params["amount_minor"]
    if amount_minor > mandate.cap_minor:
        mandate.state = "FAILED"
        mandate.outcome = {"error": "cap_exceeded"}
        session.commit()
        raise Conflict("proposed amount exceeds mandate cap")
    # Take the cycle lock (fixed lock order: circle → cycle → settlement).
    cycle_id = params.get("cycle_id")
    if cycle_id:
        _cycle(session, cycle_id, lock=True)
    # For payouts, recompute the amount from the stored settlement (engine, never the model).
    settlement_id = params.get("settlement_id")
    if settlement_id and mandate.kind == "payout":
        row = _settlement(session, settlement_id, lock=True)
        s, rules = _stored(row)
        expected = s.winner_payout
        if expected.minor != amount_minor or expected.currency != mandate.currency:
            mandate.state = "FAILED"
            mandate.outcome = {"error": "amount_recompute_mismatch"}
            session.commit()
            raise Conflict("engine recomputed amount does not match mandate params")
    if mandate.kind in ("invoice", "reminder"):
        # Collections actions are bound to the obligation's outstanding balance at execution time.
        ob = session.scalar(select(Obligation).where(Obligation.cycle_id == cycle_id,
                                                     Obligation.member_id == params["member_id"]))
        outstanding = _mo(ob, mandate.currency).outstanding if ob else 0
        if outstanding != amount_minor:
            mandate.state = "FAILED"
            mandate.outcome = {"error": "amount_recompute_mismatch", "outstanding_minor": outstanding}
            session.commit()
            raise Conflict("the member's outstanding balance changed since approval; propose again")
    if mandate.kind not in MANDATE_KINDS:
        raise Unprocessable(f"unsupported mandate kind: {mandate.kind}")
    # Persist intent (single-use consumed) before calling the provider, so a retry cannot
    # double-submit. The provider call itself happens outside the transaction.
    mandate.state = "CONSUMED"
    session.commit()
    try:
        amount = Money(amount_minor, mandate.currency)
        if mandate.kind == "payout":
            result = gateway.submit_payout(
                idempotency_key=mandate.idempotency_key,
                member_id=params["member_id"],
                amount=amount,
                session=session,
            )
            outcome = {"provider_ref": result.provider_ref, "status": result.status.value}
        elif mandate.kind == "invoice":
            cg = collection_gateway or gateway
            cycle = _cycle(session, cycle_id)
            base = config.get_env("APP_BASE_URL", "http://localhost:3000")
            back = f"{base}/app/circles/{cycle.circle_id}/cycles/{cycle.id}"
            result = cg.create_collection(
                idempotency_key=mandate.idempotency_key, member_id=params["member_id"], amount=amount,
                description=f"ChitCircle catch-up contribution, round {cycle.number}",
                return_url=f"{back}?payment=returned", cancel_url=f"{back}?payment=cancelled",
                session=session)
            if result.status == "FAILED":
                raise Conflict(result.detail or "invoice creation failed")
            outcome = {"provider_ref": result.provider_ref, "status": result.status,
                       "approval_url": result.approval_url}
        else:
            outcome = {"status": "SENT", "channel": "in_app",
                       "message": params.get("message") or "Friendly reminder: your contribution is due."}
    except Exception as exc:  # noqa: BLE001 - one failed execution must not poison the mandate
        session.rollback()
        mandate = session.get(AgentMandate, mandate_id)
        mandate.state = "FAILED"
        mandate.outcome = {"error": f"{type(exc).__name__}: {exc}"}
        session.commit()
        raise
    mandate.state = "EXECUTED"
    mandate.executed_at = _now()
    mandate.executed_by = actor_id
    mandate.outcome = outcome
    session.commit()
    return {"outcome": mandate.outcome, "mandate_id": mandate.id}


def revoke_mandate(session: Session, mandate_id: str, actor_id: str, reason: Optional[str]) -> dict:
    """Revoke an unused mandate. Only ISSUED mandates can be revoked."""
    mandate = session.get(AgentMandate, mandate_id, with_for_update=True)
    if mandate is None:
        raise NotFound("mandate not found")
    if mandate.state != "MANDATE_ISSUED":
        raise Conflict(f"mandate is {mandate.state}, cannot revoke")
    mandate.state = "REVOKED"
    mandate.outcome = {"revoked_by": actor_id, "reason": reason or "", "revoked_at": _now().isoformat()}
    session.commit()
    return {"mandate_id": mandate.id, "state": "REVOKED"}


def reject_proposal(session: Session, proposal_id: str, actor_id: str, reason: Optional[str]) -> dict:
    """Dismiss a proposal. No mandate is issued, so nothing can ever execute from it."""
    proposal = session.get(ProposedActionRow, proposal_id)
    if proposal is None:
        raise NotFound("proposal not found")
    _require_organizer(_circle(session, proposal.circle_id), actor_id)
    if proposal.state != "PROPOSED":
        raise Conflict(f"proposal is already {proposal.state}")
    proposal.state = "REJECTED"
    proposal.decided_by, proposal.decided_at = actor_id, _now()
    if reason:
        proposal.rationale = f"{proposal.rationale or ''}\n\nRejected: {reason}".strip()
    session.commit()
    return {"proposal_id": proposal.id, "state": proposal.state}


def list_proposals(session: Session, circle_id: str) -> list:
    """List proposed actions for a circle (agent proposal queue), with the mandate each one issued."""
    _circle(session, circle_id)
    rows = list(session.scalars(select(ProposedActionRow)
                                .where(ProposedActionRow.circle_id == circle_id)
                                .order_by(ProposedActionRow.created_at.desc())))
    mandates = {m.proposal_id: m for m in session.scalars(
        select(AgentMandate).where(AgentMandate.circle_id == circle_id))}
    out = []
    for r in rows:
        m = mandates.get(r.id)
        out.append({"id": r.id, "kind": r.kind, "params": r.params, "rationale": r.rationale,
                    "state": r.state, "proposed_by": r.proposed_by,
                    "decided_by": r.decided_by, "decided_at": r.decided_at.isoformat() if r.decided_at else None,
                    "created_at": as_utc(r.created_at).isoformat(),
                    "mandate": None if m is None else {
                        "id": m.id, "state": m.state, "cap_minor": m.cap_minor,
                        "expires_at": as_utc(m.expires_at).isoformat(), "outcome": m.outcome}})
    return out


def list_mandates(session: Session, circle_id: str) -> list:
    """List mandates for a circle (audit trail)."""
    _circle(session, circle_id)
    rows = list(session.scalars(select(AgentMandate)
                                .where(AgentMandate.circle_id == circle_id)
                                .order_by(AgentMandate.created_at.desc())))
    return [{"id": r.id, "proposal_id": r.proposal_id, "kind": r.kind, "params": r.params,
             "params_hash": r.params_hash, "cap_minor": r.cap_minor, "currency": r.currency,
             "expires_at": as_utc(r.expires_at).isoformat(), "state": r.state, "issued_by": r.issued_by,
             "step_up": r.step_up, "executed_at": as_utc(r.executed_at).isoformat() if r.executed_at else None,
             "executed_by": r.executed_by, "outcome": r.outcome,
             "created_at": as_utc(r.created_at).isoformat()} for r in rows]
