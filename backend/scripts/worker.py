"""Worker entry point: drains the outbox relay, the provider-event backlog and due jobs.

Phase 1 keeps this deliberately simple — a loop in a dedicated process (Render Worker / a cron tick),
no Celery and no Redis dependency, because the queue already lives in Postgres and survives restarts
for free. Celery is Phase 3 (see `docs/11-testing.md`).

Usage:
    python -m scripts.worker            # loop until SIGTERM
    python -m scripts.worker --once     # single pass (cron-friendly, used by tests)
"""
from __future__ import annotations

import argparse
import logging
import signal
import time

from app import db
from app.services import financial_service as svc
from app.services import jobs as J

log = logging.getLogger("chitcircle.worker")

# ledger.* events are fan-out for projections and notifications. Phase 1 ships no consumer for them,
# so they are acknowledged rather than dead-lettered; the row keeps the event for audit.
HANDLERS = {}


def tick(session, handlers=HANDLERS) -> dict:
    """One full pass. Safe to run repeatedly and concurrently."""
    provider = svc.process_pending_provider_events(session)
    relayed = J.relay_outbox(session)
    queue = J.run_once(session, handlers)
    return {"provider": provider, "relayed": relayed, "queue": queue}


def main() -> int:
    parser = argparse.ArgumentParser(description="ChitCircle worker")
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    parser.add_argument("--interval", type=float, default=2.0, help="seconds between passes")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    db.init_db()
    stopping = {"flag": False}

    def _stop(*_):
        stopping["flag"] = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while True:
        with db.SessionLocal() as session:
            try:
                summary = tick(session)
                if summary["provider"]["scanned"] or summary["relayed"] or summary["queue"]["claimed"]:
                    log.info("tick %s", summary)
            except Exception:                                # noqa: BLE001 - the loop must survive a bad pass
                log.exception("worker pass failed")
                session.rollback()
        if args.once or stopping["flag"]:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
