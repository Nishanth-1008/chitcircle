from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from . import config
from .models import Base

engine = None
SessionLocal = None

_GUARD_SQL = """
CREATE OR REPLACE FUNCTION chitcircle_ledger_immutable() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'ledger_events is append-only'; END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS ledger_no_update ON ledger_events;
CREATE TRIGGER ledger_no_update BEFORE UPDATE OR DELETE ON ledger_events
FOR EACH ROW EXECUTE FUNCTION chitcircle_ledger_immutable();
"""


def make_engine(url=None):
    url = url or config.DATABASE_URL
    kw = {}
    if url.startswith("sqlite"):
        kw["connect_args"] = {"check_same_thread": False}
        if url in ("sqlite://", "sqlite:///:memory:"):
            kw["poolclass"] = StaticPool
    return create_engine(url, **kw)


def init_db(url=None, create=True):
    global engine, SessionLocal
    engine = make_engine(url)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    if create:
        Base.metadata.create_all(engine)
        if engine.dialect.name == "postgresql":
            with engine.begin() as c:
                c.execute(text(_GUARD_SQL))
    return engine


def get_session():
    if SessionLocal is None:
        init_db()
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()          # anything not explicitly committed is discarded: no partial writes
