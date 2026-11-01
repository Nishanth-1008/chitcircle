"""Gaps #3/#4/#5/#6: durable ingest, provider dedupe, outbox relay and the job queue.

The core property under test is *no lost event*: a callback is persisted before it is applied, so a
failure between the two phases leaves a row that the worker finishes later.
"""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import db
from app.models import LedgerEventRow, ProviderEventRow
from app.services import financial_service as svc
from .test_api_integration import env, setup_circle, collect, to_settlement, pay


def _events(session, **filters):
    stmt = select(ProviderEventRow)
    for k, v in filters.items():
        stmt = stmt.where(getattr(ProviderEventRow, k) == v)
    return list(session.scalars(stmt))


def _session():
    return db.SessionLocal()


# -------------------------------------------------------------------------- durable ingest
def test_webhook_is_persisted_before_it_is_applied(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    collect(c, circle, cy, st)
    m = circle["members"][0]["id"]
    assert pay(c, cy["id"], m, 100_000, "t-durable", apply_phase_b=False).status_code == 200

    with _session() as s:
        row = _events(s, provider_txn_id="t-durable")[0]
        assert row.state == "RECEIVED"            # phase A: persisted, not yet applied
        assert row.signature_ok is True
        assert row.processed_at is None           # phase B has not run yet
        assert row.raw_body and "t-durable" in row.raw_body   # exact body, replayable

    # Phase B: the worker applies the durable row.
    with _session() as s:
        summary = svc.process_pending_provider_events(s)
    assert summary["scanned"] >= 1                # t-durable plus any from collect()
    assert summary["failed"] == []

    with _session() as s:
        row = _events(s, provider_txn_id="t-durable")[0]
        assert row.state == "PROCESSED"
        assert row.processed_at is not None
        # phase B resolved and denormalised the fields reconciliation needs
        assert row.cycle_id == cy["id"] and row.member_id == m and row.amount == 100_000


def test_parked_event_is_finished_by_the_worker(env):
    """A callback that cannot be applied yet is retried, not dropped (the crash-safety guarantee)."""
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    m = circle["members"][0]["id"]
    payload = dict(provider_txn_id="t-parked", kind="PAYMENT", status="COMPLETED",
                   amount=100_000, currency="INR", cycle_id=cy["id"], member_id=m)

    # simulate the crash window: ingest succeeded, apply never ran
    with _session() as s:
        ingested = svc._ingest_provider_event(s, payload, raw_body="{}", signature_ok=True)
        assert ingested["duplicate"] is False

    with _session() as s:
        rows = _events(s, provider_txn_id="t-parked")
        assert len(rows) == 1 and rows[0].state == "RECEIVED" and rows[0].processed_at is None

    # the worker picks it up and applies it
    with _session() as s:
        summary = svc.process_pending_provider_events(s)
    assert summary["scanned"] == 1 and summary["failed"] == []
    assert summary["applied"][0]["duplicate"] is False

    with _session() as s:
        row = _events(s, provider_txn_id="t-parked")[0]
        assert row.state == "PROCESSED" and row.processed_at is not None
        assert row.member_id == m and row.amount == 100_000
        assert s.scalar(select(LedgerEventRow).where(LedgerEventRow.idempotency_key == "provider:t-parked"))


def test_cycle_lock_serialises_concurrent_provider_events(env):
    """Two callbacks for the same cycle applied back-to-back never double-count."""
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    m = circle["members"][0]["id"]

    def confirmed_minor():
        with _session() as s:
            return sum(e.amount for e in s.scalars(select(LedgerEventRow).where(
                LedgerEventRow.cycle_id == cy["id"], LedgerEventRow.event_type == "PAYMENT_CONFIRMED")))

    before = confirmed_minor()
    for txn in ("t-serial-1", "t-serial-2"):
        assert pay(c, cy["id"], m, 25_000, txn).json()["duplicate"] is False

    # Apply the persisted events asynchronously (phase B).
    with _session() as s:
        svc.process_pending_provider_events(s)

    assert confirmed_minor() == before + 50_000


# -------------------------------------------------------------------------- dedupe
def test_ingress_dedupe_uses_event_id_when_present(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    collect(c, circle, cy, st)
    m = circle["members"][0]["id"]
    body = dict(provider_txn_id="t-ev", kind="PAYMENT", status="COMPLETED",
                amount=10_000, currency="INR", cycle_id=cy["id"], member_id=m, event_id="evt-1")
    first = svc.apply_provider_event(_session(), body, raw_body="{}", signature_ok=True)
    second = svc.apply_provider_event(_session(), body, raw_body="{}", signature_ok=True)
    assert first["duplicate"] is False and second["duplicate"] is True


def test_ledger_dedupe_ignores_a_second_event_for_the_same_txn(env):
    """A distinct event id pointing at an already-counted transaction changes nothing."""
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    m = circle["members"][0]["id"]
    for event_id in ("evt-a", "evt-b"):
        svc.apply_provider_event(_session(), dict(
            provider_txn_id="t-same", kind="PAYMENT", status="COMPLETED", amount=40_000,
            currency="INR", cycle_id=cy["id"], member_id=m, event_id=event_id),
            raw_body="{}", signature_ok=True)

    with _session() as s:
        confirmed = list(s.scalars(select(LedgerEventRow).where(
            LedgerEventRow.cycle_id == cy["id"], LedgerEventRow.event_type == "PAYMENT_CONFIRMED",
            LedgerEventRow.provider_ref == "t-same")))
        assert len(confirmed) == 1 and confirmed[0].amount == 40_000


def test_permanent_validation_error_is_rejected_not_retried(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    m = circle["members"][0]["id"]
    with pytest.raises(Exception) as exc:
        svc.apply_provider_event(_session(), dict(
            provider_txn_id="t-badcur", kind="PAYMENT", status="COMPLETED", amount=1,
            currency="USD", cycle_id=cy["id"], member_id=m), raw_body="{}", signature_ok=True)
    assert "CURRENCY_MISMATCH" in str(exc.value) or "currency" in str(exc.value).lower()

    with _session() as s:
        row = _events(s, provider_txn_id="t-badcur")[0]
        assert row.state == "REJECTED" and row.last_error
        # the worker must not touch it again
        summary = svc.process_pending_provider_events(s)
    assert summary["scanned"] == 0


def test_parked_event_dead_letters_after_the_attempt_ceiling(env):
    """Retries are backoff-gated: the worker cannot burn the budget in a single tight loop."""
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    m = circle["members"][0]["id"]
    with _session() as s:
        svc._ingest_provider_event(s, dict(provider_txn_id="t-doomed", kind="PAYMENT",
                                           status="COMPLETED", amount=10_000, currency="INR",
                                           cycle_id=cy["id"], member_id="not-a-member"),
                                   raw_body="{}", signature_ok=True)

    for _ in range(50):
        with _session() as s:
            svc.process_pending_provider_events(s)
        with _session() as s:
            row = _events(s, provider_txn_id="t-doomed")[0]
            # many passes, but only the first is eligible: the rest are gated by exponential backoff
            assert row.attempts == 1, row.attempts
            assert row.state == "PARKED"

    # simulate the passage of time so each subsequent retry becomes eligible
    for _ in range(svc.PROVIDER_MAX_ATTEMPTS):
        with _session() as s:
            svc.process_pending_provider_events(s)
        with _session() as s:
            row = _events(s, provider_txn_id="t-doomed")[0]
            row.last_attempt_at = svc.as_utc(row.last_attempt_at) - timedelta(
                seconds=svc.provider_backoff(row.attempts) + 1)
            s.commit()

    with _session() as s:
        row = _events(s, provider_txn_id="t-doomed")[0]
        assert row.state == "DEAD"
        assert row.attempts == svc.PROVIDER_MAX_ATTEMPTS
