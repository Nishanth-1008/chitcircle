"""row-level security policies

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-01 00:00:00.000000
"""
from __future__ import annotations

from alembic import op

# Row-level security: circles, members, cycles, settlements are visible only to the user who
# organizes the parent circle (keyed by app.current_user_id). The application connects as the
# table owner, so FORCE is required for RLS to actually apply to that user. Mirrors the policy
# text in app.db._GUARD_SQL; applied only on PostgreSQL, where RLS exists.
#
# `CREATE POLICY IF NOT EXISTS` is not valid PostgreSQL, so each policy is dropped (if present)
# before being created, keeping the migration idempotent across upgrade/downgrade cycles.
_RLS_SQL = """
ALTER TABLE circles ENABLE ROW LEVEL SECURITY;
ALTER TABLE circles FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS circles_organizer_rls ON circles;
CREATE POLICY circles_organizer_rls ON circles
    USING (organizer_id = current_setting('app.current_user_id', true));

ALTER TABLE members ENABLE ROW LEVEL SECURITY;
ALTER TABLE members FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS members_organizer_rls ON members;
CREATE POLICY members_organizer_rls ON members
    USING (circle_id IN (
        SELECT id FROM circles WHERE organizer_id = current_setting('app.current_user_id', true)
    ));

ALTER TABLE cycles ENABLE ROW LEVEL SECURITY;
ALTER TABLE cycles FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cycles_organizer_rls ON cycles;
CREATE POLICY cycles_organizer_rls ON cycles
    USING (circle_id IN (
        SELECT id FROM circles WHERE organizer_id = current_setting('app.current_user_id', true)
    ));

ALTER TABLE settlements ENABLE ROW LEVEL SECURITY;
ALTER TABLE settlements FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS settlements_organizer_rls ON settlements;
CREATE POLICY settlements_organizer_rls ON settlements
    USING (circle_id IN (
        SELECT id FROM circles WHERE organizer_id = current_setting('app.current_user_id', true)
    ));
"""

_RLS_DOWNGRADE_SQL = """
DROP POLICY IF EXISTS settlements_organizer_rls ON settlements;
ALTER TABLE settlements NO FORCE ROW LEVEL SECURITY;
ALTER TABLE settlements DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS cycles_organizer_rls ON cycles;
ALTER TABLE cycles NO FORCE ROW LEVEL SECURITY;
ALTER TABLE cycles DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS members_organizer_rls ON members;
ALTER TABLE members NO FORCE ROW LEVEL SECURITY;
ALTER TABLE members DISABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS circles_organizer_rls ON circles;
ALTER TABLE circles NO FORCE ROW LEVEL SECURITY;
ALTER TABLE circles DISABLE ROW LEVEL SECURITY;
"""

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_RLS_SQL)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(_RLS_DOWNGRADE_SQL)
