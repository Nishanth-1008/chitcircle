"""Append-only ledger events and balanced double-entry journals.

The chart of accounts below is PROPOSED; the full mapping is a reserved decision in the spec.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from .errors import FinancialEngineError
from .money import Money


class LedgerError(FinancialEngineError):
    pass


class EventType(str, Enum):
    CONTRIBUTION_DUE = "CONTRIBUTION_DUE"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    DIVIDEND_CREDITED = "DIVIDEND_CREDITED"
    COMMISSION_ALLOCATED = "COMMISSION_ALLOCATED"
    PAYOUT_REQUESTED = "PAYOUT_REQUESTED"
    PAYOUT_CONFIRMED = "PAYOUT_CONFIRMED"
    REFUND_CONFIRMED = "REFUND_CONFIRMED"
    ADJUSTMENT_RECORDED = "ADJUSTMENT_RECORDED"
    SETTLEMENT_FINALIZED = "SETTLEMENT_FINALIZED"
    DISPUTE_OPENED = "DISPUTE_OPENED"
    DISPUTE_RESOLVED = "DISPUTE_RESOLVED"


POOL = "CIRCLE_POOL"
CASH = "CASH_CLEARING"
WINNER_PAYABLE = "WINNER_PAYABLE"
COMMISSION_PAYABLE = "ORGANIZER_COMMISSION_PAYABLE"
ORGANIZER_ROUNDING = "ORGANIZER_ROUNDING_PAYABLE"
RESERVE = "CIRCLE_RESERVE"


def receivable(member_id: str) -> str:
    return f"MEMBER_RECEIVABLE:{member_id}"


@dataclass(frozen=True)
class Posting:
    account: str
    debit: int = 0
    credit: int = 0


@dataclass(frozen=True)
class Journal:
    currency: str
    postings: tuple

    @property
    def total_debits(self) -> int:
        return sum(p.debit for p in self.postings)

    @property
    def total_credits(self) -> int:
        return sum(p.credit for p in self.postings)

    @property
    def is_balanced(self) -> bool:
        return self.total_debits == self.total_credits and all(
            p.debit >= 0 and p.credit >= 0 for p in self.postings)

    def assert_balanced(self) -> None:
        if not self.is_balanced:
            raise LedgerError(f"unbalanced journal: debits {self.total_debits} != credits {self.total_credits}")

    def mirrored(self) -> "Journal":
        return Journal(self.currency, tuple(Posting(p.account, p.credit, p.debit) for p in self.postings))

    def to_dict(self) -> dict:
        return {"currency": self.currency,
                "postings": [{"account": p.account, "debit": p.debit, "credit": p.credit} for p in self.postings]}

    @classmethod
    def from_dict(cls, d: dict) -> "Journal":
        return cls(d["currency"], tuple(Posting(p["account"], p["debit"], p["credit"]) for p in d["postings"]))


def _j(amount: Money, debit: str, credit: str) -> Journal:
    return Journal(amount.currency, (Posting(debit, debit=amount.minor), Posting(credit, credit=amount.minor)))


def contribution_due_journal(member_id: str, amount: Money) -> Journal:
    return _j(amount, receivable(member_id), POOL)


def payment_confirmed_journal(member_id: str, amount: Money) -> Journal:
    return _j(amount, CASH, receivable(member_id))


def refund_confirmed_journal(member_id: str, amount: Money) -> Journal:
    return _j(amount, receivable(member_id), CASH)


def payout_requested_journal(amount: Money) -> Journal:
    return _j(amount, POOL, WINNER_PAYABLE)


def payout_confirmed_journal(amount: Money) -> Journal:
    return _j(amount, WINNER_PAYABLE, CASH)


@dataclass(frozen=True)
class JournalSpec:
    event_type: EventType
    member_id: Optional[str]
    amount: Money
    journal: Journal
    reason: str


def settlement_journals(s) -> list:
    """Events produced when a settlement is calculated (dividends, commission, rounding)."""
    out = []
    for m in s.member_order:
        d = s.dividends[m]
        if d.minor > 0:
            out.append(JournalSpec(EventType.DIVIDEND_CREDITED, m, d,
                                   _j(d, POOL, receivable(m)), "dividend credit (not cash)"))
    if s.commission.minor > 0:
        out.append(JournalSpec(EventType.COMMISSION_ALLOCATED, None, s.commission,
                               _j(s.commission, POOL, COMMISSION_PAYABLE), "organizer commission"))
    if s.rounding_remainder.minor > 0:
        acct = ORGANIZER_ROUNDING if s.remainder_destination == "ORGANIZER" else RESERVE
        out.append(JournalSpec(EventType.ADJUSTMENT_RECORDED, None, s.rounding_remainder,
                               _j(s.rounding_remainder, POOL, acct), "rounding remainder of dividend split"))
    return out


@dataclass(frozen=True)
class LedgerEvent:
    event_id: str
    circle_id: str
    event_type: EventType
    amount: Money
    timestamp: datetime
    actor: str
    ruleset_version: int
    cycle_id: Optional[str] = None
    member_id: Optional[str] = None
    settlement_id: Optional[str] = None
    provider_ref: Optional[str] = None
    idempotency_key: Optional[str] = None
    reverses_event_id: Optional[str] = None
    reason: Optional[str] = None
    approval: Optional[dict] = None
    journal: Optional[Journal] = None


class Ledger:
    """In-memory append-only ledger (reference implementation used by tests and the service layer's rules)."""

    def __init__(self) -> None:
        self._events: list = []
        self._by_key: dict = {}

    @property
    def events(self) -> tuple:
        return tuple(self._events)

    def append(self, event: LedgerEvent) -> LedgerEvent:
        if event.journal is not None:
            event.journal.assert_balanced()
        if event.idempotency_key:
            existing = self._by_key.get(event.idempotency_key)
            if existing is not None:
                return existing                      # duplicate retry: no new financial effect
            self._by_key[event.idempotency_key] = event
        self._events.append(event)
        return event

    def reverse(self, event_id: str, actor: str, at: datetime, reason: str) -> LedgerEvent:
        orig = next((e for e in self._events if e.event_id == event_id), None)
        if orig is None:
            raise LedgerError("unknown event")
        if any(e.reverses_event_id == event_id for e in self._events):
            raise LedgerError("event already reversed")
        rev = LedgerEvent(
            event_id=str(uuid.uuid4()), circle_id=orig.circle_id, event_type=EventType.ADJUSTMENT_RECORDED,
            amount=-orig.amount, timestamp=at, actor=actor, ruleset_version=orig.ruleset_version,
            cycle_id=orig.cycle_id, member_id=orig.member_id, settlement_id=orig.settlement_id,
            reverses_event_id=event_id, reason=reason,
            journal=orig.journal.mirrored() if orig.journal else None,
            idempotency_key=f"reversal:{event_id}")
        return self.append(rev)

    def credit_balance(self, account: str) -> int:
        """credits - debits for an account across all events."""
        return sum(p.credit - p.debit for e in self._events if e.journal for p in e.journal.postings
                   if p.account == account)
