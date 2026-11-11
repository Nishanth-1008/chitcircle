"""Read models for timeline, dashboard and member view, with a Redis cache keyed by circle version.

The cache key includes a version derived from the circle's ledger sequence, its latest state transition,
bid count and member security/won flags, so any write produces a new key and readers never see stale data
for longer than it takes to compute it. Redis is best-effort; without it every read is computed directly.
"""
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import hashlib
import json

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import config
from ..models import BidRow, Circle, Cycle, LedgerEventRow, Member, Obligation, SettlementRow, StateTransition

_CACHE_TTL_SECONDS = 300

PAYOUT_IN_FLIGHT = ("APPROVED", "PAYOUT_PENDING", "PAYOUT_SUBMITTED", "PAYOUT_CONFIRMED", "RECONCILIATION_PENDING")
AUCTION_STATES = ("AUCTION_OPEN", "AUCTION_CLOSED")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return _utc(dt).isoformat() if dt else None


def _cache_get(key: str) -> Optional[Dict[str, Any]]:
    try:
        raw = config.get_redis().get(key)
        if raw:
            return json.loads(raw)
    except Exception:  # noqa: BLE001 - cache is best-effort
        pass
    return None


def _cache_set(key: str, data: Dict[str, Any]) -> None:
    try:
        config.get_redis().setex(key, _CACHE_TTL_SECONDS, json.dumps(data, default=str))
    except Exception:  # noqa: BLE001 - cache is best-effort
        pass


