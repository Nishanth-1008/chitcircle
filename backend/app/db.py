from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from .config import database_url, read_replica_url
from .models import Base

engine = None
SessionLocal = None
read_engine = None
ReadSessionLocal = None

_GUARD_SQL = """
CREATE OR REPLACE FUNCTION chitcircle_ledger_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'ledger_events is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS ledger_no_update ON ledger_events;
CREATE TRIGGER ledger_no_update BEFORE UPDATE OR DELETE ON ledger_events
FOR EACH ROW EXECUTE FUNCTION chitcircle_ledger_immutable();

-- Row-level security: circles, members, cycles, settlements are visible only
-- to the user who organizes the parent circle (keyed by app.current_user_id).
-- The application connects as the table owner, so FORCE is required for RLS
-- to actually apply to that user.
ALTER TABLE circles ENABLE ROW LEVEL SECURITY;
ALTER TABLE circles FORCE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS circles_organizer_rls ON circles
    USING (organizer_id = current_setting('app.current_user_id', true));

ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE members FORCE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS members_organizer_rls ON members
    USING (circle_id IN (
        SELECT id FROM circles WHERE organizer_id = current_setting('app.current_user_id', true)
    ));

ALTER TABLE cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cycles FORCE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS cycles_organizer_rls ON cycles
    USING (circle_id IN (
        SELECT id FROM circles WHERE organizer_id = current_setting('app.current_user_id', true)
    ));

ALTER TABLE settlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE settlements FORCE ROW LEVEL SECURITY;
CREATE POLICY IF NOT EXISTS settlements_organizer_rls ON settlements
    USING (circle_id IN (
        SELECT id FROM circles WHERE organizer_id = current_setting('app.current_user_id', true)
    ));
"""


def make_engine(url=None):
    url = url or database_url()
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool
    return create_engine(url, **kw)


def make_read_engine(url=None):
    """Engine for read-only endpoints. Reads from the configured replica when
    READ_REPLICA_DATABASE_URL is set; otherwise falls back to the primary so
    behavior is unchanged (gap #20: replica routing is opt-in via env var)."""
    url = url or read_replica_url() or database_url()
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool
    return create_engine(url, **kw)


def init_db(url=None, create=None):
    """Open the engine (and create the session factory).

    On SQLite (`tests`, local bootstrap) the schema is created with `create_all` — there is no
    Alembic history for an in-memory database. On PostgreSQL the schema is owned by Alembic and
    `create` is forced off so startup never mutates a deployed schema (gap #1).
    """
    global engine, SessionLocal
    engine = make_engine(url)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    if create is None:
        create = engine.dialect.name == "sqlite"
    if create:
        Base.metadata.create_all(engine)
        if engine.dialect.name == "postgresql":
            with engine.begin() as c:
                c.execute(text(_GUARD_SQL))
    return engine


def migrations_pending() -> bool:
    """True when the database schema is behind the migrations.

    Startup must never mutate schema (gap #1), so production is *checked* here and migrated by
    `alembic upgrade head`. SQLite (tests, local bootstrap) has no Alembic history and is created
    by `init_db`.
    """
    if engine is None or engine.dialect.name == "sqlite":
        return False
    try:
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory
        from alembic.config import Config
        here = Path(__file__).resolve().parent.parent
        cfg = Config(str(here / "alembic.ini"))
        cfg.set_main_option("script_location", str(here / "alembic"))
        script = ScriptDirectory.from_config(cfg)
        with engine.begin() as c:
            current = set(MigrationContext.configure(c).get_current_heads())
        return current != set(script.get_heads())
    except Exception:
        # if migrations cannot be inspected at all, treat it as pending rather than guessing
        return True


def assert_migrations_applied() -> None:
    if migrations_pending():
        raise RuntimeError(
            "database schema is not up to date; run `alembic upgrade head` before starting (gap #1)")


def get_session():
    if SessionLocal is None:
        init_db()
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()          # anything not explicitly committed is discarded: no partial writes


def get_read_session():
    """Yield a session for read-only endpoints.

    When READ_REPLICA_DATABASE_URL is set, binds to a dedicated read engine
    (the replica). Otherwise falls back to the primary session, so behavior is
    unchanged unless a replica is explicitly configured (gap #20).
    """
    if not read_replica_url():
        if SessionLocal is None:
            init_db()
        s = SessionLocal()
    else:
        global read_engine, ReadSessionLocal
        if read_engine is None:
            read_engine = make_read_engine()
            ReadSessionLocal = sessionmaker(bind=read_engine, expire_on_commit=False)
        s = ReadSessionLocal()
    try:
        yield s
    finally:
        s.close()
