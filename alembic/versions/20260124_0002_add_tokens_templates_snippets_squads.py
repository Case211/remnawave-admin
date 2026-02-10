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
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_tokens (
            uuid UUID NOT NULL,
            name VARCHAR(255),
            token_hash VARCHAR(255),
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_tokens_name ON api_tokens (name)")

    # Subscription Templates table
    op.execute("""
        CREATE TABLE IF NOT EXISTS templates (
            uuid UUID NOT NULL,
            name VARCHAR(255),
            template_type VARCHAR(50),
            sort_order INTEGER,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_templates_name ON templates (name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_templates_sort_order ON templates (sort_order)")

    # Snippets table (keyed by name, not UUID)
    op.execute("""
        CREATE TABLE IF NOT EXISTS snippets (
            name VARCHAR(255) NOT NULL,
            snippet_data JSON,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (name)
        )
    """)

    # Internal Squads table
    op.execute("""
        CREATE TABLE IF NOT EXISTS internal_squads (
            uuid UUID NOT NULL,
            name VARCHAR(255),
            description TEXT,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_internal_squads_name ON internal_squads (name)")

    # External Squads table
    op.execute("""
        CREATE TABLE IF NOT EXISTS external_squads (
            uuid UUID NOT NULL,
            name VARCHAR(255),
            description TEXT,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_external_squads_name ON external_squads (name)")


def downgrade() -> None:
    op.drop_table('external_squads')
    op.drop_table('internal_squads')
    op.drop_table('snippets')
    op.drop_table('templates')
    op.drop_table('api_tokens')
