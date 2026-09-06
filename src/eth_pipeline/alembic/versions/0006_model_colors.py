"""DB-backed model colors for the Línea de tiempo view.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create model_color and backfill one color per existing provider.

    ``color_index`` is a stable index into the fixed tableau20 palette
    (the RGB values live only in the frontend renderer).  The UNIQUE
    constraint on provider_id enforces the 1:1 provider↔color relation;
    ON DELETE CASCADE frees the index when a provider is deleted.
    """
    op.create_table(
        'model_color',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('provider_id', sa.Text(), nullable=False),
        sa.Column('color_index', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint('color_index >= 0 AND color_index <= 19',
                           name='ck_model_color_index_range'),
        sa.ForeignKeyConstraint(['provider_id'], ['llm_provider.id'],
                                name='fk_model_color_provider_id',
                                ondelete='CASCADE'),
        sa.UniqueConstraint('provider_id', name='uq_model_color_provider_id'),
    )

    # Backfill: one row per existing provider, ordered by creation, assigning
    # first-available indices 0..19 (wraps past 20 providers).
    op.execute(
        "INSERT INTO model_color (id, provider_id, color_index) "
        "SELECT gen_random_uuid()::text, p.id, "
        "       ((row_number() OVER (ORDER BY p.created_at, p.id)) - 1) % 20 "
        "FROM llm_provider p "
        "WHERE NOT EXISTS (SELECT 1 FROM model_color mc WHERE mc.provider_id = p.id)"
    )


def downgrade() -> None:
    op.drop_table('model_color')
