"""Drop old v6 event/reference/entity tables (Phase 38 cleanup)

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-10
"""
from alembic import op

revision = '0002'
down_revision = '0001'


def upgrade():
    """Drop old v6 tables in FK-safe order (children before parents)."""
    op.drop_table('event_participant')
    op.drop_table('event_entity_link')
    op.drop_table('reference')
    op.drop_table('event')
    op.drop_table('canonical_entity')


def downgrade():
    """No downgrade — tables contain deprecated v6 pipeline data."""
    pass