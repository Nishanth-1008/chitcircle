"""Read paths for the web client: my circles, a circle's rounds, and a circle-wide activity feed.

Everything here is read-only and reports server-held numbers; no money is calculated.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from financial_engine.obligations import MemberObligation

from ..models import (AgentMandate, Circle, Cycle, LedgerEventRow, Member, Obligation, ProposedActionRow,
                      RulesetRow, SettlementRow)
from . import accounts as A
from .financial_service import _active_ruleset_row, _circle, _cycle, as_utc

# Events every member may see in the group view (status of the pot, not other members' payments).
GROUP_EVENT_TYPES = {"PAYOUT_REQUESTED", "PAYOUT_CONFIRMED", "SETTLEMENT_FINALIZED", "COMMISSION_ALLOCATED",
                     "DISPUTE_OPENED", "DISPUTE_RESOLVED"}


def _outstanding(o: Obligation) -> int:
    return MemberObligation(o.member_id, o.cycle_id, "INR", o.gross_due, as_utc(o.due_date), o.dividend_credit,
                            o.adjustments, o.confirmed_paid).outstanding


def _cycle_summary(session: Session, c: Cycle, seat: Optional[Member]) -> dict:
    obs = list(session.scalars(select(Obligation).where(Obligation.cycle_id == c.id)))
    settlement = session.scalar(select(SettlementRow).where(SettlementRow.cycle_id == c.id))
    mine = next((o for o in obs if seat and o.member_id == seat.id), None)
    return {
        "id": c.id, "number": c.number, "state": c.state, "prior_state": c.prior_state,
        "due_date": as_utc(c.due_date).isoformat(), "ruleset_version": c.ruleset_version,
        "payout_method": c.payout_method, "winner_member_id": c.winner_member_id, "discount": c.discount,
        "settlement_id": settlement.id if settlement else None,
        "settlement_status": settlement.status if settlement else None,
        "obligations_total": len(obs),
        "obligations_settled": sum(1 for o in obs if _outstanding(o) == 0),
        "outstanding_total": sum(_outstanding(o) for o in obs),
        "my_outstanding": _outstanding(mine) if mine else None,
        "my_net_payable": (mine.gross_due + mine.adjustments - mine.dividend_credit) if mine else None,
    }


def list_my_circles(session: Session, actor_id: str) -> list:
    seat_circles = select(Member.circle_id).where(or_(Member.user_id == actor_id, Member.id == actor_id))
    circles = list(session.scalars(select(Circle).where(
        or_(Circle.organizer_id == actor_id, Circle.id.in_(seat_circles))).order_by(Circle.created_at.desc())))
    out = []
    for c in circles:
        rules = _active_ruleset_row(session, c.id).data
        members = list(session.scalars(select(Member).where(Member.circle_id == c.id)))
        seat = next((m for m in members if actor_id in (m.id, m.user_id)), None)
        latest = session.scalar(select(Cycle).where(Cycle.circle_id == c.id).order_by(Cycle.number.desc()).limit(1))
        pending = 0
        if c.organizer_id == actor_id:
            pending = len(list(session.scalars(select(ProposedActionRow.id).where(
                ProposedActionRow.circle_id == c.id, ProposedActionRow.state == "PROPOSED"))))
            pending += len(list(session.scalars(select(AgentMandate.id).where(
                AgentMandate.circle_id == c.id, AgentMandate.state == "MANDATE_ISSUED"))))
        out.append({
            "id": c.id, "name": c.name, "organizer_id": c.organizer_id,
            "my_role": "organizer" if c.organizer_id == actor_id else "member",
            "my_member_id": seat.id if seat else None,
            "currency": rules.get("currency"), "total_chit_value": rules.get("total_chit_value"),
            "member_count": len(members), "won_count": sum(1 for m in members if m.has_won),
            "payout_mode": rules.get("payout_mode"),
            "pending_actions": pending,
            "current_cycle": _cycle_summary(session, latest, seat) if latest else None,
        })
    return out


def list_cycles(session: Session, circle_id: str, actor_id: str, actor_role: str = "member") -> list:
    circle = _circle(session, circle_id)
    A.require_circle_access(session, circle, actor_id, actor_role)
    seat = A.seat_for(session, circle_id, actor_id)
    cycles = session.scalars(select(Cycle).where(Cycle.circle_id == circle_id).order_by(Cycle.number.desc()))
    return [_cycle_summary(session, c, seat) for c in cycles]


def _ledger_item(e: LedgerEventRow, cycle_numbers: dict) -> dict:
    return {"id": e.id, "type": e.event_type, "member_id": e.member_id, "cycle_id": e.cycle_id,
            "cycle_number": cycle_numbers.get(e.cycle_id), "amount": e.amount, "currency": e.currency,
            "timestamp": as_utc(e.timestamp).isoformat(), "actor": e.actor, "ruleset_version": e.ruleset_version,
            "settlement_id": e.settlement_id, "provider_ref": e.provider_ref, "reverses": e.reverses_event_id,
            "reason": e.reason, "journal": e.journal}


def visible_ledger_filter(session: Session, circle: Circle, actor_id: str, actor_role: str):
    """Organizer (and designated approvers) see everything; a member sees their own entries plus group events."""
    role = A.require_circle_access(session, circle, actor_id, actor_role)
    if role == "organizer" or actor_role == "approver" or actor_id == "system":
        return None
    seat = A.seat_for(session, circle.id, actor_id)
    return or_(LedgerEventRow.member_id == (seat.id if seat else None),
               LedgerEventRow.member_id.is_(None),
               LedgerEventRow.event_type.in_(GROUP_EVENT_TYPES))


def circle_ledger(session: Session, circle_id: str, actor_id: str, actor_role: str = "member",
                  cursor: Optional[str] = None, limit: int = 50, cycle_id: Optional[str] = None,
                  member_id: Optional[str] = None) -> dict:
    """Newest-first, cursor-paginated feed across every round of a circle."""
    circle = _circle(session, circle_id)
    visible = visible_ledger_filter(session, circle, actor_id, actor_role)
    limit = max(1, min(limit or 50, 200))
    q = select(LedgerEventRow).where(LedgerEventRow.circle_id == circle_id)
    if visible is not None:
        q = q.where(visible)
    if cycle_id:
        q = q.where(LedgerEventRow.cycle_id == cycle_id)
    if member_id:
        q = q.where(LedgerEventRow.member_id == member_id)
    if cursor:
        ts_str, id_str = cursor.split("|", 1)
        ts = datetime.fromisoformat(ts_str)
        q = q.where((LedgerEventRow.timestamp < ts) |
                    ((LedgerEventRow.timestamp == ts) & (LedgerEventRow.id < id_str)))
    rows = list(session.scalars(q.order_by(LedgerEventRow.timestamp.desc(), LedgerEventRow.id.desc())
                                .limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    numbers = {c.id: c.number for c in session.scalars(select(Cycle).where(Cycle.circle_id == circle_id))}
    return {"items": [_ledger_item(e, numbers) for e in rows],
            "next_cursor": f"{as_utc(rows[-1].timestamp).isoformat()}|{rows[-1].id}" if rows and has_more else None,
            "has_more": has_more}


def ruleset_versions(session: Session, circle_id: str) -> list:
    return [{"version": r.version, "status": r.status, "fingerprint": r.fingerprint, "reason": r.reason,
             "data": r.data, "created_by": r.created_by}
            for r in session.scalars(select(RulesetRow).where(RulesetRow.circle_id == circle_id)
                                     .order_by(RulesetRow.version))]
