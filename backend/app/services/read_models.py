"""Read models for timeline and dashboard - optimized SQL queries."""
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import text, select, func, and_, or_
from sqlalchemy.sql import case

from ..models import Circle, Member, Cycle, Obligation, BidRow, SettlementRow, LedgerEventRow


def get_circle_timeline(session: Session, circle_id: str) -> Dict[str, Any]:
    """
    Get timeline data for a circle: member x cycle grid with cell states.
    Returns data suitable for Bryntum timeline grid.
    """
    # Verify circle exists
    circle = session.get(Circle, circle_id)
    if not circle:
        return {"error": "Circle not found"}

    # Get all members ordered by position
    members = session.execute(
        select(Member).where(Member.circle_id == circle_id).order_by(Member.position)
    ).scalars().all()

    # Get all cycles ordered by number
    cycles = session.execute(
        select(Cycle).where(Cycle.circle_id == circle_id).order_by(Cycle.number)
    ).scalars().all()

    # Build timeline grid
    timeline = []
    for member in members:
        member_data = {
            "member_id": member.id,
            "member_name": member.name,
            "position": member.position,
            "has_won": member.has_won,
            "security_status": member.security_status,
            "cycles": []
        }

        for cycle in cycles:
            # Get obligation for this member in this cycle
            obligation = session.execute(
                select(Obligation).where(
                    Obligation.cycle_id == cycle.id,
                    Obligation.member_id == member.id
                )
            ).scalar_one_or_none()

            # Get settlement for this cycle
            settlement = session.execute(
                select(SettlementRow).where(SettlementRow.cycle_id == cycle.id)
            ).scalar_one_or_none()

            # Determine cell state
            cell_state = "PENDING"
            cell_data = {
                "cycle_id": cycle.id,
                "cycle_number": cycle.number,
                "due_date": cycle.due_date.isoformat() if cycle.due_date else None,
                "state": cell_state,
                "amount_due": 0,
                "amount_paid": 0,
                "dividend": 0,
                "is_winner": False,
                "discount": None,
            }

            if obligation:
                cell_data["amount_due"] = obligation.gross_due + obligation.adjustments - obligation.dividend_credit
                cell_data["amount_paid"] = obligation.confirmed_paid
                cell_data["dividend"] = obligation.dividend_credit

                outstanding = cell_data["amount_due"] - cell_data["amount_paid"]

                if outstanding <= 0:
                    cell_state = "PAID"
                elif cycle.due_date and cycle.due_date < datetime.now(timezone.utc):
                    cell_state = "LATE"
                else:
                    cell_state = "PENDING"

            # Check if this member won this cycle
            if settlement and settlement.data:
                settlement_data = settlement.data
                winner_id = settlement_data.get("settlement", {}).get("winner_member_id")
                if winner_id == member.id:
                    cell_state = "WINNER"
                    cell_data["is_winner"] = True
                    cell_data["discount"] = settlement_data.get("settlement", {}).get("winner_payout", {}).get("discount")

            # Check if auction happened for this cycle
            if cycle.state in ("AUCTION_OPEN", "AUCTION_CLOSED", "SETTLED", "PAID_OUT", "FINALIZED"):
                if cell_state == "PENDING":
                    cell_state = "AUCTION"

            cell_data["state"] = cell_state
            member_data["cycles"].append(cell_data)

        timeline.append(member_data)

    # Also include cycle summary
    cycle_summaries = []
    for cycle in cycles:
        settlement = session.execute(
            select(SettlementRow).where(SettlementRow.cycle_id == cycle.id)
        ).scalar_one_or_none()

        cycle_summaries.append({
            "cycle_id": cycle.id,
            "cycle_number": cycle.number,
            "state": cycle.state,
            "due_date": cycle.due_date.isoformat() if cycle.due_date else None,
            "winner_member_id": cycle.winner_member_id,
            "discount": cycle.discount,
            "settlement_status": settlement.status if settlement else None,
        })

    return {
        "circle_id": circle_id,
        "circle_name": circle.name,
        "members": timeline,
        "cycles": cycle_summaries,
    }


