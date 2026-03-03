"""Add performance indexes and UNIQUE constraint for user_connections.

Revision ID: 0039
Revises: 0038
Create Date: 2026-03-03

Fixes deadlocks and improves batch collector performance:
- Cleans up duplicate active connections (keeps only the latest per user+ip)
- Adds partial UNIQUE index on (user_uuid, ip_address) WHERE disconnected_at IS NULL
  to enable INSERT ... ON CONFLICT batch upserts
- Adds composite index for active connection lookups
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0039'
down_revision: Union[str, None] = '0038'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Clean up duplicate active connections: keep only the latest per (user_uuid, ip_address)
    op.execute("""
        UPDATE user_connections SET disconnected_at = NOW()
        WHERE id IN (
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY user_uuid, ip_address
                    ORDER BY connected_at DESC
                ) AS rn
                FROM user_connections
                WHERE disconnected_at IS NULL
            ) sub
            WHERE rn > 1
        )
    """)

    # 2. Partial UNIQUE index: at most one active connection per (user, IP)
    #    Enables INSERT ... ON CONFLICT for batch upserts
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_connections_active_uq
        ON user_connections (user_uuid, ip_address)
        WHERE disconnected_at IS NULL
    """)

    # 3. Composite index for active connection lookups and stale-close queries
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_connections_user_active
        ON user_connections (user_uuid, disconnected_at, connected_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_connections_user_active")
    op.execute("DROP INDEX IF EXISTS idx_user_connections_active_uq")
