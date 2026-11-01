"""Gaps #5/#6: the outbox relay and the durable job queue.

The properties under test are the ones that decide whether an event can be lost: relay idempotence,
at-most-one-owner claim semantics, and a crash mid-run decaying into backoff then a dead letter.
"""
import os
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import db
from app.models import Job, OutboxRow
from app.services import jobs as J
from .test_api_integration import env, setup_circle, collect, to_settlement, pay


def _session():
    return db.SessionLocal()


def _outbox_rows(session, **filters):
    stmt = select(OutboxRow)
    for k, v in filters.items():
        stmt = stmt.where(getattr(OutboxRow, k) == v)
    return list(session.scalars(stmt))


# -------------------------------------------------------------------------- outbox relay
def test_outbox_row_is_written_in_the_ledger_transaction(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    collect(c, circle, cy, st)

    with _session() as s:
        rows = _outbox_rows(s, event_type="ledger.PAYMENT_CONFIRMED")
        assert len(rows) >= 4
        assert all(r.published_at is None for r in rows)      # nothing published before the relay runs
        assert all(r.payload.get("event_id") and r.payload.get("journal") is not None for r in rows)


def test_relay_publishes_every_row_exactly_once(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    collect(c, circle, cy, st)

    with _session() as s:
        first = J.relay_outbox(s)
        assert first >= 4

    with _session() as s:
        assert all(r.published_at is not None for r in _outbox_rows(s))
        assert J.relay_outbox(s) == 0                        # a second pass finds nothing

    with _session() as s:
        # every relayed outbox row yields exactly one job; a second relay cannot add another
        rows = _outbox_rows(s)
        assert rows and all(r.published_at is not None for r in rows)
        keys = [j.dedupe_key for j in s.scalars(select(Job))]
        assert len(keys) == len(set(keys))                   # dedupe keys are unique
        for r in rows:
            assert s.query(Job).filter_by(dedupe_key=f"outbox:{r.id}").count() == 1


def test_relay_enqueue_is_idempotent_on_duplicate_key(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    collect(c, circle, cy, st)
    with _session() as s:
        row = _outbox_rows(s, event_type="ledger.PAYMENT_CONFIRMED")[0]
        payload = {"outbox_id": row.id, **row.payload}
        key = f"outbox-test:{row.id}-{os.urandom(8).hex()}"
        assert J.enqueue(s, type=row.event_type, payload=payload, dedupe_key=key) is not None
        # the key is now taken, so a second enqueue reports "already queued" instead of raising
        assert J.enqueue(s, type=row.event_type, payload=payload, dedupe_key=key) is None


# -------------------------------------------------------------------------- job queue
def test_unknown_event_type_is_acknowledged_not_dead_lettered(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    collect(c, circle, cy, st)
    with _session() as s:
        J.relay_outbox(s)
        summary = J.run_once(s, handlers={})                  # no consumers shipped in Phase 1
    assert summary["claimed"] >= 1
    assert all(o["status"] == "DONE" for o in summary["outcomes"])
    with _session() as s:
        assert J.dead_letter_count(s) == 0


def test_failing_handler_backs_off_then_dead_letters(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)

    def boom(session, payload):
        raise RuntimeError("consumer is down")

    with _session() as s:
        job = J.enqueue(s, type="ledger.CONTRIBUTION_DUE", payload={"x": 1}, dedupe_key=f"k1-{os.urandom(8).hex()}")
        s.commit()
        job_id = job.id

    for _ in range(10):
        with _session() as s:
            J.run_once(s, handlers={"ledger.CONTRIBUTION_DUE": boom})
        with _session() as s:
            j = s.get(Job, job_id)
            if j.status == "DONE":
                break
            # each failure schedules a later retry, so pull the next attempt forward
            j.run_at = J.as_utc(j.run_at) - timedelta(seconds=J.backoff(j.attempts) + 1)
            s.commit()

    with _session() as s:
        j = s.get(Job, job_id)
        assert j.status == "DEAD"
        assert j.attempts == 5
        assert "consumer is down" in (j.last_error or "")


def test_recovered_handler_succeeds_on_a_later_attempt(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    calls = {"n": 0}

    def flaky(session, payload):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient")

    with _session() as s:
        job = J.enqueue(s, type="ledger.CONTRIBUTION_DUE", payload={}, dedupe_key=f"k2-{os.urandom(8).hex()}")
        s.commit()
        job_id = job.id

    for _ in range(3):
        with _session() as s:
            J.run_once(s, handlers={"ledger.CONTRIBUTION_DUE": flaky})
        with _session() as s:
            j = s.get(Job, job_id)
            if j.status == "DONE":
                break
            j.run_at = J.as_utc(j.run_at) - timedelta(seconds=J.backoff(j.attempts) + 1)
            s.commit()

    with _session() as s:
        j = s.get(Job, job_id)
        assert j.status == "DONE" and calls["n"] == 2
        assert j.last_error is None


def test_claim_excludes_jobs_that_are_not_yet_due(env):
    c = env
    circle, cy, st = to_settlement(c, n=4, V=400_000)
    from datetime import datetime, timezone
    with _session() as s:
        J.enqueue(s, type="ledger.CONTRIBUTION_DUE", payload={}, dedupe_key=f"future-{os.urandom(8).hex()}",
                  run_at=datetime.now(timezone.utc) + timedelta(hours=1))
        s.commit()

    with _session() as s:
        assert J.claim(s, limit=10) == []


def test_job_backoff_is_exponential_and_capped():
    assert [J.backoff(n) for n in (1, 2, 3, 4)] == [5, 10, 20, 40]
    assert J.backoff(20) == 3600


def test_provider_backoff_is_exponential_and_capped():
    from app.services import financial_service as svc
    assert [svc.provider_backoff(n) for n in (1, 2, 3, 4)] == [5, 10, 20, 40]
    assert svc.provider_backoff(20) == 3600