def get_circle_dashboard(session: Session, circle_id: str) -> Dict[str, Any]:
    """
    Get organizer dashboard summary for a circle.
    Returns collections, auctions, payouts, risk summary.
    """
    circle = session.get(Circle, circle_id)
    if not circle:
        return {"error": "Circle not found"}

    # Total members
    total_members = session.execute(
        select(func.count(Member.id)).where(Member.circle_id == circle_id)
    ).scalar()

    # Members who have won
    won_members = session.execute(
        select(func.count(Member.id)).where(
            Member.circle_id == circle_id,
            Member.has_won == True
        )
    ).scalar()

    # Total cycles
    total_cycles = session.execute(
        select(func.count(Cycle.id)).where(Cycle.circle_id == circle_id)
    ).scalar()

    # Completed cycles
    completed_cycles = session.execute(
        select(func.count(Cycle.id)).where(
            Cycle.circle_id == circle_id,
            Cycle.state.in_(["FINALIZED", "PAID_OUT"])
        )
    ).scalar()

    # Current cycle (latest)
    current_cycle = session.execute(
        select(Cycle).where(Cycle.circle_id == circle_id).order_by(Cycle.number.desc())
    ).scalar_one_or_none()

    # Collections summary for current cycle
    collections = {"collected": 0, "outstanding": 0, "late": 0, "total_members": 0}
    if current_cycle:
        obligations = session.execute(
            select(Obligation).where(Obligation.cycle_id == current_cycle.id)
        ).scalars().all()

        for ob in obligations:
            outstanding = ob.gross_due + ob.adjustments - ob.dividend_credit - ob.confirmed_paid
            if outstanding <= 0:
                collections["collected"] += 1
            elif current_cycle.due_date and current_cycle.due_date < datetime.now(timezone.utc):
                collections["late"] += 1
                collections["outstanding"] += 1
            else:
                collections["outstanding"] += 1
            collections["total_members"] += 1

    # Auction summary
    auctions = {"completed": 0, "pending": 0, "current_state": None}
    if current_cycle:
        auctions["current_state"] = current_cycle.state
        if current_cycle.state in ("AUCTION_OPEN", "AUCTION_CLOSED"):
            auctions["pending"] += 1
        elif current_cycle.state in ("SETTLED", "PAID_OUT", "FINALIZED"):
            auctions["completed"] += 1

    # Count completed auctions
    completed_auctions = session.execute(
        select(func.count(Cycle.id)).where(
            Cycle.circle_id == circle_id,
            Cycle.state.in_(["SETTLED", "PAID_OUT", "FINALIZED"])
        )
    ).scalar()
    auctions["completed"] = completed_auctions

    # Payout summary
    payouts = {"completed": 0, "pending": 0, "failed": 0}
    settlements = session.execute(
        select(SettlementRow).where(SettlementRow.circle_id == circle_id)
    ).scalars().all()

    for s in settlements:
        if s.status == "FINALIZED":
            payouts["completed"] += 1
        elif s.status in ("PAYOUT_REQUESTED", "PAYOUT_SUBMITTED", "PAYOUT_CONFIRMED"):
            payouts["pending"] += 1
        elif s.status == "PAYOUT_FAILED":
            payouts["failed"] += 1

    # Risk summary - members with late payments
    late_members = []
    if current_cycle:
        late_obligations = session.execute(
            select(Obligation, Member).join(Member, Obligation.member_id == Member.id).where(
                Obligation.cycle_id == current_cycle.id,
                Obligation.confirmed_paid < (Obligation.gross_due + Obligation.adjustments - Obligation.dividend_credit)
            )
        ).all()

        for ob, member in late_obligations:
            outstanding = ob.gross_due + ob.adjustments - ob.dividend_credit - ob.confirmed_paid
            if outstanding > 0:
                late_members.append({
                    "member_id": member.id,
                    "member_name": member.name,
                    "position": member.position,
                    "outstanding": outstanding,
                    "due_date": current_cycle.due_date.isoformat() if current_cycle.due_date else None,
                    "is_late": current_cycle.due_date and current_cycle.due_date < datetime.now(timezone.utc),
                })

    # Recent ledger activity (last 10 events)
    recent_events = session.execute(
        select(LedgerEventRow).where(LedgerEventRow.circle_id == circle_id)
        .order_by(LedgerEventRow.timestamp.desc()).limit(10)
    ).scalars().all()

    recent_activity = [
        {
            "event_id": e.id,
            "event_type": e.event_type,
            "amount": e.amount,
            "currency": e.currency,
            "timestamp": e.timestamp.isoformat(),
            "member_id": e.member_id,
            "cycle_id": e.cycle_id,
        }
        for e in recent_events
    ]

    return {
        "circle_id": circle_id,
        "circle_name": circle.name,
        "summary": {
            "total_members": total_members,
            "won_members": won_members,
            "remaining_members": total_members - won_members,
            "total_cycles": total_cycles,
            "completed_cycles": completed_cycles,
            "current_cycle_number": current_cycle.number if current_cycle else 0,
            "current_cycle_state": current_cycle.state if current_cycle else None,
        },
        "collections": collections,
        "auctions": auctions,
        "payouts": payouts,
        "risk": {
            "late_members_count": len(late_members),
            "late_members": late_members,
        },
        "recent_activity": recent_activity,
    }


