"""Scheduler: advisory-lock leadership + scheduled job enqueuing.

Only one scheduler instance holds the advisory lock at a time (PostgreSQL
``pg_try_advisory_lock``; SQLite assumes a single instance). On each tick it
enqueues any scheduled jobs that are due; the worker then picks them up via
``jobs.run_once``.

Phase 1 ships the lock + loop infrastructure with no recurring jobs registered.
Scheduled tasks (nightly invariant check, reminders, etc.) are added in Phase 2/3.

Usage:
    python -m scripts.scheduler          # loop until SIGTERM
    python -m scripts.scheduler --once   # single pass
"""
from __future__ import annotations

import argparse
import logging
import signal
import time

from sqlalchemy import text

from app import db
from app.services import jobs as J, money_alerts

log = logging.getLogger("chitcircle.scheduler")

# Advisory lock key for scheduler leadership (PostgreSQL only).
SCHEDULER_LOCK_KEY = 0x43484954  # "CHIT"

# Scheduled task registry: (name, interval_seconds, callback).
# Phase 1 ships the lock + loop infrastructure with no recurring jobs registered.
# Scheduled tasks (nightly invariant check, provider reconciliation, dead-letter reaper) are
# registered below (gap #6).
_SCHEDULED_TASKS: list[dict] = []


def _invariant_check(session) -> None:
    """Nightly invariant check: enqueue a job to verify ledger/obligation consistency."""
    J.enqueue(session, type="invariant_check", payload={})


def _provider_reconciliation(session) -> None:
    """Nightly provider reconciliation: enqueue a job to sync with PayPal."""
    J.enqueue(session, type="provider_reconciliation", payload={})


def _dead_letter_reaper(session) -> None:
    """Hourly dead-letter reaper: enqueue a job when DEAD jobs exist."""
    dead = J.dead_letter_count(session)
    if dead:
        J.enqueue(session, type="dead_letter_reaper",
                  payload={"dead_count": dead})


# Register recurring schedules (gap #6).


def register_schedule(name: str, interval_seconds: float, callback) -> None:
    """Register a recurring task. ``callback`` receives a SQLAlchemy session."""
    _SCHEDULED_TASKS.append(
        {"name": name, "interval": interval_seconds, "callback": callback, "last_run": None}
    )


register_schedule("invariant_check", 86400.0, _invariant_check)            # nightly
register_schedule("provider_reconciliation", 86400.0, _provider_reconciliation)  # nightly
register_schedule("dead_letter_reaper", 3600.0, _dead_letter_reaper)       # hourly
register_schedule("ledger_imbalance", 300.0, money_alerts.check_ledger_imbalance)  # every 5 min
register_schedule("dead_letter_spike", 300.0, money_alerts.check_dead_letter_spike)  # every 5 min


def _try_acquire_lock(session) -> bool:
    """Try to acquire the scheduler advisory lock. True if we are the leader."""
    try:
        result = session.execute(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": SCHEDULER_LOCK_KEY}
        )
        return bool(result.scalar())
    except Exception:
        # SQLite or other DB without advisory locks: single instance assumed.
        return True


def _release_lock(session) -> None:
    """Release the scheduler advisory lock."""
    try:
        session.execute(
            text("SELECT pg_advisory_unlock(:key)"), {"key": SCHEDULER_LOCK_KEY}
        )
    except Exception:
        pass


def tick(session) -> dict:
    """One scheduler pass. Enqueues any scheduled jobs that are due.

    Returns a summary dict for logging.
    """
    now = time.time()
    enqueued = 0
    for task in _SCHEDULED_TASKS:
        last = task["last_run"]
        if last is None or now - last >= task["interval"]:
            try:
                task["callback"](session)
                session.commit()
                task["last_run"] = now
                enqueued += 1
            except Exception:  # noqa: BLE001 - one bad task must not stall the scheduler
                session.rollback()
                log.exception("scheduled task %s failed", task["name"])
    return {"enqueued": enqueued}


def main() -> int:
    parser = argparse.ArgumentParser(description="ChitCircle scheduler")
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    parser.add_argument("--interval", type=float, default=30.0, help="seconds between passes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_db()
    stopping = {"flag": False}

    def _stop(*_):
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    session = db.SessionLocal()
    try:
        if not _try_acquire_lock(session):
            log.info("scheduler advisory lock held by another instance; exiting")
            return 1

        while True:
            try:
                summary = tick(session)
                if summary["enqueued"]:
                    log.info("scheduler tick %s", summary)
            except Exception:                                # noqa: BLE001 - loop must survive
                log.exception("scheduler pass failed")
                session.rollback()

            if args.once or stopping["flag"]:
                return 0
            time.sleep(args.interval)
    finally:
        _release_lock(session)
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
