"""HTTP layer: authentication, request parsing, authorization. No financial logic here."""
from dataclasses import dataclass
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from financial_engine.money import Money
from financial_engine.reconciliation import HmacVerifier

from .. import config, schemas
from ..db import get_session
from ..services import financial_service as svc
from ..services.read_models import get_circle_timeline, get_circle_dashboard, get_member_view
from ..services.gateway import (
    PayoutGateway, get_gateway, CollectionGateway, get_collection_gateway, get_webhook_verifier
)
from ..auth import (
    create_access_token, get_current_user, get_current_organizer,
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


@dataclass
class Actor:
    id: str
    role: str


def get_current_actor(
    request: Request,
    session: Session = Depends(get_session),
    x_actor_id: Optional[str] = Header(None, alias="X-Actor-Id"),
    x_actor_role: Optional[str] = Header("member", alias="X-Actor-Role"),
) -> Actor:
    """Allow Bearer JWT token if provided; fallback to X-Actor-Id / X-Actor-Role headers in dev."""
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        try:
            payload = decode_token(token)
            uid = payload.get("sub")
            role = payload.get("role", "member")
            if uid:
                return Actor(id=uid, role=role)
        except Exception:
            pass
    if x_actor_id:
        return Actor(id=x_actor_id, role=x_actor_role or "member")
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Provide Bearer token or X-Actor-Id.",
        headers={"WWW-Authenticate": "Bearer"},
    )


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
def ledger(cycle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    return svc.list_ledger(s, cycle_id)


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
    """Signed provider callbacks (payments, refunds, payouts). Unsigned/invalid callbacks are rejected."""
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
    return svc.apply_provider_event(s, payload)


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
    )

    return result


# Read model endpoints

@router.get("/circles/{circle_id}/timeline")
def circle_timeline(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """Get timeline grid for Bryntum: member x cycle with cell states."""
    return get_circle_timeline(s, circle_id)


@router.get("/circles/{circle_id}/dashboard")
def circle_dashboard(circle_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """Get organizer dashboard summary."""
    return get_circle_dashboard(s, circle_id)


@router.get("/circles/{circle_id}/members/{member_id}/view")
def member_view(circle_id: str, member_id: str, a = Depends(get_current_actor), s: Session = Depends(get_session)):
    """Get member-specific view: my payments, bids, settlements."""
    return get_member_view(s, circle_id, member_id)