def get_member_view(session: Session, circle_id: str, member_id: str) -> Dict[str, Any]:
    """
    Get member-specific view: my payments, bid screen, settlement breakdown.
    """
    member = session.get(Member, member_id)
    if not member or member.circle_id != circle_id:
        return {"error": "Member not found in circle"}

    # Get all cycles for this circle
    cycles = session.execute(
        select(Cycle).where(Cycle.circle_id == circle_id).order_by(Cycle.number)
    ).scalars().all()

    my_cycles = []
    for cycle in cycles:
        obligation = session.execute(
            select(Obligation).where(
                Obligation.cycle_id == cycle.id,
                Obligation.member_id == member_id
            )
        ).scalar_one_or_none()

        settlement = session.execute(
            select(SettlementRow).where(SettlementRow.cycle_id == cycle.id)
        ).scalar_one_or_none()

        # My bid for this cycle (if auction)
        my_bid = session.execute(
            select(BidRow).where(
                BidRow.cycle_id == cycle.id,
                BidRow.member_id == member_id
            )
        ).scalar_one_or_none()

        cycle_data = {
            "cycle_id": cycle.id,
            "cycle_number": cycle.number,
            "state": cycle.state,
            "due_date": cycle.due_date.isoformat() if cycle.due_date else None,
            "obligation": None,
            "bid": None,
            "settlement": None,
        }

        if obligation:
            cycle_data["obligation"] = {
                "gross_due": obligation.gross_due,
                "dividend_credit": obligation.dividend_credit,
                "adjustments": obligation.adjustments,
                "confirmed_paid": obligation.confirmed_paid,
                "outstanding": obligation.gross_due + obligation.adjustments - obligation.dividend_credit - obligation.confirmed_paid,
            }

        if my_bid:
            cycle_data["bid"] = {
                "discount": my_bid.discount,
                "accepted": my_bid.accepted,
                "reasons": my_bid.reasons,
            }

        if settlement and settlement.data:
            settlement_data = settlement.data.get("settlement", {})
            winner_payout = settlement_data.get("winner_payout", {})
            dividends = settlement_data.get("dividends", {})

            cycle_data["settlement"] = {
                "status": settlement.status,
                "is_winner": winner_payout.get("winner_member_id") == member_id,
                "winner_payout": winner_payout if winner_payout.get("winner_member_id") == member_id else None,
                "my_dividend": dividends.get(member_id, 0),
                "total_dividend_pool": sum(dividends.values()) if dividends else 0,
            }

        my_cycles.append(cycle_data)

    return {
        "member_id": member.id,
        "member_name": member.name,
        "position": member.position,
        "has_won": member.has_won,
        "security_status": member.security_status,
        "cycles": my_cycles,
    }