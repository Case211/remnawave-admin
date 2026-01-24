"""Add tokens, templates, snippets, squads tables.

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # API Tokens table
    op.create_table(
        'api_tokens',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('token_hash', sa.String(255), nullable=True),  # Masked token for display
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index('idx_api_tokens_name', 'api_tokens', ['name'])

    # Subscription Templates table
    op.create_table(
        'templates',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('template_type', sa.String(50), nullable=True),  # json, yaml, etc.
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index('idx_templates_name', 'templates', ['name'])
    op.create_index('idx_templates_sort_order', 'templates', ['sort_order'])

    # Snippets table (keyed by name, not UUID)
    op.create_table(
        'snippets',
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('snippet_data', sa.JSON(), nullable=True),  # The actual snippet content
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('name')
    )

    # Internal Squads table
    op.create_table(
        'internal_squads',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index('idx_internal_squads_name', 'internal_squads', ['name'])

    # External Squads table
    op.create_table(
        'external_squads',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(255), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('NOW()'), nullable=True),
        sa.Column('raw_data', sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint('uuid')
    )
    op.create_index('idx_external_squads_name', 'external_squads', ['name'])


def downgrade() -> None:
    op.drop_table('external_squads')
    op.drop_table('internal_squads')
    op.drop_table('snippets')
    op.drop_table('templates')
    op.drop_table('api_tokens')
