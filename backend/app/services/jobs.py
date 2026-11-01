"""Outbox relay and durable job queue (gaps #5 and #6).

The outbox row is written in the same transaction as the ledger event, so "committed to the ledger"
and "queued for projection" cannot disagree. The relay is what moves those rows into work that a
worker owns, and `jobs` is what survives a crash while that work is in flight.
"""
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import Job, OutboxRow


def _now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def backoff(attempts: int) -> int:
    """Exponential backoff in seconds: 5, 10, 20, 40, ... capped at an hour."""
    return min(5 * (2 ** max(0, attempts - 1)), 3600)


def enqueue(session: Session, *, type: str, payload: dict, circle_id: Optional[str] = None,
            run_at: Optional[datetime] = None, dedupe_key: Optional[str] = None) -> Optional[Job]:
    """Queue work. Returns the job, or None when `dedupe_key` is already queued (not an error)."""
    if dedupe_key is not None and session.scalar(
            select(Job.id).where(Job.dedupe_key == dedupe_key).limit(1)) is not None:
        return None                                   # already queued; leave the session untouched
    job = Job(type=type, payload=payload, circle_id=circle_id, run_at=run_at or _now(),
              dedupe_key=dedupe_key, status="PENDING")
    session.add(job)
    try:
        # flush so a genuine constraint violation (a bad payload, say) surfaces here rather than
        # being swallowed below; the pre-check above has already handled the duplicate-key case
        session.flush()
    except IntegrityError:
        session.rollback()
        raise
    return job


def relay_outbox(session: Session, limit: int = 500) -> int:
    """Publish unpublished outbox rows into the job queue and mark them published.

    One transaction per batch: a row is either published *and* queued, or neither. Nothing is
    acknowledged before it is durably queued, so a relay crash cannot drop an event.
    """
    rows = list(session.scalars(select(OutboxRow).where(OutboxRow.published_at.is_(None))
                                .order_by(OutboxRow.id).limit(limit).with_for_update(skip_locked=True)))
    for row in rows:
        enqueue(session, type=row.event_type, circle_id=row.payload.get("circle_id"),
                payload={"outbox_id": row.id, **row.payload}, dedupe_key=f"outbox:{row.id}")
        row.published_at = _now()
    session.commit()
    return len(rows)


def claim(session: Session, limit: int = 10, types: Optional[list] = None,
          visibility_timeout_seconds: int = 60) -> list:
    """Atomically take runnable jobs, giving each a visibility timeout.

    A job that is PENDING and due, or RUNNING with an elapsed timeout (the worker died mid-run), can
    be claimed. SKIP LOCKED keeps concurrent workers off the same rows.
    """
    now = _now()
    runnable = (Job.status == "PENDING") | ((Job.status == "RUNNING") & (Job.locked_until < now))
    stmt = select(Job).where(runnable, Job.run_at <= now).order_by(Job.run_at, Job.id).limit(limit)
    if types:
        stmt = stmt.where(Job.type.in_(types))
    rows = list(session.scalars(stmt.with_for_update(skip_locked=True)))
    for job in rows:
        job.status, job.locked_until = "RUNNING", now + timedelta(seconds=visibility_timeout_seconds)
    if rows:
        session.commit()
    return rows


def complete(session: Session, job: Job) -> str:
    # clear last_error: a job that finally succeeded should not still read as broken to an operator
    job.status, job.attempts, job.locked_until, job.last_error = "DONE", job.attempts + 1, None, None
    session.commit()
    return "DONE"


def fail(session: Session, job: Job, error: str, max_attempts: int = 5) -> str:
    """Record a failure: back off and retry, or dead-letter once the ceiling is reached."""
    attempts = job.attempts + 1
    job.attempts, job.last_error, job.locked_until = attempts, (error or "")[:2000], None
    if attempts >= max_attempts:
        job.status, job.run_at = "DEAD", _now()
    else:
        job.status, job.run_at = "PENDING", _now() + timedelta(seconds=backoff(attempts))
    session.commit()
    return job.status


def dispatch(session: Session, job: Job, handlers: dict) -> str:
    """Run one job to completion under the retry/dead-letter policy."""
    handler: Optional[Callable[[Session, dict], None]] = handlers.get(job.type)
    if handler is None:
        # an event type with no consumer yet is acknowledged, not dead-lettered; the outbox row keeps it
        return complete(session, job)
    try:
        handler(session, job.payload)
        return complete(session, job)
    except Exception as exc:                            # noqa: BLE001 - one bad job must not stall the queue
        session.rollback()
        return fail(session, job, f"{type(exc).__name__}: {exc}")


def run_once(session: Session, handlers: dict, limit: int = 10,
             types: Optional[list] = None) -> dict:
    """Claim a batch and dispatch it. Returns a summary for logs and tests."""
    jobs = claim(session, limit=limit, types=types)
    outcomes = [{"id": j.id, "type": j.type, "status": dispatch(session, j, handlers)} for j in jobs]
    return {"claimed": len(jobs), "outcomes": outcomes}


def dead_letter_count(session: Session) -> int:
    from sqlalchemy import func
    return session.scalar(select(func.count(Job.id)).where(Job.status == "DEAD")) or 0
