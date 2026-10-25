"""Cycle state machine."""
from __future__ import annotations

from enum import Enum
from typing import Optional

from .errors import FinancialEngineError


class InvalidTransitionError(FinancialEngineError):
    pass


class CycleState(str, Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    COLLECTIONS_IN_PROGRESS = "COLLECTIONS_IN_PROGRESS"
    AUCTION_OPEN = "AUCTION_OPEN"
    AUCTION_CLOSED = "AUCTION_CLOSED"
    SETTLEMENT_CALCULATED = "SETTLEMENT_CALCULATED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    PAYOUT_PENDING = "PAYOUT_PENDING"
    PAYOUT_SUBMITTED = "PAYOUT_SUBMITTED"
    PAYOUT_CONFIRMED = "PAYOUT_CONFIRMED"
    RECONCILIATION_PENDING = "RECONCILIATION_PENDING"
    FINALIZED = "FINALIZED"
    ON_HOLD = "ON_HOLD"
    FAILED = "FAILED"
    DISPUTED = "DISPUTED"


S = CycleState
EXCEPTION_STATES = frozenset({S.ON_HOLD, S.FAILED, S.DISPUTED})

FORWARD = {
    S.DRAFT: {S.OPEN},
    S.OPEN: {S.COLLECTIONS_IN_PROGRESS},
    S.COLLECTIONS_IN_PROGRESS: {S.AUCTION_OPEN, S.SETTLEMENT_CALCULATED},
    S.AUCTION_OPEN: {S.AUCTION_CLOSED},
    S.AUCTION_CLOSED: {S.SETTLEMENT_CALCULATED},
    S.SETTLEMENT_CALCULATED: {S.AWAITING_APPROVAL},
    S.AWAITING_APPROVAL: {S.APPROVED},
    S.APPROVED: {S.PAYOUT_PENDING},
    S.PAYOUT_PENDING: {S.PAYOUT_SUBMITTED},
    S.PAYOUT_SUBMITTED: {S.PAYOUT_CONFIRMED},
    S.PAYOUT_CONFIRMED: {S.RECONCILIATION_PENDING},
    S.RECONCILIATION_PENDING: {S.FINALIZED},
    S.FINALIZED: set(),
}


def can_transition(current: CycleState, target: CycleState, resume_from: Optional[CycleState] = None) -> bool:
    if current == S.FINALIZED:
        return False
    if current in EXCEPTION_STATES:
        # leave an exception state only by moving to another exception state or resuming
        return target in EXCEPTION_STATES - {current} or (resume_from is not None and target == resume_from)
    if target in EXCEPTION_STATES:
        return True
    return target in FORWARD[current]


def ensure_transition(current: CycleState, target: CycleState, resume_from: Optional[CycleState] = None) -> None:
    if not can_transition(current, target, resume_from):
        raise InvalidTransitionError(f"transition {current.value} -> {target.value} is not permitted")
