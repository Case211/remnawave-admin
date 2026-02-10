"""Add bot_config table for dynamic configuration storage.

Revision ID: 0006
Revises: 0005
Create Date: 2026-01-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS bot_config (
            key VARCHAR(100) NOT NULL PRIMARY KEY,
            value TEXT,
            value_type VARCHAR(20) NOT NULL DEFAULT 'string',
            category VARCHAR(50) NOT NULL DEFAULT 'general',
            subcategory VARCHAR(50),
            display_name VARCHAR(200),
            description TEXT,
            default_value TEXT,
            env_var_name VARCHAR(100),
            is_secret BOOLEAN NOT NULL DEFAULT false,
            is_readonly BOOLEAN NOT NULL DEFAULT false,
            validation_regex VARCHAR(500),
            options_json TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_bot_config_category ON bot_config (category)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bot_config_subcategory ON bot_config (subcategory)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bot_config_env_var_name ON bot_config (env_var_name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_bot_config_sort_order ON bot_config (category, sort_order)")


def downgrade() -> None:
    op.drop_index('idx_bot_config_sort_order', table_name='bot_config')
    op.drop_index('idx_bot_config_env_var_name', table_name='bot_config')
    op.drop_index('idx_bot_config_subcategory', table_name='bot_config')
    op.drop_index('idx_bot_config_category', table_name='bot_config')
    op.drop_table('bot_config')
