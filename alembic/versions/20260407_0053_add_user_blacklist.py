"""Add user_blacklist table for Telegram user ID blacklisting.

Revision ID: 0053
Revises: 0052
Create Date: 2026-04-07
"""
from alembic import op

revision = "0053"
down_revision = "0052"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_blacklist (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            reason TEXT,
            source VARCHAR(500) NOT NULL DEFAULT 'manual',
            added_by_username VARCHAR(255),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (telegram_id)
        );
        CREATE INDEX IF NOT EXISTS idx_user_blacklist_telegram_id ON user_blacklist (telegram_id);
        CREATE INDEX IF NOT EXISTS idx_user_blacklist_source ON user_blacklist (source);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS user_blacklist;")
