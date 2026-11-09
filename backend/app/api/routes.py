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
from ..services import accounts as A
from ..services import agents as agents_svc
from ..services import financial_service as svc
from ..services import paypal_events
from ..services import queries as Q
from ..services import sandbox as sandbox_svc
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
    from sqlalchemy import func
    from ..models import User
    user = session.query(User).filter(func.lower(User.email) == form_data.username.strip().lower()).first()
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
    A.link_pending_seats(session, user)
    return _token_response(session, user)


def _token_response(session: Session, user) -> dict:
    access_token = create_access_token(data={"sub": user.id, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer", "user_id": user.id, "role": user.role,
            "expires_in": config.jwt_expiration_minutes() * 60, "user": A.user_view(session, user)}


@router.post("/auth/register", status_code=201)
def register(body: schemas.RegisterIn, session: Session = Depends(get_session)):
    """Create an account. Seats an organizer reserved for this email are linked automatically."""
    user = A.register_user(session, body.email, body.password, body.name, body.role)
    return _token_response(session, user)


@router.get("/auth/me")
def me(a=Depends(get_current_actor), s: Session = Depends(get_session)):
    from ..models import User
    user = s.get(User, a.id)
    if user is None:
        return {"id": a.id, "email": None, "name": a.id, "role": a.role, "payout_email": None,
                "payout_email_verified": False}
    return A.user_view(s, user)


@router.post("/auth/refresh")
def refresh(a=Depends(get_current_actor), s: Session = Depends(get_session)):
    """Exchange a still-valid token for a fresh one (sliding session)."""
    from ..models import User
    user = s.get(User, a.id)
    if user is None or a.method != "jwt":
        raise HTTPException(status_code=401, detail="a valid bearer token is required")
    return _token_response(s, user)


@router.put("/auth/me/payout-email")
def set_payout_email(body: schemas.ContactIn, a=Depends(get_current_actor), s: Session = Depends(get_session)):
    return A.set_payout_contact(s, a.id, body.email)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/config")
def public_config():
    """What the client may offer: sandbox simulation tools and which payment gateway is active."""
    from ..services.gateway import gateway_name
    return {"environment": config.app_env(), "sandbox_tools": config.sandbox_tools_enabled(),
            "payment_gateway": gateway_name()}


@router.get("/circles")
def my_circles(a=Depends(get_current_actor), s: Session = Depends(get_session)):
    """Circles the caller organizes or holds a seat in, with the current round's status."""
    return Q.list_my_circles(s, a.id)


@router.post("/circles", status_code=201)
def create_circle(body: schemas.CreateCircle, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    members = [m if isinstance(m, str) else m.model_dump() for m in body.members]
    return svc.create_circle(s, a.id, body.name, body.ruleset, members)


@router.get("/circles/{circle_id}")
def get_circle(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.get_circle(s, circle_id, a.id, a.role)


@router.get("/circles/{circle_id}/cycles")
def list_cycles(circle_id: str, a=Depends(get_current_actor), s: Session = Depends(get_session)):
    return Q.list_cycles(s, circle_id, a.id, a.role)


@router.get("/circles/{circle_id}/ledger")
def circle_ledger(circle_id: str, cursor: Optional[str] = None, limit: int = 50, cycle_id: Optional[str] = None,
                  member_id: Optional[str] = None, a=Depends(get_current_actor), s: Session = Depends(get_session)):
    return Q.circle_ledger(s, circle_id, a.id, a.role, cursor=cursor, limit=limit, cycle_id=cycle_id,
                           member_id=member_id)


@router.post("/circles/{circle_id}/agents/collections/run")
def run_collections_agent(circle_id: str, a=Depends(get_current_actor), s: Session = Depends(get_session)):
    """Collections agent: scan open obligations and propose reminders / catch-up invoices for approval."""
    return agents_svc.run_collections_agent(s, circle_id, a.id)


@router.post("/circles/{circle_id}/rulesets", status_code=201)
def new_ruleset(circle_id: str, body: schemas.NewRuleset, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.add_ruleset_version(s, circle_id, a.id, body.ruleset, body.reason)


@router.put("/circles/{circle_id}/members/{member_id}/security")
def security(circle_id: str, member_id: str, body: schemas.SecurityIn, a = Depends(get_current_actor),
             s: Session = Depends(get_session)):
    return svc.set_security_status(s, circle_id, member_id, a.id, body.status)


@router.get("/circles/{circle_id}/members/{member_id}/risk")
def risk(circle_id: str, member_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    _require_self_or_organizer(s, circle_id, member_id, a)
    return svc.member_risk(s, circle_id, member_id)


def _require_self_or_organizer(s: Session, circle_id: str, member_id: str, a) -> None:
    """Private member data (risk, member view) is for the member and the organizer only."""
    from ..errors import Forbidden
    from ..models import Member
    circle = svc._circle(s, circle_id)
    if circle.organizer_id == a.id or a.role == "approver":
        return
    if not A.acts_for(s.get(Member, member_id), a.id):
        raise Forbidden("this is private to the member and the organizer")


@router.post("/circles/{circle_id}/cycles", status_code=201)
def new_cycle(circle_id: str, body: schemas.NewCycle, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.create_cycle(s, circle_id, a.id, body.due_date, body.ruleset_version)


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.get_cycle(s, cycle_id, a.id, a.role)


@router.get("/cycles/{cycle_id}/members/{member_id}/explanation")
def explain(cycle_id: str, member_id: str, a=Depends(get_current_actor), s: Session = Depends(get_session)):
    """Explainer: plain-language breakdown of a member's installment, built from stored engine output."""
    return agents_svc.explain_installment(s, cycle_id, member_id, a.id, a.role)


@router.get("/cycles/{cycle_id}/auction/preview")
def bid_preview(cycle_id: str, member_id: str, discount: int, a=Depends(get_current_actor),
                s: Session = Depends(get_session)):
    """Bid advisor: what a discount would mean for the bidder, computed by the settlement engine."""
    return agents_svc.bid_preview(s, cycle_id, member_id, discount, a.id)


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
    cycle = svc._cycle(s, cycle_id)
    A.require_circle_access(s, svc._circle(s, cycle.circle_id), a.id, a.role)
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
    return svc.list_ledger(s, cycle_id, cursor=cursor, limit=limit, actor_id=a.id, actor_role=a.role)


@router.post("/cycles/{cycle_id}/resume")
def resume(cycle_id: str, body: schemas.ReasonIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.resume_cycle(s, cycle_id, a.id, body.reason)


@router.post("/cycles/{cycle_id}/disputes")
def dispute(cycle_id: str, body: schemas.ReasonIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    A.require_circle_access(s, svc._circle(s, svc._cycle(s, cycle_id).circle_id), a.id, a.role)
    return svc.open_dispute(s, cycle_id, a.id, body.reason)


@router.post("/cycles/{cycle_id}/disputes/resolve")
def resolve(cycle_id: str, body: schemas.ReasonIn, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.resolve_dispute(s, cycle_id, a.id, body.reason)


@router.get("/settlements/{settlement_id}")
def get_settlement(settlement_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.get_settlement(s, settlement_id, a.id, a.role)


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
    row = svc._settlement(s, settlement_id)
    A.require_circle_access(s, svc._circle(s, row.circle_id), a.id, a.role)
    return svc.reconciliation_report(s, settlement_id)


@router.post("/sandbox/cycles/{cycle_id}/payments")
def sandbox_payment(cycle_id: str, body: schemas.SandboxPaymentIn, a=Depends(get_current_actor),
                    s: Session = Depends(get_session)):
    """Sandbox only: simulate a provider-confirmed contribution through the real ingest pipeline."""
    return sandbox_svc.simulate_payment(s, cycle_id, a.id, body.member_id, body.amount, body.status)


@router.post("/sandbox/settlements/{settlement_id}/payout")
def sandbox_payout(settlement_id: str, body: schemas.SandboxPayoutIn, a=Depends(get_current_actor),
                   s: Session = Depends(get_session)):
    """Sandbox only: simulate the provider's payout confirmation callback."""
    return sandbox_svc.simulate_payout(s, settlement_id, a.id, body.status)


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
        payload = json.loads(body)
    except Exception as exc:
        raise HTTPException(422, f"invalid callback: {exc}")
    if paypal_events.is_paypal_event(payload):
        normalized = paypal_events.normalize(s, payload)
        if normalized is None:
            # not a payment we track; acknowledge so the provider stops retrying
            return {"ignored": True, "event_type": payload.get("event_type")}
        payload = normalized
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
    """Create a PayPal invoice for a member's contribution obligation (organizer or the member)."""
    from ..services.financial_service import _cycle, _circle, _rules
    from ..errors import Forbidden
    from ..models import Member, Obligation

    cycle = _cycle(s, cycle_id, lock=True)
    circle = _circle(s, cycle.circle_id)
    if a.id != circle.organizer_id and not A.acts_for(s.get(Member, member_id), a.id):
        raise Forbidden("only the member or the organizer can request a payment link")
    rules = _rules(s, cycle.circle_id, cycle.ruleset_version)

    ob = s.scalar(select(Obligation).where(Obligation.cycle_id == cycle.id, Obligation.member_id == member_id))
    if ob is None:
        raise HTTPException(404, "obligation not found")

    # Calculate outstanding amount
    outstanding = ob.gross_due + ob.adjustments - ob.dividend_credit - ob.confirmed_paid
    if outstanding <= 0:
        raise HTTPException(400, "no outstanding amount")

    amount = Money(outstanding, rules.currency)
    idempotency_key = f"collection:{cycle.id}:{member_id}"
    back = f"{config.get_env('APP_BASE_URL', 'http://localhost:3000')}/app/circles/{cycle.circle_id}/cycles/{cycle.id}"

    try:
        result = gw.create_collection(
            idempotency_key=idempotency_key,
            member_id=member_id,
            amount=amount,
            description=f"ChitCircle contribution, {circle.name} round {cycle.number}",
            return_url=f"{back}?payment=returned",
            cancel_url=f"{back}?payment=cancelled",
            session=s,
        )
    except Exception as exc:  # noqa: BLE001 - provider errors surface as a clear 502, not a 500
        raise HTTPException(status_code=502, detail=f"payment provider error: {type(exc).__name__}")

    if result.status == "FAILED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=result.detail or "collection creation failed",
        )
    return {"status": result.status, "provider_ref": result.provider_ref, "approval_url": result.approval_url,
            "detail": result.detail, "amount": outstanding, "currency": rules.currency}


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
    A.require_circle_access(s, svc._circle(s, circle_id), a.id, a.role)
    data = get_circle_timeline(s, circle_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return _etag_response(data, if_none_match)


@router.get("/circles/{circle_id}/dashboard")
def circle_dashboard(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_read_session),
                     if_none_match: Optional[str] = Header(None)):
    """Get organizer dashboard summary."""
    A.require_circle_access(s, svc._circle(s, circle_id), a.id, a.role)
    data = get_circle_dashboard(s, circle_id)
    if "error" in data:
        raise HTTPException(404, data["error"])
    return _etag_response(data, if_none_match)


@router.get("/circles/{circle_id}/members/{member_id}/view")
def member_view(circle_id: str, member_id: str, a = Depends(get_current_actor), s: Session = Depends(get_read_session),
                if_none_match: Optional[str] = Header(None)):
    """Get member-specific view: my payments, bids, settlements."""
    _require_self_or_organizer(s, circle_id, member_id, a)
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


@router.post("/proposed-actions/{proposal_id}/reject")
def reject_proposal(proposal_id: str, body: schemas.RevokeMandateIn,
                    a=Depends(get_current_actor), s: Session = Depends(get_session)):
    """Dismiss a proposal; no mandate is issued."""
    return svc.reject_proposal(s, proposal_id, a.id, body.reason)


@router.post("/mandates/{mandate_id}/execute")
def execute_mandate(mandate_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session),
                    gw: PayoutGateway = Depends(get_gateway),
                    cgw: CollectionGateway = Depends(get_collection_gateway)):
    """Execute an approved, mandate-locked action. Takes only the mandate id."""
    return svc.execute_mandate(s, mandate_id, a.id, gw, cgw)


@router.post("/mandates/{mandate_id}/revoke")
def revoke_mandate(mandate_id: str, body: schemas.RevokeMandateIn,
                   a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """Revoke an unused mandate."""
    return svc.revoke_mandate(s, mandate_id, a.id, body.reason)


@router.get("/circles/{circle_id}/proposed-actions")
def list_proposals(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """List proposed actions for a circle (agent proposal queue). Organizer only."""
    svc._require_organizer(svc._circle(s, circle_id), a.id)
    return svc.list_proposals(s, circle_id)


@router.get("/circles/{circle_id}/mandates")
def list_mandates(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """List mandates for a circle (audit trail). Organizer only."""
    svc._require_organizer(svc._circle(s, circle_id), a.id)
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
