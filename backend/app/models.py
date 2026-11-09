import uuid
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet
from sqlalchemy import (JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, Text,
                        TypeDecorator, UniqueConstraint, event)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .config import encryption_key


def _id() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EncryptedString(TypeDecorator):
    """AES-256 (Fernet) encrypted text column. Plaintext never hits disk.

    The ciphertext is stored as a base64 string in a plain VARCHAR column, so no
    migration is needed when switching a column to this type — the DB column type
    stays the same and the encryption happens entirely in the application layer.
    """

    impl = String
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        key = encryption_key()
        if not key:
            raise RuntimeError("ENCRYPTION_KEY is required to write encrypted fields")
        fernet = Fernet(key)
        return fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        key = encryption_key()
        if not key:
            raise RuntimeError("ENCRYPTION_KEY is required to read encrypted fields")
        fernet = Fernet(key)
        return fernet.decrypt(value.encode("ascii")).decode("utf-8")


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20), default="member")  # organizer, member, approver, admin
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Circle(Base):
    __tablename__ = "circles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    name: Mapped[str] = mapped_column(String(200))
    organizer_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    ledger_seq: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)


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
    # The account that holds this seat. NULL until the invited person registers (matched on invite_email).
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    invite_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)


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
    """Two-phase provider ingest: the callback is durable before anything is applied.

    Phase A (ingest) writes the raw body and marks the row RECEIVED. Phase B (apply) locks the row,
    applies it to the cycle/ledger under the cycle lock and marks it PROCESSED. A failure parks the
    row for the worker to retry; a permanent validation error marks it REJECTED. A crash between the
    two phases loses nothing: the row is already on disk.
    """
    __tablename__ = "provider_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(20), default="paypal")
    provider_event_id: Mapped[str] = mapped_column(String(120))                   # ingress dedupe key
    provider_txn_id: Mapped[str] = mapped_column(String(100), index=True)         # business idempotency key
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    state: Mapped[str] = mapped_column(String(20), default="RECEIVED", index=True)  # RECEIVED|PROCESSED|PARKED|REJECTED|DEAD
    cycle_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    member_id: Mapped[str] = mapped_column(String(36), nullable=True)
    settlement_id: Mapped[str] = mapped_column(String(36), nullable=True)
    # phase B (apply) fills these in once the cycle/obligation is resolved; NULL means "not yet applied"
    amount: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    raw: Mapped[dict] = mapped_column(JSON)
    raw_body: Mapped[str] = mapped_column(Text)                                   # exactly as received, for replay
    signature_ok: Mapped[bool] = mapped_column(Boolean, default=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    last_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("provider", "provider_event_id", name="uq_provider_event"),
    )


class OutboxRow(Base):
    """Transactional outbox: written in the same transaction as the ledger event."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    aggregate_type: Mapped[str] = mapped_column(String(50))
    aggregate_id: Mapped[str] = mapped_column(String(36))
    event_type: Mapped[str] = mapped_column(String(50))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_outbox_unpublished", "id"),
    )


class Job(Base):
    """Durable work queue: the outbox relay publishes here, and the scheduler enqueues here.

    Claiming is atomic (`SELECT ... FOR UPDATE SKIP LOCKED` on Postgres), so one worker owns a job.
    A claimed job carries `locked_until`: if the worker dies mid-run the job becomes claimable again
    after the visibility timeout, and `attempts` drives exponential backoff into a DEAD letter.
    """
    __tablename__ = "jobs"
    # Integer, not BigInteger: SQLite only autoincrements `INTEGER PRIMARY KEY`, and the queue must
    # work identically on the dev/test SQLite backend and on Postgres.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    type: Mapped[str] = mapped_column(String(80), index=True)
    circle_id: Mapped[str] = mapped_column(String(36), nullable=True, index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", index=True)  # PENDING|RUNNING|DONE|DEAD
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    dedupe_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=True)
    locked_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class FeatureFlag(Base):
    """Operational kill switches (§13.4 / §16.6).

    Values are stored lower-case strings: "true" or "false". Absent row means the configured
    default in `app.config` applies, so an instance can boot with the flag hard-off via env.
    """
    __tablename__ = "feature_flags"
    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text, nullable=True)
    updated_by: Mapped[str] = mapped_column(String(100), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AgentMandate(Base):
    """A single-use, hash-locked permission to execute an already-approved proposed action.

    The agent may only *propose*. A human approves, then the approval issues this mandate bound to
    the exact parameters that were shown to them. `execute_mandate` takes the id alone and re-reads
    everything from here: it recomputes the params hash, re-validates caps and the kill switch, and
    refuses if the row is not MANDATE_ISSUED. Nothing about the action can drift after approval.
    """
    __tablename__ = "agent_mandates"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    proposal_id: Mapped[str] = mapped_column(ForeignKey("proposed_actions.id"), unique=True)
    circle_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict] = mapped_column(JSON)                                    # frozen copy shown to the approver
    params_hash: Mapped[str] = mapped_column(String(64), index=True)              # sha256 of the canonical params
    cap_minor: Mapped[int] = mapped_column(BigInteger)                            # inclusive ceiling at execution time
    currency: Mapped[str] = mapped_column(String(3))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(30), default="MANDATE_ISSUED", index=True)
    issued_by: Mapped[str] = mapped_column(String(100))
    step_up: Mapped[dict] = mapped_column(JSON, nullable=True)                    # how the human proved presence
    idempotency_key: Mapped[str] = mapped_column(String(100), unique=True)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_by: Mapped[str] = mapped_column(String(100), nullable=True)
    outcome: Mapped[dict] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApiIdempotencyRow(Base):
    """API idempotency (authoritative copy; Redis is only a fast path)."""
    __tablename__ = "api_idempotency"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    actor_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSON, nullable=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ProposedActionRow(Base):
    """Proposed actions from agents; humans approve before anything executes."""
    __tablename__ = "proposed_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_id)
    circle_id: Mapped[str] = mapped_column(String(36), index=True)
    kind: Mapped[str] = mapped_column(String(50))
    params: Mapped[dict] = mapped_column(JSON)
    rationale: Mapped[str] = mapped_column(Text, nullable=True)
    state: Mapped[str] = mapped_column(String(20), default="PROPOSED")
    proposed_by: Mapped[str] = mapped_column(String(50))
    decided_by: Mapped[str] = mapped_column(String(36), nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserContact(Base):
    """Encrypted contact info for a user. PII lives here, not in the ledger.

    The payments adapter resolves a member's verified contact at the edge
    instead of using placeholder addresses (§10.10, gap #10).
    """
    __tablename__ = "user_contacts"
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)   # "email" | "phone"
    value: Mapped[str] = mapped_column(EncryptedString(255), nullable=False)  # contact value (encrypted at rest)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
