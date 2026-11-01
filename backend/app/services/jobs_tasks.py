"""Celery tasks that dispatch durable Postgres jobs.

The Postgres `Job` table (app/services/jobs.py) stays the durable source of truth. Each task
claims due jobs with ``SELECT ... FOR UPDATE SKIP LOCKED`` so concurrent Celery workers never
take the same job, then dispatches them under the existing retry/dead-letter policy.
"""
from typing import Optional

from celery import shared_task

from app import db
from app.services import jobs as J


def _ensure_session_factory() -> None:
    if db.SessionLocal is None:
        db.init_db()


@shared_task(name="app.services.jobs.run_due_jobs", bind=True)
def run_due_jobs(self, limit: int = 20, types: Optional[list] = None) -> dict:
    """Claim due jobs from the Postgres Job table and dispatch them.

    Safe to run repeatedly (e.g. via celery beat). Returns a summary for logs and tests.
    """
    _ensure_session_factory()
    with db.SessionLocal() as session:
        jobs = J.claim(session, limit=limit, types=types)
        outcomes = [
            {"id": job.id, "type": job.type, "status": J.dispatch(session, job, {})}
            for job in jobs
        ]
        return {"claimed": len(jobs), "outcomes": outcomes}