def _etag(data: Dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()


def circle_version(session: Session, circle: Circle) -> str:
    cycle_ids = select(Cycle.id).where(Cycle.circle_id == circle.id)
    last_transition = session.scalar(select(func.max(StateTransition.id)).where(StateTransition.cycle_id.in_(cycle_ids)))
    bids = session.scalar(select(func.count(BidRow.id)).where(BidRow.cycle_id.in_(cycle_ids)))
    members = session.execute(select(Member.id, Member.security_status, Member.has_won, Member.user_id)
                              .where(Member.circle_id == circle.id).order_by(Member.id)).all()
    mhash = hashlib.sha1(repr(members).encode()).hexdigest()[:12]
    return f"{circle.ledger_seq or 0}.{last_transition or 0}.{bids or 0}.{mhash}"


def _cached(session: Session, circle: Circle, name: str, build) -> Dict[str, Any]:
    key = f"read:{name}:{circle.id}:{circle_version(session, circle)}"
    cached = _cache_get(key)
    if cached is not None:
        return cached
    data = build()
    _cache_set(key, data)
    return data


def _outstanding(ob: Obligation) -> int:
    return max(0, ob.gross_due + ob.adjustments - ob.dividend_credit - ob.confirmed_paid)


def _settlement_winner(settlement: Optional[SettlementRow]) -> Optional[str]:
    if settlement is None or not settlement.data:
        return None
    return settlement.data.get("settlement", {}).get("winner_member_id")


def get_circle_timeline(session: Session, circle_id: str) -> Dict[str, Any]:
    """Member x cycle grid: each cell is PAID, LATE, PENDING, WINNER, AUCTION or NOT_OPEN."""
    circle = session.get(Circle, circle_id)
    if not circle:
        return {"error": "Circle not found"}

    def build() -> Dict[str, Any]:
        members = session.scalars(select(Member).where(Member.circle_id == circle_id).order_by(Member.position)).all()
        cycles = session.scalars(select(Cycle).where(Cycle.circle_id == circle_id).order_by(Cycle.number)).all()
        cycle_ids = [c.id for c in cycles]
        obligations = {(o.cycle_id, o.member_id): o for o in session.scalars(
            select(Obligation).where(Obligation.cycle_id.in_(cycle_ids)))} if cycle_ids else {}
        settlements = {s.cycle_id: s for s in session.scalars(
            select(SettlementRow).where(SettlementRow.cycle_id.in_(cycle_ids)))} if cycle_ids else {}
        now = _now()
        rows = []
        for member in members:
            cells = []
            for cycle in cycles:
                ob = obligations.get((cycle.id, member.id))
                settlement = settlements.get(cycle.id)
                winner = _settlement_winner(settlement) or cycle.winner_member_id
                cell = {"cycle_id": cycle.id, "cycle_number": cycle.number, "due_date": _iso(cycle.due_date),
                        "state": "NOT_OPEN", "amount_due": 0, "amount_paid": 0, "dividend": 0,
                        "is_winner": winner == member.id, "discount": None}
                if ob:
                    cell["amount_due"] = ob.gross_due + ob.adjustments - ob.dividend_credit
                    cell["amount_paid"] = ob.confirmed_paid
                    cell["dividend"] = ob.dividend_credit
                    if _outstanding(ob) <= 0:
                        cell["state"] = "PAID"
                    elif _utc(cycle.due_date) < now:
                        cell["state"] = "LATE"
                    else:
                        cell["state"] = "PENDING"
                if cell["is_winner"]:
                    cell["paid_state"] = cell["state"]
                    cell["state"] = "WINNER"
                    cell["discount"] = cycle.discount
                elif cycle.state in AUCTION_STATES and cell["state"] == "PENDING":
                    cell["state"] = "AUCTION"
                cells.append(cell)
            rows.append({"member_id": member.id, "member_name": member.name, "position": member.position,
                         "has_won": member.has_won, "security_status": member.security_status,
                         "user_id": member.user_id, "cycles": cells})
        summaries = [{"cycle_id": c.id, "cycle_number": c.number, "state": c.state, "due_date": _iso(c.due_date),
                      "winner_member_id": c.winner_member_id, "discount": c.discount,
                      "settlement_status": settlements[c.id].status if c.id in settlements else None}
                     for c in cycles]
        return {"circle_id": circle_id, "circle_name": circle.name, "members": rows, "cycles": summaries}

    return _cached(session, circle, "circle_timeline", build)


def get_circle_dashboard(session: Session, circle_id: str) -> Dict[str, Any]:
    """Organizer summary: collections, auction, payouts, members at risk and recent activity."""
    circle = session.get(Circle, circle_id)
    if not circle:
        return {"error": "Circle not found"}

    def build() -> Dict[str, Any]:
        members = session.scalars(select(Member).where(Member.circle_id == circle_id)).all()
        cycles = session.scalars(select(Cycle).where(Cycle.circle_id == circle_id).order_by(Cycle.number)).all()
        current = cycles[-1] if cycles else None
        now = _now()
        names = {m.id: m.name for m in members}

        collections = {"collected": 0, "outstanding": 0, "late": 0, "total_members": 0,
                       "amount_collected": 0, "amount_outstanding": 0}
        late_members = []
        if current:
            for ob in session.scalars(select(Obligation).where(Obligation.cycle_id == current.id)):
                out = _outstanding(ob)
                collections["total_members"] += 1
                collections["amount_collected"] += ob.confirmed_paid
                collections["amount_outstanding"] += out
                if out <= 0:
                    collections["collected"] += 1
                    continue
                collections["outstanding"] += 1
                is_late = _utc(current.due_date) < now
                if is_late:
                    collections["late"] += 1
                late_members.append({"member_id": ob.member_id, "member_name": names.get(ob.member_id),
                                     "outstanding": out, "due_date": _iso(current.due_date), "is_late": is_late})

        recent = session.scalars(select(LedgerEventRow).where(LedgerEventRow.circle_id == circle_id)
                                 .order_by(LedgerEventRow.timestamp.desc()).limit(10)).all()
        return {
            "circle_id": circle_id,
            "circle_name": circle.name,
            "summary": {
                "total_members": len(members),
                "won_members": sum(1 for m in members if m.has_won),
                "remaining_members": sum(1 for m in members if not m.has_won),
                "total_cycles": len(cycles),
                "completed_cycles": sum(1 for c in cycles if c.state == "FINALIZED"),
                "current_cycle_id": current.id if current else None,
                "current_cycle_number": current.number if current else 0,
                "current_cycle_state": current.state if current else None,
                "current_cycle_due_date": _iso(current.due_date) if current else None,
            },
            "collections": collections,
            "auctions": {"completed": sum(1 for c in cycles if c.discount is not None and c.state == "FINALIZED"),
                         "pending": sum(1 for c in cycles if c.state in AUCTION_STATES),
                         "current_state": current.state if current else None},
            "payouts": {"completed": sum(1 for c in cycles if c.state == "FINALIZED"),
                        "pending": sum(1 for c in cycles if c.state in PAYOUT_IN_FLIGHT),
                        "failed": sum(1 for c in cycles if c.state == "FAILED")},
            "risk": {"late_members_count": sum(1 for m in late_members if m["is_late"]),
                     "late_members": late_members},
            "security": {"pending": sum(1 for m in members if m.security_status == "PENDING"),
                         "verified": sum(1 for m in members if m.security_status == "VERIFIED")},
            "recent_activity": [{"event_id": e.id, "event_type": e.event_type, "amount": e.amount,
                                 "currency": e.currency, "timestamp": _iso(e.timestamp), "member_id": e.member_id,
                                 "member_name": names.get(e.member_id), "cycle_id": e.cycle_id} for e in recent],
        }

    return _cached(session, circle, "circle_dashboard", build)


def get_member_view(session: Session, circle_id: str, member_id: str) -> Dict[str, Any]:
    """A member's private view: obligations, bids and settlement share per round."""
    member = session.get(Member, member_id)
    circle = session.get(Circle, circle_id)
    if not member or not circle or member.circle_id != circle_id:
        return {"error": "Member not found in circle"}

    def build() -> Dict[str, Any]:
        cycles = session.scalars(select(Cycle).where(Cycle.circle_id == circle_id).order_by(Cycle.number)).all()
        out = []
        for cycle in cycles:
            ob = session.scalar(select(Obligation).where(Obligation.cycle_id == cycle.id,
                                                         Obligation.member_id == member_id))
            settlement = session.scalar(select(SettlementRow).where(SettlementRow.cycle_id == cycle.id))
            bids = session.scalars(select(BidRow).where(BidRow.cycle_id == cycle.id, BidRow.member_id == member_id)
                                   .order_by(BidRow.submitted_at)).all()
            item = {"cycle_id": cycle.id, "cycle_number": cycle.number, "state": cycle.state,
                    "due_date": _iso(cycle.due_date), "obligation": None, "bids": [], "settlement": None}
            if ob:
                item["obligation"] = {"gross_due": ob.gross_due, "dividend_credit": ob.dividend_credit,
                                      "adjustments": ob.adjustments, "confirmed_paid": ob.confirmed_paid,
                                      "net_payable": ob.gross_due + ob.adjustments - ob.dividend_credit,
                                      "outstanding": _outstanding(ob)}
            item["bids"] = [{"bid_id": b.id, "discount": b.discount, "accepted": b.accepted, "reasons": b.reasons,
                             "submitted_at": _iso(b.submitted_at)} for b in bids]
            if settlement and settlement.data:
                s = settlement.data.get("settlement", {})
                is_winner = s.get("winner_member_id") == member_id
                item["settlement"] = {
                    "id": settlement.id, "status": settlement.status, "is_winner": is_winner,
                    "winner_payout": (s.get("winner_payout") or {}).get("minor") if is_winner else None,
                    "my_dividend": (s.get("dividends", {}).get(member_id) or {}).get("minor", 0),
                    "my_net_contribution": (s.get("net_contributions", {}).get(member_id) or {}).get("minor"),
                    "dividend_pool": (s.get("dividend_pool") or {}).get("minor", 0),
                    "currency": s.get("currency"),
                }
            out.append(item)
        return {"member_id": member.id, "member_name": member.name, "position": member.position,
                "has_won": member.has_won, "security_status": member.security_status, "cycles": out}

    return _cached(session, circle, f"member_view:{member_id}", build)
