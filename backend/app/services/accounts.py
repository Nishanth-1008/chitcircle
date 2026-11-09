"""Accounts: users, the link between a circle seat and a user, and verified payout contacts.

PII (emails) lives on `users` and in encrypted `user_contacts`; the ledger and engine keep member ids only.
"""
from __future__ import annotations

from typing import Optional, Union

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .. import config
from ..errors import Conflict, Forbidden, NotFound, ServiceError, Unprocessable
from ..models import Circle, Member, User, UserContact

SELF_SERVICE_ROLES = {"member", "approver"}


def _norm_email(email: Optional[str]) -> Optional[str]:
    return email.strip().lower() if email and email.strip() else None


def user_view(session: Session, user: User) -> dict:
    contact = session.get(UserContact, user.id)
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role,
            "payout_email": contact.value if contact else None,
            "payout_email_verified": bool(contact and contact.verified)}


def register_user(session: Session, email: str, password: str, name: str, role: str = "member") -> User:
    from ..auth import create_user
    email = _norm_email(email)
    if role not in SELF_SERVICE_ROLES or (role != "member" and config.is_production()):
        raise Unprocessable("role must be 'member' (approver accounts are development-only)")
    if session.scalar(select(User).where(func.lower(User.email) == email)):
        raise Conflict("an account with this email already exists", "EMAIL_TAKEN")
    user = create_user(session, email, password, name.strip(), role)
    link_pending_seats(session, user)
    return user


def link_pending_seats(session: Session, user: User) -> int:
    """Claim seats an organizer reserved for this email before the person had an account."""
    seats = list(session.scalars(select(Member).where(
        Member.user_id.is_(None), func.lower(Member.invite_email) == _norm_email(user.email))))
    for m in seats:
        m.user_id = user.id
    if seats:
        session.commit()
    return len(seats)


def set_payout_contact(session: Session, user_id: str, email: str) -> dict:
    """Store the PayPal email used for invoices and payouts.

    Sandbox builds mark it verified immediately so sandbox accounts can be used end to end; a production
    build stores it unverified until a provider-side verification flow confirms ownership.
    """
    if not config.encryption_key():
        raise ServiceError("ENCRYPTION_KEY is not configured; contacts cannot be stored", "ENCRYPTION_NOT_CONFIGURED")
    user = session.get(User, user_id)
    if user is None:
        raise NotFound("user not found")
    row = session.get(UserContact, user_id)
    if row is None:
        row = UserContact(user_id=user_id, kind="email", value=_norm_email(email), verified=False)
        session.add(row)
    else:
        row.kind, row.value = "email", _norm_email(email)
    row.verified = not config.is_production()
    session.commit()
    return user_view(session, user)


# ---------------------------------------------------------------- seats
def build_seats(session: Session, circle_id: str, actor_id: str, specs: list[Union[str, dict]]) -> list[Member]:
    """Turn create-circle member entries into seats, linking registered users by email."""
    seats: list[Member] = []
    linked: set[str] = set()
    for i, raw in enumerate(specs):
        spec = {"name": raw} if isinstance(raw, str) else dict(raw)
        name = (spec.get("name") or "").strip()
        email = _norm_email(spec.get("email"))
        if not email and "@" in name and " " not in name:
            email, name = _norm_email(name), ""
        user_id = spec.get("user_id")
        if user_id and user_id != actor_id:
            raise Forbidden("a seat can only be linked to another person by inviting their email")
        if email and not user_id:
            user = session.scalar(select(User).where(func.lower(User.email) == email))
            user_id = user.id if user else None
            name = name or (user.name if user else "")
        if user_id and not name:
            user = session.get(User, user_id)
            name = user.name if user else ""
        name = name or (email.split("@")[0] if email else "")
        if not name:
            raise Unprocessable(f"member {i + 1} needs a name or an email")
        if user_id:
            if user_id in linked:
                raise Unprocessable("the same person cannot hold two seats in one circle")
            linked.add(user_id)
        seats.append(Member(circle_id=circle_id, name=name[:200], position=i + 1,
                            user_id=user_id, invite_email=email))
    return seats


def seat_for(session: Session, circle_id: str, actor_id: str) -> Optional[Member]:
    """The seat the caller holds in a circle (linked account, or the legacy member-id identity)."""
    return session.scalar(select(Member).where(
        Member.circle_id == circle_id, or_(Member.user_id == actor_id, Member.id == actor_id)))


def acts_for(member: Optional[Member], actor_id: str) -> bool:
    return member is not None and actor_id in (member.id, member.user_id)


def circle_role(session: Session, circle: Circle, actor_id: str) -> str:
    if circle.organizer_id == actor_id:
        return "organizer"
    return "member" if seat_for(session, circle.id, actor_id) else "none"


def require_circle_access(session: Session, circle: Circle, actor_id: str, actor_role: str = "member") -> str:
    """Organizer, seat holder, or a designated approver may read a circle. Returns the circle role."""
    role = circle_role(session, circle, actor_id)
    if role == "none" and actor_role != "approver" and actor_id != "system":
        raise Forbidden("you are not a member of this circle")
    return role
