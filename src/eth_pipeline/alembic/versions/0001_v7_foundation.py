"""v7.0 foundation: PostGIS, schema_version, new event tables

Revision ID: 0001
Revises: None
Create Date: 2026-06-09
"""
import logging

from alembic import op
import sqlalchemy as sa

logger = logging.getLogger(__name__)

revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    except Exception:
        logger.warning("PostGIS extension not available — will be created when postgis/postgis image is deployed (Plan 33-03)")

    op.add_column('document', sa.Column(
        'schema_version', sa.String(10),
        server_default='v6',
        nullable=False
    ))

    op.create_table(
        'event_v2',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('document_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('description', sa.Text(), default=''),
        sa.Column('time_start', sa.DateTime(timezone=True), nullable=True),
        sa.Column('time_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('time_precision', sa.String(), nullable=True),
        sa.Column('extraction_confidence', sa.Float(), default=1.0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['document_id'], ['document(id)'], ondelete='CASCADE'),
    )
    op.create_index('idx_event_v2_document', 'event_v2', ['document_id'])
    op.create_index('idx_event_v2_time_start', 'event_v2', ['time_start'])

    op.create_table(
        'event_location',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('location_type', sa.String(), nullable=True),
        sa.Column('geom', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['event_id'], ['event_v2(id)'], ondelete='CASCADE'),
    )
    op.create_index('idx_event_location_event', 'event_location', ['event_id'])

    op.create_table(
        'event_participant_v2',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('role', sa.String(), default=''),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['event_id'], ['event_v2(id)'], ondelete='CASCADE'),
    )
    op.create_index('idx_event_participant_v2_event', 'event_participant_v2', ['event_id'])

    op.create_table(
        'event_document',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('document_id', sa.String(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['event_id'], ['event_v2(id)'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['document_id'], ['document(id)'], ondelete='CASCADE'),
    )
    op.create_index('idx_event_document_event', 'event_document', ['event_id'])
    op.create_index('idx_event_document_doc', 'event_document', ['document_id'])

    op.create_table(
        'event_ref',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('event_id', sa.String(), nullable=False),
        sa.Column('reference_type', sa.String(), nullable=False),
        sa.Column('verbatim_text', sa.Text(), nullable=False),
        sa.Column('span_start', sa.Integer(), nullable=False),
        sa.Column('span_end', sa.Integer(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['event_id'], ['event_v2(id)'], ondelete='CASCADE'),
    )
    op.create_index('idx_event_ref_event', 'event_ref', ['event_id'])


def downgrade():
    op.drop_table('event_ref')
    op.drop_table('event_document')
    op.drop_table('event_participant_v2')
    op.drop_table('event_location')
    op.drop_table('event_v2')
    op.drop_column('document', 'schema_version')
