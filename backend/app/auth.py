"""JWT authentication: issue/verify tokens, password hashing, actor resolution."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy import text
from sqlalchemy.orm import Session
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm

from .config import (
    allow_actor_headers,
    jwt_secret_key,
    jwt_algorithm,
    jwt_expiration_minutes,
)
from .models import User
from .db import get_session


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=jwt_expiration_minutes())
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, jwt_secret_key(), algorithm=jwt_algorithm())


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, jwt_secret_key(), algorithms=[jwt_algorithm()])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_user_by_id(session: Session, user_id: str) -> Optional[User]:
    return session.get(User, user_id)


def get_user_by_email(session: Session, email: str) -> Optional[User]:
    return session.query(User).filter(User.email == email).first()


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User:
    payload = decode_token(token)
    user_id: str = payload.get("sub")
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = get_user_by_id(session, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_organizer(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != "organizer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Organizer role required",
        )
    return current_user


@dataclass(frozen=True)
class Actor:
    """The caller, resolved for this request.

    `method` records how the actor was established:
      - ``jwt``    a verified Bearer token; `role` is read from the database, never from the token.
      - ``header`` the development/test ``X-Actor-Id`` stub (disabled when ``APP_ENV=production``).
    """
    id: str
    role: str
    method: str = "jwt"


async def get_current_actor(
    authorization: Optional[str] = Header(default=None),
    x_actor_id: Optional[str] = Header(default=None),
    x_actor_role: Optional[str] = Header(default=None),
    session: Session = Depends(get_session),
) -> Actor:
    """Resolve the caller.

    Bearer token wins. The header stub remains only because the web client and the API integration
    tests still send it (it is removed in Phase 2 along with the stub) — it is rejected outright in
    production, so a deployed instance can never be acted through by naming an actor id.
    """
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token",
                                headers={"WWW-Authenticate": "Bearer"})
        user = get_user_by_id(session, user_id)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found",
                                headers={"WWW-Authenticate": "Bearer"})
        # AuthZ is resolved from the database, not trusted from the token.
        # SET app.current_user_id is PostgreSQL-specific (RLS session variable);
        # on SQLite (tests, local bootstrap) it is a no-op since RLS isn't enabled there.
        if session.bind.dialect.name == "postgresql":
            session.execute(text("SET app.current_user_id = :id"), {"id": user.id})
        return Actor(id=user.id, role=user.role, method="jwt")

    if x_actor_id:
        if not allow_actor_headers():
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Actor headers are disabled; send a Bearer token",
                                headers={"WWW-Authenticate": "Bearer"})
        if session.bind.dialect.name == "postgresql":
            session.execute(text("SET app.current_user_id = :id"), {"id": x_actor_id})
        return Actor(id=x_actor_id, role=x_actor_role or "member", method="header")

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated",
                        headers={"WWW-Authenticate": "Bearer"})


def create_user(
    session: Session,
    email: str,
    password: str,
    name: str,
    role: str = "member",
) -> User:
    user = User(
        email=email,
        hashed_password=hash_password(password),
        name=name,
        role=role,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user