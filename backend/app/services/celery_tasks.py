"""Celery tasks: execute jobs from the Postgres durable queue (gap #7).

The Postgres ``jobs`` table is the durable source of truth. Celery workers
claim due jobs, execute them via registered handlers, and mark them complete
or dead-lettered.
"""
from datetime import datetime, timedelta, timezone

from app import db
from app.services import jobs as J
from app.services.celery_app import celery_app

# Job handler registry: type -> handler(session, payload) -> None.
# Services register handlers for the job types they produce.
_HANDLERS: dict = {}


def register_handler(job_type: str, handler) -> None:
    """Register a Celery handler for a job type."""
    _HANDLERS[job_type] = handler


@celery_app.task(bind=True, max_retries=3, acks_late=True)
def process_job(self, job_id: int) -> dict:
    """Claim and run a single job from the Postgres queue."""
    session = db.SessionLocal()
    try:
        job = session.get(J.Job, job_id)
        if job is None:
            return {"status": "not_found"}
        if job.status != "PENDING":
            return {"status": job.status}

        now = datetime.now(timezone.utc)
        job.status = "RUNNING"
        job.locked_until = now + timedelta(seconds=60)
        session.commit()

        handler = _HANDLERS.get(job.type)
        if handler is None:
            # No consumer for this event type: acknowledge, don't dead-letter.
            J.complete(session, job)
            return {"status": "no_handler"}

        try:
            handler(session, job.payload)
            return J.complete(session, job)
        except Exception as exc:  # noqa: BLE001 - one bad job must not stall the worker
            session.rollback()
            status = J.fail(session, job, f"{type(exc).__name__}: {exc}")
            if status == "DEAD":
                return {"status": "dead"}
            raise self.retry(exc=exc, countdown=J.backoff(job.attempts))
    finally:
        session.close()


@celery_app.task
def run_due_jobs(limit: int = 10, types: list | None = None) -> dict:
    """Claim a batch of due jobs and dispatch each to process_job."""
    session = db.SessionLocal()
    try:
        claimed = J.claim(session, limit=limit, types=types)
        results = []
        for job in claimed:
            result = process_job.delay(job.id)
            results.append({"id": job.id, "type": job.type, "task_id": result.id})
        return {"claimed": len(claimed), "results": results}
    finally:
        session.close()
