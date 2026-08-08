"""LLM providers (DB-backed) and per-document model selection.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create llm_provider table and link documents to a provider/model."""
    op.create_table(
        'llm_provider',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False, unique=True),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('base_url', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), nullable=True),
        sa.Column('is_default', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Per-document provider selection (fan-out). provider_id points at the
    # chosen llm_provider; model is denormalized for convenience and to keep
    # llm_usage/llm_call_log attribution cheap without a join.
    op.add_column('document', sa.Column('provider_id', sa.String(), nullable=True))
    op.add_column('document', sa.Column('model', sa.String(), nullable=True))
    op.create_index('ix_document_provider_id', 'document', ['provider_id'])
    op.create_foreign_key(
        'fk_document_provider_id', 'document', 'llm_provider',
        ['provider_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_document_provider_id', 'document', type_='foreignkey')
    op.drop_index('ix_document_provider_id', table_name='document')
    op.drop_column('document', 'model')
    op.drop_column('document', 'provider_id')
    op.drop_table('llm_provider')