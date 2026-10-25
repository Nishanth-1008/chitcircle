import uuid
from datetime import datetime, timezone

import pytest

from financial_engine import ledger as L
from financial_engine.ledger import EventType, Journal, Ledger, LedgerError, LedgerEvent, Posting
from financial_engine.money import Money
from financial_engine.rules import PayoutMethod
from financial_engine.settlement import calculate_settlement
from .conftest import make_rules, members

NOW = datetime(2026, 11, 1, tzinfo=timezone.utc)


def ev(typ, amount, journal, key=None):
    return LedgerEvent(str(uuid.uuid4()), "c1", typ, amount, NOW, "system", 1, journal=journal, idempotency_key=key)


def test_unbalanced_journal_rejected():
    bad = Journal("INR", (Posting("A", debit=10), Posting("B", credit=9)))
    with pytest.raises(LedgerError):
        Ledger().append(ev(EventType.ADJUSTMENT_RECORDED, Money(10, "INR"), bad))


def test_idempotent_append_and_reversal():
    led = Ledger()
    j = L.payment_confirmed_journal("m1", Money(100, "INR"))
    a = led.append(ev(EventType.PAYMENT_CONFIRMED, Money(100, "INR"), j, "k1"))
    b = led.append(ev(EventType.PAYMENT_CONFIRMED, Money(100, "INR"), j, "k1"))
    assert a is b and len(led.events) == 1
    rev = led.reverse(a.event_id, "organizer", NOW, "wrong member")
    assert rev.reverses_event_id == a.event_id and rev.amount.minor == -100 and len(led.events) == 2
    assert led.credit_balance(L.CASH) == 0                       # original preserved, correction nets to zero
    with pytest.raises(LedgerError):
        led.reverse(a.event_id, "organizer", NOW, "again")


def test_full_cycle_pool_nets_to_zero():
    r = make_rules()
    s = calculate_settlement(r, "cy1", members(), "m03", PayoutMethod.SEALED_BID_AUCTION, discount=Money(1_200_000, "INR"))
    led = Ledger()
    for m in members():
        led.append(ev(EventType.CONTRIBUTION_DUE, s.contributions[m], L.contribution_due_journal(m, s.contributions[m])))
    for spec in L.settlement_journals(s):
        led.append(ev(spec.event_type, spec.amount, spec.journal))
    led.append(ev(EventType.PAYOUT_REQUESTED, s.winner_payout, L.payout_requested_journal(s.winner_payout)))
    assert led.credit_balance(L.POOL) == 0
    assert led.credit_balance(L.WINNER_PAYABLE) == 8_800_000
    assert led.credit_balance(L.COMMISSION_PAYABLE) == 500_000
    # dividend credit reduces the receivable but is not cash
    assert -led.credit_balance(L.receivable("m01")) == 465_000
    assert led.credit_balance(L.CASH) == 0
