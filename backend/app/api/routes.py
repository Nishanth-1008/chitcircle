"""HTTP layer: authentication stub, request parsing, authorization. No financial logic here."""
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from financial_engine.reconciliation import HmacVerifier

from .. import config, schemas
from ..db import get_session
from ..services import financial_service as svc
from ..services.gateway import PayoutGateway, get_gateway

router = APIRouter()


@dataclass
class Actor:
    id: str
    role: str


def actor(x_actor_id: str = Header(...), x_actor_role: str = Header("member")) -> Actor:
    """Authentication stub: replace with real auth (JWT/OIDC). Services re-check organizer identity."""
    if x_actor_role not in ("organizer", "member", "approver", "system"):
        raise HTTPException(403, "unknown role")
    return Actor(x_actor_id, x_actor_role)


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/circles", status_code=201)
def create_circle(body: schemas.CreateCircle, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.create_circle(s, a.id, body.name, body.ruleset, body.members)


@router.get("/circles/{circle_id}")
def get_circle(circle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.get_circle(s, circle_id)


@router.post("/circles/{circle_id}/rulesets", status_code=201)
def new_ruleset(circle_id: str, body: schemas.NewRuleset, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.add_ruleset_version(s, circle_id, a.id, body.ruleset, body.reason)


@router.put("/circles/{circle_id}/members/{member_id}/security")
def security(circle_id: str, member_id: str, body: schemas.SecurityIn, a: Actor = Depends(actor),
             s: Session = Depends(get_session)):
    return svc.set_security_status(s, circle_id, member_id, a.id, body.status)


@router.get("/circles/{circle_id}/members/{member_id}/risk")
def risk(circle_id: str, member_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.member_risk(s, circle_id, member_id)


@router.post("/circles/{circle_id}/cycles", status_code=201)
def new_cycle(circle_id: str, body: schemas.NewCycle, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.create_cycle(s, circle_id, a.id, body.due_date, body.ruleset_version)


@router.get("/cycles/{cycle_id}")
def get_cycle(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.get_cycle(s, cycle_id)


@router.post("/cycles/{cycle_id}/open")
def open_cycle(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.open_cycle(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/auction/open")
def open_auction(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.open_auction(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/auction/bids")
def bid(cycle_id: str, body: schemas.BidIn, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.submit_bid(s, cycle_id, a.id, body.member_id, body.discount)


@router.get("/cycles/{cycle_id}/auction/bids")
def bids(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.list_bids(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/auction/close")
def close_auction(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.close_auction(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/recipient")
def recipient(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.select_recipient(s, cycle_id, a.id)


@router.post("/cycles/{cycle_id}/early-payout")
def early(cycle_id: str, body: schemas.EarlyPayoutIn, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.early_payout(s, cycle_id, a.id, body.requester_id, body.discount, body.consenting_member_ids)


@router.post("/cycles/{cycle_id}/settlement", status_code=201)
def calc_settlement(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.calculate_cycle_settlement(s, cycle_id, a.id)


@router.get("/cycles/{cycle_id}/ledger")
def ledger(cycle_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.list_ledger(s, cycle_id)


@router.post("/cycles/{cycle_id}/resume")
def resume(cycle_id: str, body: schemas.ReasonIn, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.resume_cycle(s, cycle_id, a.id, body.reason)


@router.post("/cycles/{cycle_id}/disputes")
def dispute(cycle_id: str, body: schemas.ReasonIn, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.open_dispute(s, cycle_id, a.id, body.reason)


@router.post("/cycles/{cycle_id}/disputes/resolve")
def resolve(cycle_id: str, body: schemas.ReasonIn, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.resolve_dispute(s, cycle_id, a.id, body.reason)


@router.get("/settlements/{settlement_id}")
def get_settlement(settlement_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.get_settlement(s, settlement_id)


@router.post("/settlements/{settlement_id}/approvals")
def approve(settlement_id: str, body: schemas.ApprovalIn, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.approve_settlement(s, settlement_id, a.id, a.role, body.decision, body.reason)


@router.post("/settlements/{settlement_id}/payout")
def payout(settlement_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session),
           gw: PayoutGateway = Depends(get_gateway)):
    return svc.execute_payout(s, settlement_id, a.id, gw)


@router.post("/settlements/{settlement_id}/payout/check")
def payout_check(settlement_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session),
                 gw: PayoutGateway = Depends(get_gateway)):
    return svc.check_payout(s, settlement_id, a.id, gw)


@router.get("/settlements/{settlement_id}/reconciliation")
def reconciliation(settlement_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.reconciliation_report(s, settlement_id)


@router.post("/settlements/{settlement_id}/finalize")
def finalize(settlement_id: str, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.finalize_settlement(s, settlement_id, a.id)


@router.post("/ledger/{event_id}/reversal")
def reversal(event_id: str, body: schemas.ReasonIn, a: Actor = Depends(actor), s: Session = Depends(get_session)):
    return svc.reverse_event(s, event_id, a.id, body.reason)


@router.post("/webhooks/provider")
async def provider_webhook(request: Request, s: Session = Depends(get_session),
                           x_signature: str = Header(None)):
    """Signed provider callbacks (payments, refunds, payouts). Unsigned/invalid callbacks are rejected."""
    secret = config.webhook_secret()
    if not secret:
        raise HTTPException(503, "webhook secret not configured")
    body = await request.body()
    if not HmacVerifier(secret).verify(body, x_signature):
        raise HTTPException(401, "invalid signature")
    try:
        payload = schemas.ProviderCallback.model_validate_json(body).model_dump()
    except Exception as exc:
        raise HTTPException(422, f"invalid callback: {exc}")
    return svc.apply_provider_event(s, payload)
