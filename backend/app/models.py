import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text,
                        UniqueConstraint, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Circle(Base):
    __tablename__ = "circles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    organizer_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RulesetRow(Base):
    __tablename__ = "rulesets"
    __table_args__ = (UniqueConstraint("circle_id", "version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    circle_id: Mapped[str] = mapped_column(ForeignKey("circles.id"))
    version: Mapped[int] = mapped_column(Integer)
    data: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20))
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Member(Base):
    __tablename__ = "members"
    __table_args__ = (UniqueConstraint("circle_id", "position"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    circle_id: Mapped[str] = mapped_column(ForeignKey("circles.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    position: Mapped[int] = mapped_column(Integer)
    security_status: Mapped[str] = mapped_column(String(20), default="NONE")
    has_won: Mapped[bool] = mapped_column(Boolean, default=False)


class Cycle(Base):
    __tablename__ = "cycles"
    __table_args__ = (UniqueConstraint("circle_id", "number"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    circle_id: Mapped[str] = mapped_column(ForeignKey("circles.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    ruleset_version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(40), default="DRAFT")
    prior_state: Mapped[str] = mapped_column(String(40), nullable=True)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payout_method: Mapped[str] = mapped_column(String(40), nullable=True)
    winner_member_id: Mapped[str] = mapped_column(String(36), nullable=True)
    discount: Mapped[int] = mapped_column(BigInteger, nullable=True)
    tie_seed: Mapped[str] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class StateTransition(Base):
    __tablename__ = "state_transitions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), index=True)
    from_state: Mapped[str] = mapped_column(String(40))
    to_state: Mapped[str] = mapped_column(String(40))
    actor: Mapped[str] = mapped_column(String(100))
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Obligation(Base):
    __tablename__ = "obligations"
    __table_args__ = (UniqueConstraint("cycle_id", "member_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), index=True)
    member_id: Mapped[str] = mapped_column(ForeignKey("members.id"), index=True)
    gross_due: Mapped[int] = mapped_column(BigInteger)
    dividend_credit: Mapped[int] = mapped_column(BigInteger, default=0)
    adjustments: Mapped[int] = mapped_column(BigInteger, default=0)
    confirmed_paid: Mapped[int] = mapped_column(BigInteger, default=0)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class BidRow(Base):
    __tablename__ = "bids"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), index=True)
    member_id: Mapped[str] = mapped_column(String(36))
    discount: Mapped[int] = mapped_column(BigInteger)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    accepted: Mapped[bool] = mapped_column(Boolean)
    reasons: Mapped[list] = mapped_column(JSON, default=list)


class LotteryRow(Base):
    __tablename__ = "lottery_draws"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), unique=True)   # no unauthorized reruns
    record: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SettlementRow(Base):
    __tablename__ = "settlements"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    cycle_id: Mapped[str] = mapped_column(ForeignKey("cycles.id"), unique=True)   # one settlement per cycle
    circle_id: Mapped[str] = mapped_column(String(36))
    ruleset_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="CALCULATED")
    data: Mapped[dict] = mapped_column(JSON)               # settlement + exact ruleset snapshot
    payout_idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    provider_payout_ref: Mapped[str] = mapped_column(String(100), nullable=True)
    payout_requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApprovalRow(Base):
    __tablename__ = "approvals"
    __table_args__ = (UniqueConstraint("settlement_id", "approver_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    settlement_id: Mapped[str] = mapped_column(ForeignKey("settlements.id"), index=True)
    approver_id: Mapped[str] = mapped_column(String(100))
    decision: Mapped[str] = mapped_column(String(10))
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class LedgerEventRow(Base):
    __tablename__ = "ledger_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    circle_id: Mapped[str] = mapped_column(String(36), index=True)
    cycle_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    member_id: Mapped[str] = mapped_column(String(36), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40))
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    actor: Mapped[str] = mapped_column(String(100))
    ruleset_version: Mapped[int] = mapped_column(Integer)
    settlement_id: Mapped[str] = mapped_column(String(36), nullable=True)
    provider_ref: Mapped[str] = mapped_column(String(100), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=True)
    reverses_event_id: Mapped[str] = mapped_column(String(36), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    approval: Mapped[dict] = mapped_column(JSON, nullable=True)
    journal: Mapped[dict] = mapped_column(JSON, nullable=True)


class LedgerImmutableError(Exception):
    pass


@event.listens_for(LedgerEventRow, "before_update")
@event.listens_for(LedgerEventRow, "before_delete")
def _ledger_is_append_only(mapper, connection, target):
    raise LedgerImmutableError("ledger events are append-only; record a linked reversal instead")


class ProviderEventRow(Base):
    __tablename__ = "provider_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider_txn_id: Mapped[str] = mapped_column(String(100), unique=True)       # duplicate callbacks ignored
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    cycle_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    member_id: Mapped[str] = mapped_column(String(36), nullable=True)
    settlement_id: Mapped[str] = mapped_column(String(36), nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    raw: Mapped[dict] = mapped_column(JSON)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
