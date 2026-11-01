import copy
import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db
from app.models import Base
from financial_engine.rules import Ruleset  # noqa: E402


class IdempotentTestClient:
    """TestClient wrapper that auto-adds a unique Idempotency-Key to state-changing requests.

    The idempotency middleware (gap #2) requires Idempotency-Key on POST/PUT/PATCH/DELETE.
    Tests use authenticated actor headers (X-Actor-Id) so each state-changing request needs a
    distinct key; this wrapper generates one per call so tests don't need to thread keys through
    every call site.
    """

    def __init__(self, client: TestClient):
        self._client = client
        for attr in ("gw",):
            if hasattr(client, attr):
                setattr(self, attr, getattr(client, attr))

    def _idem_headers(self, headers: dict | None) -> dict:
        h = dict(headers or {})
        h.setdefault("Idempotency-Key", str(uuid.uuid4()))
        return h

    def post(self, *args, **kwargs):
        kwargs["headers"] = self._idem_headers(kwargs.get("headers"))
        return self._client.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        kwargs["headers"] = self._idem_headers(kwargs.get("headers"))
        return self._client.put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        kwargs["headers"] = self._idem_headers(kwargs.get("headers"))
        return self._client.patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        kwargs["headers"] = self._idem_headers(kwargs.get("headers"))
        return self._client.delete(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._client.get(*args, **kwargs)

    def head(self, *args, **kwargs):
        return self._client.head(*args, **kwargs)

    def options(self, *args, **kwargs):
        return self._client.options(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(self._client, name)

BASE = dict(
    circle_id="c1", version=1, currency="INR", total_chit_value=10_000_000, member_count=20,
    payout_mode="SEALED_BID_AUCTION",
    commission=dict(base="PERCENT_OF_CHIT_VALUE", rate="0.05", rounding="HALF_UP"),
    dividend=dict(allocation="ALL_MEMBERS"),
    auction=dict(max_discount_rate="0.40", min_discount=0, increment=0,
                 tie_break="EARLIEST_BID", no_bid_fallback="HOLD"),
    grace_period_days=5, rounding=dict(contribution_remainder="REJECT", remainder_destination=None),
    required_approvals=1, require_security=False, jurisdiction_profile="IN-SANDBOX",
    effective_date="2026-10-22", status="ACTIVE",
)


def rules_dict(**over):
    d = copy.deepcopy(BASE)
    d.update(over)
    return d


def make_rules(**over) -> Ruleset:
    return Ruleset.from_dict(rules_dict(**over))


def members(n=20):
    return [f"m{i:02d}" for i in range(1, n + 1)]


@pytest.fixture(autouse=True)
def _isolate_tests_on_postgres():
    """Give each test a clean schema on PostgreSQL (CI).

    The ``env`` fixture provides a fresh in-memory SQLite database per test, but on
    PostgreSQL all tests share one database. Truncate every table after each test so
    PostgreSQL behaves like the per-test-fresh SQLite, keeping CI results comparable
    to local runs. Cross-test data leakage (e.g. ``SettlementRow.count()`` assertions)
    would otherwise make shared-database runs flaky.
    """
    yield
    if os.getenv("DATABASE_URL", "sqlite://").startswith("postgresql"):
        with db.SessionLocal() as s:
            for table in reversed(Base.metadata.sorted_tables):
                s.execute(delete(table))
            s.commit()
