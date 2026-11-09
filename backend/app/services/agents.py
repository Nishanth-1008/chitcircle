"""Assistive agents (docs/10-ai-agents.md): they read state, explain engine numbers and propose actions.

Rules before AI: every amount here comes from the engine or stored obligations/settlements, the escalation
schedule is deterministic, and wording is template-based. Agents only *propose*; a human approves with
step-up and execution goes through the single-use mandate path in `financial_service.execute_mandate`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from fractions import Fraction
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_engine.auction import AuctionState, Bid, validate_bid
from financial_engine.errors import FinancialEngineError
from financial_engine.money import Money
from financial_engine.rules import AUCTION_MODES, PayoutMethod
from financial_engine.settlement import calculate_settlement
from financial_engine.states import CycleState as S

from ..errors import Conflict, Forbidden, NotFound, Unprocessable
from ..models import BidRow, Cycle, LedgerEventRow, Member, Obligation, ProposedActionRow, SettlementRow
from . import accounts as A
from .financial_service import (_circle, _cycle, _dividend_eligible, _members, _mo, _require_organizer, _rules,
                                _standings, _stored, as_utc, create_proposal)

COLLECTION_STATES = {S.COLLECTIONS_IN_PROGRESS, S.AUCTION_OPEN, S.AUCTION_CLOSED, S.SETTLEMENT_CALCULATED,
                     S.AWAITING_APPROVAL, S.APPROVED, S.ON_HOLD}
REMIND_BEFORE_DUE_DAYS = 3
INVOICE_AFTER_DAYS = 7
ALERT_AFTER_DAYS = 10


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _fmt(minor: int, currency: str) -> str:
    return Money(minor, currency).format()


def _pct(part: int, whole: int) -> str:
    if whole <= 0:
        return "0%"
    q = Fraction(part * 100, whole)
    return f"{float(round(q, 1)):.1f}%"


# ---------------------------------------------------------------- collections agent
def _stage(days_overdue: int) -> Optional[tuple[str, str]]:
    """Deterministic escalation: (kind, stage). None when no action is due yet."""
    if days_overdue < -REMIND_BEFORE_DUE_DAYS:
        return None
    if days_overdue < 0:
        return "reminder", "UPCOMING"
    if days_overdue < 3:
        return "reminder", "FRIENDLY"
    if days_overdue < INVOICE_AFTER_DAYS:
        return "reminder", "FOLLOW_UP"
    return "invoice", "CATCH_UP_INVOICE" if days_overdue < ALERT_AFTER_DAYS else "ORGANIZER_ALERT"


def _message(stage: str, name: str, amount: str, due: str, cycle_number: int, circle: str) -> str:
    first = name.split()[0] if name else "there"
    return {
        "UPCOMING": f"Hi {first}, a quick heads-up: your {circle} contribution of {amount} for round "
                    f"{cycle_number} is due on {due}.",
        "FRIENDLY": f"Hi {first}, your {circle} contribution of {amount} for round {cycle_number} was due on "
                    f"{due}. Whenever you can, please complete it. Thank you!",
        "FOLLOW_UP": f"Hi {first}, following up on round {cycle_number} of {circle}: {amount} (due {due}) is "
                     f"still open. Please pay soon so the round can settle on time.",
        "CATCH_UP_INVOICE": f"Hi {first}, here is a catch-up invoice for {amount} for round {cycle_number} of "
                            f"{circle} (due {due}).",
        "ORGANIZER_ALERT": f"Hi {first}, round {cycle_number} of {circle} is still waiting on {amount} (due {due}). "
                           f"Here is a catch-up invoice; please reach out to the organizer if you need help.",
    }[stage]


def run_collections_agent(session: Session, circle_id: str, actor_id: str, now: Optional[datetime] = None) -> dict:
    circle = _circle(session, circle_id)
    _require_organizer(circle, actor_id)
    now = now or _now()
    cycles = [c for c in session.scalars(select(Cycle).where(Cycle.circle_id == circle_id))
              if S(c.state) in COLLECTION_STATES or (S(c.state) == S.DISPUTED)]
    open_props = list(session.scalars(select(ProposedActionRow).where(
        ProposedActionRow.circle_id == circle_id, ProposedActionRow.state.in_(["PROPOSED", "APPROVED"]))))
    members = {m.id: m for m in _members(session, circle_id)}
    created, skipped, scanned = [], [], 0
    for cycle in cycles:
        rules = _rules(session, circle_id, cycle.ruleset_version)
        settled = session.scalar(select(SettlementRow.id).where(SettlementRow.cycle_id == cycle.id)) is not None
        if rules.payout_mode in AUCTION_MODES and not settled:
            # the installment is only final once the dividend is known; asking earlier would overcharge
            skipped.append({"cycle_id": cycle.id, "reason": "waiting for the auction settlement"})
            continue
        for ob in session.scalars(select(Obligation).where(Obligation.cycle_id == cycle.id)):
            scanned += 1
            outstanding = _mo(ob, rules.currency).outstanding
            if outstanding <= 0:
                continue
            due = as_utc(ob.due_date)
            days_overdue = (now - due).days if now >= due else -((due - now).days + 1)
            step = _stage(days_overdue)
            if step is None:
                continue
            kind, stage = step
            dupe = next((p for p in open_props if p.params.get("cycle_id") == cycle.id
                         and p.params.get("member_id") == ob.member_id and p.kind == kind), None)
            if dupe is not None:
                skipped.append({"member_id": ob.member_id, "reason": "an open proposal already exists"})
                continue
            member = members.get(ob.member_id)
            name = member.name if member else "member"
            amount_txt, due_txt = _fmt(outstanding, rules.currency), due.strftime("%d %b %Y")
            message = _message(stage, name, amount_txt, due_txt, cycle.number, circle.name)
            when = "not yet due" if days_overdue < 0 else f"{days_overdue} day(s) past due"
            rationale = (f"{name} owes {amount_txt} for round {cycle.number} ({when}; grace period "
                         f"{rules.grace_period_days} day(s)). Escalation step: {stage.replace('_', ' ').lower()}.")
            if stage == "ORGANIZER_ALERT":
                rationale += " Normal reminders have not resolved this; consider contacting the member directly."
            params = {"kind": kind, "member_id": ob.member_id, "member_name": name, "amount_minor": outstanding,
                      "currency": rules.currency, "cycle_id": cycle.id, "cycle_number": cycle.number,
                      "due_date": due.isoformat(), "days_overdue": days_overdue, "stage": stage, "message": message}
            res = create_proposal(session, circle_id, "agent:collections", kind, params, rationale, 60 * 24 * 3)
            created.append({"proposal_id": res["proposal_id"], "kind": kind, "member_id": ob.member_id,
                            "stage": stage, "amount_minor": outstanding})
    return {"scanned": scanned, "created": created, "skipped": skipped}


# ---------------------------------------------------------------- explainer
def explain_installment(session: Session, cycle_id: str, member_id: str, actor_id: str,
                        actor_role: str = "member") -> dict:
    cycle = _cycle(session, cycle_id)
    circle = _circle(session, cycle.circle_id)
    seat = session.get(Member, member_id)
    if seat is None or seat.circle_id != circle.id:
        raise NotFound("member not found in this circle")
    if actor_id != circle.organizer_id and not A.acts_for(seat, actor_id) and actor_role != "approver":
        raise Forbidden("members can only see the explanation of their own installment")
    rules = _rules(session, circle.id, cycle.ruleset_version)
    cur = rules.currency
    ob = session.scalar(select(Obligation).where(Obligation.cycle_id == cycle.id, Obligation.member_id == member_id))
    if ob is None:
        raise Conflict("contributions for this round have not been opened yet")
    row = session.scalar(select(SettlementRow).where(SettlementRow.cycle_id == cycle.id))
    n = rules.member_count
    lines = [{"label": "Your share of the pot", "amount_minor": ob.gross_due,
              "note": f"Chit value {_fmt(rules.total_chit_value, cur)} ÷ {n} members"}]
    summary = [f"Round {cycle.number}: your share of the {_fmt(rules.total_chit_value, cur)} pot is "
               f"{_fmt(ob.gross_due, cur)} ({n} equal shares)."]
    is_winner = False
    if row is not None:
        s, _ = _stored(row)
        is_winner = s.winner_member_id == member_id
        recipients = sum(1 for d in s.dividends.values() if d.minor > 0)
        if s.dividend_pool.minor > 0:
            lines.append({"label": "Dividend credit", "amount_minor": -ob.dividend_credit,
                          "note": f"Pool {_fmt(s.dividend_pool.minor, cur)} = discount {_fmt(s.discount.minor, cur)} "
                                  f"− commission {_fmt(s.commission.minor, cur)}, shared by {recipients} members"})
            if ob.dividend_credit:
                summary.append(f"The winning discount of {_fmt(s.discount.minor, cur)} minus the organizer's "
                               f"commission of {_fmt(s.commission.minor, cur)} left a dividend pool of "
                               f"{_fmt(s.dividend_pool.minor, cur)}, split across {recipients} members, so "
                               f"{_fmt(ob.dividend_credit, cur)} is credited to you.")
            else:
                summary.append("You did not receive a dividend this round (members in arrears past the grace "
                               "period are not eligible under this circle's rules).")
        if s.rounding_remainder.minor:
            summary.append(f"{_fmt(s.rounding_remainder.minor, cur)} left over from the equal split goes to "
                           f"{(s.remainder_destination or 'the configured destination').lower().replace('_', ' ')}.")
        if is_winner:
            summary.append(f"You received this round's pot: {_fmt(s.winner_payout.minor, cur)}.")
    else:
        summary.append("The settlement has not been calculated yet, so no dividend has been applied.")
    if ob.adjustments:
        lines.append({"label": "Adjustments", "amount_minor": ob.adjustments, "note": "Recorded corrections"})
    net = ob.gross_due + ob.adjustments - ob.dividend_credit
    lines.append({"label": "Net installment", "amount_minor": net, "note": "What you owe this round"})
    lines.append({"label": "Confirmed paid", "amount_minor": ob.confirmed_paid, "note": "Provider-confirmed only"})
    outstanding = _mo(ob, cur).outstanding
    lines.append({"label": "Still due", "amount_minor": outstanding, "note": ""})
    summary.append(f"Your net installment is {_fmt(net, cur)}; {_fmt(ob.confirmed_paid, cur)} has been confirmed "
                   f"by the payment provider" + (f", leaving {_fmt(outstanding, cur)} due." if outstanding else
                                                  ", so you are fully paid for this round."))
    sources = [e.id for e in session.scalars(select(LedgerEventRow).where(
        LedgerEventRow.cycle_id == cycle.id, LedgerEventRow.member_id == member_id)
        .order_by(LedgerEventRow.timestamp))]
    return {"member_id": member_id, "cycle_id": cycle.id, "currency": cur, "is_winner": is_winner,
            "lines": lines, "summary": " ".join(summary), "source_event_ids": sources}


# ---------------------------------------------------------------- bid advisor
def bid_preview(session: Session, cycle_id: str, member_id: str, discount_minor: int, actor_id: str) -> dict:
    cycle = _cycle(session, cycle_id)
    circle = _circle(session, cycle.circle_id)
    seat = session.get(Member, member_id)
    if seat is None or seat.circle_id != circle.id:
        raise NotFound("member not found in this circle")
    if actor_id != circle.organizer_id and not A.acts_for(seat, actor_id):
        raise Forbidden("members can only preview their own bid")
    rules = _rules(session, circle.id, cycle.ruleset_version)
    if rules.payout_mode not in AUCTION_MODES or rules.auction is None:
        raise Conflict("this circle does not use auctions")
    if isinstance(discount_minor, bool) or not isinstance(discount_minor, int):
        raise Unprocessable("discount must be an integer number of minor units")
    cur, now = rules.currency, _now()
    standings = _standings(session, cycle, rules)
    accepted = [Bid(b.id, b.member_id, Money(b.discount, cur), as_utc(b.submitted_at))
                for b in session.scalars(select(BidRow).where(BidRow.cycle_id == cycle.id, BidRow.accepted.is_(True)))]
    state = AuctionState(S(cycle.state) == S.AUCTION_OPEN, tuple(accepted))
    reasons = [r.value for r in validate_bid(rules, state, Bid("preview", member_id, Money(discount_minor, cur), now),
                                             standings.get(member_id), now)]
    out = {"member_id": member_id, "currency": cur, "discount_minor": discount_minor, "reasons": reasons,
           "valid": not reasons, "chit_value_minor": rules.total_chit_value,
           "cap_minor": rules.discount_cap_minor(), "min_discount_minor": rules.auction.min_discount,
           "increment_minor": rules.auction.increment, "discount_rate": _pct(discount_minor, rules.total_chit_value),
           "preview": None}
    if discount_minor > 0 and "DISCOUNT_ABOVE_CAP" not in reasons:
        prior = frozenset(m.id for m in _members(session, circle.id) if m.has_won)
        try:
            s = calculate_settlement(rules, cycle.id, [m.id for m in _members(session, circle.id)], member_id,
                                     PayoutMethod(rules.payout_mode), Money(discount_minor, cur),
                                     _dividend_eligible(rules, standings, now), prior)
            out["preview"] = {"you_receive_minor": s.winner_payout.minor, "commission_minor": s.commission.minor,
                              "dividend_pool_minor": s.dividend_pool.minor,
                              "your_dividend_minor": s.dividends[member_id].minor,
                              "your_net_contribution_minor": s.net_contributions[member_id].minor}
        except FinancialEngineError as exc:
            out["reasons"].append(type(exc).__name__)
            out["valid"] = False
    history = []
    for c in session.scalars(select(Cycle).where(Cycle.circle_id == circle.id, Cycle.discount.is_not(None),
                                                 Cycle.id != cycle.id).order_by(Cycle.number)):
        history.append({"cycle_number": c.number, "discount_minor": c.discount,
                        "discount_rate": _pct(c.discount, rules.total_chit_value)})
    out["history"] = history
    out["note"] = ("Past winning discounts are historical context, not a prediction of what will win."
                   if history else "No earlier auctions in this circle to compare with yet.")
    return out
