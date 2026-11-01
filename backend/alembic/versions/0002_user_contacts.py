"""user_contacts table

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-31 09:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_contacts',
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('value', sa.String(length=255), nullable=False),
        sa.Column('verified', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('user_id'),
    )
    op.create_index(op.f('ix_user_contacts_user_id'), 'user_contacts', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_user_contacts_user_id'), table_name='user_contacts')
    op.drop_table('user_contacts')
