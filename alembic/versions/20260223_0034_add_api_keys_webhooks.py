"""Add api_keys and webhook_subscriptions tables.

Revision ID: 0034
Revises: 0033
Create Date: 2026-02-23

External API: API key authentication and webhook event dispatch.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0034'
down_revision: Union[str, None] = '0033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            key_hash VARCHAR(512) NOT NULL UNIQUE,
            key_prefix VARCHAR(12) NOT NULL,
            scopes TEXT[] NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT true,
            expires_at TIMESTAMPTZ,
            last_used_at TIMESTAMPTZ,
            created_by_admin_id BIGINT,
            created_by_username VARCHAR(255),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys (key_hash)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_active ON api_keys (is_active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS webhook_subscriptions (
            id BIGSERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            url VARCHAR(2048) NOT NULL,
            secret VARCHAR(512),
            events TEXT[] NOT NULL DEFAULT '{}',
            is_active BOOLEAN NOT NULL DEFAULT true,
            last_triggered_at TIMESTAMPTZ,
            failure_count INT NOT NULL DEFAULT 0,
            created_by_admin_id BIGINT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_webhook_subs_active ON webhook_subscriptions (is_active)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_webhook_subs_active")
    op.execute("DROP TABLE IF EXISTS webhook_subscriptions")
    op.execute("DROP INDEX IF EXISTS idx_api_keys_active")
    op.execute("DROP INDEX IF EXISTS idx_api_keys_hash")
    op.execute("DROP TABLE IF EXISTS api_keys")
