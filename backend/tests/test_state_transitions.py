import pytest

from financial_engine.states import CycleState as S, InvalidTransitionError, can_transition, ensure_transition

HAPPY = [S.DRAFT, S.OPEN, S.COLLECTIONS_IN_PROGRESS, S.AUCTION_OPEN, S.AUCTION_CLOSED, S.SETTLEMENT_CALCULATED,
         S.AWAITING_APPROVAL, S.APPROVED, S.PAYOUT_PENDING, S.PAYOUT_SUBMITTED, S.PAYOUT_CONFIRMED,
         S.RECONCILIATION_PENDING, S.FINALIZED]


def test_happy_path():
    for a, b in zip(HAPPY, HAPPY[1:]):
        ensure_transition(a, b)


def test_skipping_states_is_rejected():
    for a, b in [(S.DRAFT, S.APPROVED), (S.AWAITING_APPROVAL, S.PAYOUT_PENDING),
                 (S.PAYOUT_SUBMITTED, S.FINALIZED), (S.AUCTION_CLOSED, S.APPROVED), (S.APPROVED, S.OPEN)]:
        with pytest.raises(InvalidTransitionError):
            ensure_transition(a, b)


def test_finalized_is_terminal():
    for t in S:
        assert not can_transition(S.FINALIZED, t, S.APPROVED)


def test_exception_states_resume_only_to_recorded_state():
    assert can_transition(S.APPROVED, S.ON_HOLD)
    assert can_transition(S.ON_HOLD, S.APPROVED, resume_from=S.APPROVED)
    assert not can_transition(S.ON_HOLD, S.PAYOUT_PENDING, resume_from=S.APPROVED)
    assert not can_transition(S.DISPUTED, S.FINALIZED, resume_from=S.RECONCILIATION_PENDING)
    assert can_transition(S.DISPUTED, S.ON_HOLD, resume_from=S.APPROVED)
    assert not can_transition(S.FAILED, S.APPROVED)
