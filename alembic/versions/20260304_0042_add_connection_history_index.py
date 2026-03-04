"""Add index on user_connections(user_uuid, connected_at) for history queries.

Revision ID: 0042
Revises: 0041
Create Date: 2026-03-04

The get_user_connection_stats_combined query has subqueries filtering by
(user_uuid, connected_at) without disconnected_at — not covered by the
existing idx_user_connections_user_active index. This index speeds up:
  - COUNT(DISTINCT ip_address) WHERE user_uuid=? AND connected_at > ?
  - COUNT(*) WHERE user_uuid=? AND connected_at > ? (24h history)
  - MAX(connected_at) WHERE user_uuid=? AND ...
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0042'
down_revision: Union[str, None] = '0041'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_connections_user_connected_at
        ON user_connections (user_uuid, connected_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_user_connections_user_connected_at")
