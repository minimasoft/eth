"""Per-event model provenance, document source groups, geo-ready locations.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-30
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-event LLM provenance: which provider/model extracted this event.
    # Plain text without FK on purpose: provenance must survive provider
    # deletion, and it lets multi-model comparison group events without a
    # join through document.
    op.add_column('event_v2', sa.Column('provider_id', sa.String(), nullable=True))
    op.add_column('event_v2', sa.Column('model', sa.String(), nullable=True))
    op.create_index('ix_event_v2_model', 'event_v2', ['model'])

    # Shared source group: upload fan-out creates one document row per
    # provider; all siblings of the same upload share a source_id.
    op.add_column('document', sa.Column('source_id', sa.String(), nullable=True))
    op.create_index('ix_document_source_id', 'document', ['source_id'])
    op.execute("UPDATE document SET source_id = id WHERE source_id IS NULL")

    # Geo anchors for the future map view (filled by geocoding later;
    # geom EWKT stays the raw geometry of record).
    op.add_column('event_location', sa.Column('lat', sa.Float(), nullable=True))
    op.add_column('event_location', sa.Column('lon', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('event_location', 'lon')
    op.drop_column('event_location', 'lat')
    op.drop_index('ix_document_source_id', table_name='document')
    op.drop_column('document', 'source_id')
    op.drop_index('ix_event_v2_model', table_name='event_v2')
    op.drop_column('event_v2', 'model')
    op.drop_column('event_v2', 'provider_id')
