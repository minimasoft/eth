"""Per-document LLM mode (thinking/instruct) + instruct sampling params.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add instruct sampling params to llm_provider and llm_mode to document.

    Instruct params are nullable with no server default: NULL means
    "use the module defaults" (see eth_pipeline.llm INSTRUCT_* constants).
    """
    op.add_column('llm_provider', sa.Column('instruct_temperature', sa.Float(), nullable=True))
    op.add_column('llm_provider', sa.Column('instruct_top_p', sa.Float(), nullable=True))
    op.add_column('llm_provider', sa.Column('instruct_top_k', sa.Integer(), nullable=True))
    op.add_column('document', sa.Column('llm_mode', sa.String(), nullable=False, server_default='thinking'))


def downgrade() -> None:
    op.drop_column('document', 'llm_mode')
    op.drop_column('llm_provider', 'instruct_top_k')
    op.drop_column('llm_provider', 'instruct_top_p')
    op.drop_column('llm_provider', 'instruct_temperature')
