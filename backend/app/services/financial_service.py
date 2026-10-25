"""Service layer: coordinates the database and the pure financial engine.

Order of operations: calculate -> validate -> approve -> execute payment -> reconcile -> finalize.
Every public function commits once at the end; any exception leaves nothing written.
"""
from __future__ import annotations

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

from ..errors import Conflict, Forbidden, NotFound, Unprocessable
from ..models import (ApprovalRow, BidRow, Circle, Cycle, LedgerEventRow, LotteryRow, Member, Obligation,
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
def create_circle(session: Session, actor_id: str, name: str, ruleset_data: dict, member_names: list) -> dict:
    cid = str(uuid.uuid4())
    rules = Ruleset.from_dict({**ruleset_data, "circle_id": cid, "version": 1, "status": "ACTIVE"})
    if len(member_names) != rules.member_count:
        raise Unprocessable("number of members must equal ruleset member_count")
    session.add(Circle(id=cid, name=name, organizer_id=actor_id))
    session.add(RulesetRow(circle_id=cid, version=1, data=rules.to_dict(), fingerprint=rules.fingerprint(),
                           status="ACTIVE", reason="initial ruleset", created_by=actor_id))
    members = [Member(id=str(uuid.uuid4()), circle_id=cid, name=n, position=i + 1) for i, n in enumerate(member_names)]
    session.add_all(members)
    session.commit()
    return {"id": cid, "name": name, "organizer_id": actor_id, "ruleset_version": 1,
            "members": [{"id": m.id, "name": m.name, "position": m.position} for m in members]}


def get_circle(session: Session, circle_id: str) -> dict:
    c = _circle(session, circle_id)
    versions = list(session.scalars(select(RulesetRow).where(RulesetRow.circle_id == circle_id)
                                    .order_by(RulesetRow.version)))
    return {"id": c.id, "name": c.name, "organizer_id": c.organizer_id,
            "members": [{"id": m.id, "name": m.name, "position": m.position, "has_won": m.has_won,
                         "security_status": m.security_status} for m in _members(session, circle_id)],
            "rulesets": [{"version": r.version, "status": r.status, "fingerprint": r.fingerprint,
                          "reason": r.reason} for r in versions]}


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


def get_cycle(session: Session, cycle_id: str) -> dict:
    c = _cycle(session, cycle_id)
    out = _view_cycle(c)
    out["obligations"] = [{"member_id": o.member_id, "gross_due": o.gross_due, "dividend_credit": o.dividend_credit,
                           "net_payable": o.gross_due + o.adjustments - o.dividend_credit,
                           "confirmed_paid": o.confirmed_paid,
                           "outstanding": _mo(o, "INR").outstanding}
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
def apply_provider_event(session: Session, p: dict) -> dict:
    """Handle an already signature-verified provider callback. Duplicates are safely ignored."""
    txn_id = p["provider_txn_id"]
    if session.scalar(select(ProviderEventRow).where(ProviderEventRow.provider_txn_id == txn_id)):
        return {"duplicate": True, "provider_txn_id": txn_id}
    try:
        kind = TxnKind(p["kind"])
    except ValueError:
        raise Unprocessable("unknown provider event kind")
    if p["amount"] < 0:
        raise Unprocessable("amount must not be negative")
    try:
        if kind == TxnKind.PAYOUT:
            result = _apply_payout_event(session, p)
        else:
            result = _apply_payment_event(session, p, kind)
        session.commit()
        return result
    except IntegrityError:
        session.rollback()
        return {"duplicate": True, "provider_txn_id": txn_id}


def _apply_payment_event(session: Session, p: dict, kind: TxnKind) -> dict:
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
    session.add(ProviderEventRow(provider_txn_id=p["provider_txn_id"], kind=kind.value, status=status,
                                 cycle_id=cycle.id, member_id=ob.member_id, amount=amt.minor,
                                 currency=amt.currency, raw=p))
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
    if actor_id not in (member_id, circle.organizer_id):
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
    rows = session.scalars(select(BidRow).where(BidRow.cycle_id == cycle_id).order_by(BidRow.submitted_at))
    out = []
    for b in rows:
        own = b.member_id == actor_id
        if sealed_hidden and not own and actor_id != "system":
            out.append({"bid_id": b.id, "member_id": b.member_id, "accepted": b.accepted, "discount": None,
                        "sealed": True})
        else:
            out.append({"bid_id": b.id, "member_id": b.member_id, "discount": b.discount, "accepted": b.accepted,
                        "reasons": b.reasons})
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


def get_settlement(session: Session, settlement_id: str) -> dict:
    return _view_settlement(_settlement(session, settlement_id))


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
    if actor_id == s.winner_member_id:
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
                                   member_id=s.winner_member_id, amount=s.winner_payout)
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


def _apply_payout_event(session: Session, p: dict) -> dict:
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
    session.add(ProviderEventRow(provider_txn_id=p["provider_txn_id"], kind="PAYOUT", status=stored_status,
                                 cycle_id=cycle.id, member_id=s.winner_member_id, settlement_id=row.id,
                                 amount=amt.minor, currency=amt.currency, raw=p))
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
                for p in session.scalars(select(ProviderEventRow).where(ProviderEventRow.cycle_id == cycle.id))]
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
def list_ledger(session: Session, cycle_id: str) -> list:
    rows = session.scalars(select(LedgerEventRow).where(LedgerEventRow.cycle_id == cycle_id)
                           .order_by(LedgerEventRow.timestamp, LedgerEventRow.id))
    return [{"id": e.id, "type": e.event_type, "member_id": e.member_id, "amount": e.amount, "currency": e.currency,
             "timestamp": as_utc(e.timestamp).isoformat(), "actor": e.actor, "ruleset_version": e.ruleset_version,
             "settlement_id": e.settlement_id, "provider_ref": e.provider_ref, "reverses": e.reverses_event_id,
             "reason": e.reason, "journal": e.journal} for e in rows]


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
    if S(cycle.state) not in (S.ON_HOLD,) or not cycle.prior_state:
        raise Conflict("cycle is not on hold")
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
