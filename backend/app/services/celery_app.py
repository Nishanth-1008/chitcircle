"""Celery application: Redis broker + result backend.

The Postgres `Job` table (app/services/jobs.py) remains the durable source of truth:
``enqueue``/``claim``/``complete``/``fail`` still write to Postgres, so a Celery worker crash
loses nothing. Celery only executes and retries the dispatch of those durable jobs.

Usage:
    celery -A app.services.celery_app worker            # process due jobs
    celery -A app.services.celery_app worker --beat     # also run the periodic dispatcher
"""
from celery import Celery

from ..config import redis_url

celery_app = Celery(
    "chitcircle",
    broker=redis_url(),
    backend=redis_url(),
    include=["app.services.jobs_tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="chitcircle",
)

celery_app.conf.beat_schedule = {
    "run-due-jobs-every-10-seconds": {
        "task": "app.services.jobs.run_due_jobs",
        "schedule": 10.0,
        "kwargs": {"limit": 20},
    },
}
