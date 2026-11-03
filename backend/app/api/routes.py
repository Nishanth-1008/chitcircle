"""HTTP layer: authentication, request parsing, authorization. No financial logic here."""
from dataclasses import dataclass
from typing import Optional

from datetime import datetime, timezone

import hashlib
import json

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from financial_engine.money import Money
from financial_engine.reconciliation import HmacVerifier

from .. import config, schemas
from ..db import get_session, get_read_session
from ..services import financial_service as svc
from ..services.read_models import get_circle_timeline, get_circle_dashboard, get_member_view
from ..services.gateway import (
    PayoutGateway, get_gateway, CollectionGateway, get_collection_gateway, get_webhook_verifier
)
from ..auth import (
    create_access_token, get_current_user, get_current_organizer, get_current_actor,
    create_user, hash_password, verify_password, decode_token
)

router = APIRouter()


@router.post("/auth/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: Session = Depends(get_session),
):
    """Login endpoint - returns JWT access token."""
    from ..models import User
    user = session.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    access_token = create_access_token(data={"sub": user.id, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id, "role": user.role}


@router.post("/auth/register", status_code=201)
def register(
    email: str,
    password: str,
    name: str,
    role: str = "member",
    session: Session = Depends(get_session),
):
    """Register a new user (for demo purposes)."""
    from ..models import User
    existing = session.query(User).filter(User.email == email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )
    user = create_user(session, email, password, name, role)
    access_token = create_access_token(data={"sub": user.id, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id, "role": user.role}


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/circles", status_code=201)
def create_circle(body: schemas.CreateCircle, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.create_circle(s, a.id, body.name, body.ruleset, body.members)


@router.get("/circles/{circle_id}")
def get_circle(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.get_circle(s, circle_id)


@router.post("/circles/{circle_id}/rulesets", status_code=201)
def new_ruleset(circle_id: str, body: schemas.NewRuleset, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.add_ruleset_version(s, circle_id, a.id, body.ruleset, body.reason)


@router.put("/circles/{circle_id}/members/{member_id}/security")
def security(circle_id: str, member_id: str, body: schemas.SecurityIn, a = Depends(get_current_actor),
             s: Session = Depends(get_session)):
    return svc.set_security_status(s, circle_id, member_id, a.id, body.status)


@router.get("/circles/{circle_id}/members/{member_id}/risk")
def risk(circle_id: str, member_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.member_risk(s, circle_id, member_id)


@router.post("/circles/{circle_id}/cycles", status_code=201)
def new_cycle(circle_id: str, body: schemas.NewCycle, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.create_cycle(s, circle_id, a.id, body.due_date, body.ruleset_version)


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.get_cycle(s, cycle_id)


@router.post("/cycles/{cycle_id}/open")
def open_cycle(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.open_cycle(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/auction/open")
def open_auction(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.open_auction(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/auction/bids")
def bid(cycle_id: str, body: schemas.BidIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.submit_bid(s, cycle_id, a.id, body.member_id, body.discount)


@router.get("/cycles/{cycle_id}/auction/bids")
def bids(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.list_bids(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/auction/close")
def close_auction(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.close_auction(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/recipient")
def recipient(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.select_recipient(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/early-payout")
def early(cycle_id: str, body: schemas.EarlyPayoutIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.early_payout(s, cycle_id, a.id, body.requester_id, body.discount, body.consenting_member_ids)


@router.post("/cycles/{cycle_id}/settlement", status_code=201)
def calc_settlement(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.calculate_cycle_settlement(s, cycle_id, a.id)


@router.get("/cycles/{cycle_id}/ledger")
def ledger(cycle_id: str, cursor: Optional[str] = None, limit: Optional[int] = 50,
           a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.list_ledger(s, cycle_id, cursor=cursor, limit=limit)


@router.post("/cycles/{cycle_id}/resume")
def resume(cycle_id: str, body: schemas.ReasonIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.resume_cycle(s, cycle_id, a.id, body.reason)


@router.post("/cycles/{cycle_id}/disputes")
def dispute(cycle_id: str, body: schemas.ReasonIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.open_dispute(s, cycle_id, a.id, body.reason)


@router.post("/cycles/{cycle_id}/disputes/resolve")
def resolve(cycle_id: str, body: schemas.ReasonIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.resolve_dispute(s, cycle_id, a.id, body.reason)


@router.get("/settlements/{settlement_id}")
def get_settlement(settlement_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.get_settlement(s, settlement_id)


@router.post("/settlements/{settlement_id}/approvals")
def approve(settlement_id: str, body: schemas.ApprovalIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.approve_settlement(s, settlement_id, a.id, a.role, body.decision, body.reason)


@router.post("/settlements/{settlement_id}/payout")
def payout(settlement_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session),
           gw: PayoutGateway = Depends(get_gateway)):
    return svc.execute_payout(s, settlement_id, a.id, gw)


@router.post("/settlements/{settlement_id}/payout/check")
def payout_check(settlement_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session),
                 gw: PayoutGateway = Depends(get_gateway)):
    return svc.check_payout(s, settlement_id, a.id, gw)


@router.get("/settlements/{settlement_id}/reconciliation")
def reconciliation(settlement_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.reconciliation_report(s, settlement_id)


@router.post("/settlements/{settlement_id}/finalize")
def finalize(settlement_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.finalize_settlement(s, settlement_id, a.id)


@router.post("/ledger/{event_id}/reversal")
def reversal(event_id: str, body: schemas.ReasonIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.reverse_event(s, event_id, a.id, body.reason)


@router.post("/webhooks/provider")
async def provider_webhook(request: Request, s: Session = Depends(get_session)):
    """Signed provider callbacks (payments, refunds, payouts). Unsigned/invalid callbacks are rejected.

    Two-phase: phase A persists the verified raw body and returns 200 immediately; phase B applies
    asynchronously in the worker via `process_pending_provider_events`. A crash between the provider
    callback and durable processing cannot lose an event — the worker finishes it on the next pass.
    """
    secret = config.webhook_secret()
    if not secret:
        raise HTTPException(503, "webhook secret not configured")
    body = await request.body()
    headers = dict(request.headers)
    verifier = get_webhook_verifier()
    if not verifier.verify(body, headers):
        raise HTTPException(401, "invalid webhook signature")
    try:
        import json
        payload = json.loads(body)
    except Exception as exc:
        raise HTTPException(422, f"invalid callback: {exc}")
    # Phase A only: persist durably, return 200. Phase B runs in the worker.
    return svc._ingest_provider_event(s, payload, body.decode("utf-8", "replace"), True)


@router.post("/collections/create")
def create_collection(
    cycle_id: str,
    member_id: str,
    a = Depends(get_current_actor),
    s: Session = Depends(get_session),
    gw: CollectionGateway = Depends(get_collection_gateway),
):
    """Create a PayPal invoice for a member's contribution obligation."""
    from ..services.financial_service import _cycle, _circle, _require_organizer, _rules
    from financial_engine.money import Money

    cycle = _cycle(s, cycle_id, lock=True)
    circle = _circle(s, cycle.circle_id)
    _require_organizer(circle, a.id)
    rules = _rules(s, cycle.circle_id, cycle.ruleset_version)

    # Find the obligation
    from ..models import Obligation
    from sqlalchemy import select
    ob = s.scalar(select(Obligation).where(Obligation.cycle_id == cycle.id, Obligation.member_id == member_id))
    if ob is None:
        raise HTTPException(404, "obligation not found")

    # Calculate outstanding amount
    outstanding = ob.gross_due + ob.adjustments - ob.dividend_credit - ob.confirmed_paid
    if outstanding <= 0:
        raise HTTPException(400, "no outstanding amount")

    amount = Money(outstanding, rules.currency)
    idempotency_key = f"collection:{cycle.id}:{member_id}"

    # Create collection request
    result = gw.create_collection(
        idempotency_key=idempotency_key,
        member_id=member_id,
        amount=amount,
        description=f"Chit Circle contribution for cycle {cycle.number}",
        return_url=f"{config.get_env('APP_BASE_URL', 'http://localhost:3000')}/circles/{cycle.circle_id}/payments/success",
        cancel_url=f"{config.get_env('APP_BASE_URL', 'http://localhost:3000')}/circles/{cycle.circle_id}/payments/cancel",
        session=s,
    )

    if result.status == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.detail or "collection creation failed",
        )
    return result


# ---------------------------------------------------------------- read model ETags (gap #8)
#
# Read models are cached in Redis with a 60s TTL (read_models.py). Clients can use the
# ETag/If-None-Match exchange below to avoid re-transferring an unchanged payload:
# a 304 Not Modified is returned when the client's ETag still matches.

def _etag_response(data: dict, if_none_match: Optional[str] = None) -> Response:
    """Return a 304 if the client's ETag matches, else the JSON body with an ETag header."""
    body = json.dumps(data, sort_keys=True, default=str).encode()
    etag = hashlib.sha256(body).hexdigest()
    headers = {"ETag": etag}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=body, media_type="application/json", headers=headers)


# Read model endpoints

@router.get("/circles/{circle_id}/timeline")
def circle_timeline(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_read_session),
                    if_none_match: Optional[str] = Header(None)):
    """Get timeline grid for Bryntum: member x cycle with cell states."""
    data = get_circle_timeline(s, circle_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return _etag_response(data, if_none_match)


@router.get("/circles/{circle_id}/dashboard")
def circle_dashboard(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_read_session),
                     if_none_match: Optional[str] = Header(None)):
    """Get organizer dashboard summary."""
    data = get_circle_dashboard(s, circle_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return _etag_response(data, if_none_match)


@router.get("/circles/{circle_id}/members/{member_id}/view")
def member_view(circle_id: str, member_id: str, a = Depends(get_current_actor), s: Session = Depends(get_read_session),
                if_none_match: Optional[str] = Header(None)):
    """Get member-specific view: my payments, bids, settlements."""
    data = get_member_view(s, circle_id, member_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return _etag_response(data, if_none_match)


# ---------------------------------------------------------------- agent mandate routes (§13, adr/0007)
#
# The agent proposes; a human approves with step-up; the agent executes through the mandate.
# Routes are ordered: propose → approve → execute → revoke, plus list endpoints for the queue UI.

@router.post("/circles/{circle_id}/proposed-actions")
def propose_action(circle_id: str, body: schemas.ProposeActionIn,
                   a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """Agent (or organizer) proposes a mandate-gated action."""
    return svc.create_proposal(s, circle_id, a.id, body.kind, body.params,
                               body.rationale, body.expires_in_minutes)


@router.post("/proposed-actions/{proposal_id}/approve")
def approve_proposal(proposal_id: str, body: schemas.ApproveProposalIn,
                     a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """Human approves a proposal with step-up auth, issuing a single-use mandate."""
    return svc.approve_proposal(s, proposal_id, a.id, body.step_up_method,
                                body.step_up_evidence, body.cap_minor)


@router.post("/mandates/{mandate_id}/execute")
def execute_mandate(mandate_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session),
                    gw: PayoutGateway = Depends(get_gateway)):
    """Execute an approved, mandate-locked action. Takes only the mandate id."""
    return svc.execute_mandate(s, mandate_id, a.id, gw)


@router.post("/mandates/{mandate_id}/revoke")
def revoke_mandate(mandate_id: str, body: schemas.RevokeMandateIn,
                   a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """Revoke an unused mandate."""
    return svc.revoke_mandate(s, mandate_id, a.id, body.reason)


@router.get("/circles/{circle_id}/proposed-actions")
def list_proposals(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """List proposed actions for a circle (agent proposal queue)."""
    return svc.list_proposals(s, circle_id)


@router.get("/circles/{circle_id}/mandates")
def list_mandates(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """List mandates for a circle (audit trail)."""
    return svc.list_mandates(s, circle_id)


# ---------------------------------------------------------------- ops console (§16, gap #19)
#
# Administrative/operational endpoints for incident response and day-2 ops. All require the
# organizer role; they are intentionally narrow and read-mostly except where noted.

@router.get("/ops/ledger/search")
def ops_ledger_search(
    circle_id: Optional[str] = None,
    cycle_id: Optional[str] = None,
    member_id: Optional[str] = None,
    event_type: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: Optional[int] = 50,
    a = Depends(get_current_organizer),
    s: Session = Depends(get_session),
):
    """Search ledger events (read-only, for incident investigation)."""
    from ..models import LedgerEventRow

    stmt = select(LedgerEventRow).order_by(
        LedgerEventRow.timestamp.desc(), LedgerEventRow.id.desc(),
    )
    if circle_id:
        stmt = stmt.where(LedgerEventRow.circle_id == circle_id)
    if cycle_id:
        stmt = stmt.where(LedgerEventRow.cycle_id == cycle_id)
    if member_id:
        stmt = stmt.where(LedgerEventRow.member_id == member_id)
    if event_type:
        stmt = stmt.where(LedgerEventRow.event_type == event_type)
    if cursor:
        stmt = stmt.where(LedgerEventRow.id > cursor)
    if limit is not None:
        stmt = stmt.limit(min(limit, 200))

    rows = s.execute(stmt).scalars().all()
    return {
        "events": [
            {
                "id": e.id, "circle_id": e.circle_id, "cycle_id": e.cycle_id,
                "member_id": e.member_id, "event_type": e.event_type, "amount": e.amount,
                "currency": e.currency, "timestamp": e.timestamp.isoformat(),
                "actor": e.actor, "reason": e.reason,
            }
            for e in rows
        ],
        "cursor": rows[-1].id if rows else None,
    }


@router.post("/ops/jobs/{job_id}/replay")
def ops_replay_job(job_id: int, a = Depends(get_current_organizer), s: Session = Depends(get_session)):
    """Reset a dead-lettered job to PENDING so the worker retries it (operational recovery)."""
    from ..models import Job

    job = s.get(Job, job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.status != "DEAD":
        raise HTTPException(400, f"job is {job.status}; only DEAD jobs can be replayed")
    job.status = "PENDING"
    job.attempts = 0
    job.last_error = None
    job.locked_until = None
    job.run_at = datetime.now(timezone.utc)
    s.commit()
    return {"id": job.id, "status": job.status, "type": job.type}


@router.post("/ops/reconciliation/rerun")
def ops_rerun_reconciliation(a = Depends(get_current_organizer), s: Session = Depends(get_session)):
    """Enqueue a provider reconciliation job."""
    from app.services import jobs as J

    job = J.enqueue(s, type="provider_reconciliation", payload={})
    return {"job_id": job.id, "status": job.status, "type": job.type}


@router.post("/ops/circles/{circle_id}/pause")
def ops_pause_circle(circle_id: str, reason: Optional[str] = None,
                     a = Depends(get_current_organizer), s: Session = Depends(get_session)):
    """Set the circle_paused kill switch for a circle."""
    from ..models import FeatureFlag

    key = f"circle_paused:{circle_id}"
    flag = s.get(FeatureFlag, key)
    if flag is None:
        flag = FeatureFlag(key=key, value=True, reason=reason, updated_by=a.id)
        s.add(flag)
    else:
        flag.value = True
        flag.reason = reason
        flag.updated_by = a.id
    s.commit()
    return {"circle_id": circle_id, "paused": True, "reason": reason}


@router.post("/ops/circles/{circle_id}/resume")
def ops_resume_circle(circle_id: str, a = Depends(get_current_organizer), s: Session = Depends(get_session)):
    """Clear the circle_paused kill switch for a circle."""
    from ..models import FeatureFlag

    key = f"circle_paused:{circle_id}"
    flag = s.get(FeatureFlag, key)
    if flag is not None:
        flag.value = False
        flag.updated_by = a.id
        s.commit()
    return {"circle_id": circle_id, "paused": False}
