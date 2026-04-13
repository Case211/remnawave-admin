"""Add node_traffic_snapshots table for granular traffic timeseries.

Revision ID: 0056
Revises: 0055
Create Date: 2026-04-13

Stores per-node total traffic bytes at each sync cycle (~5 min),
enabling hourly/daily granularity on the Dashboard traffic chart
instead of relying on Panel API's daily-only bandwidth-stats.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0056"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS node_traffic_snapshots (
            id BIGSERIAL PRIMARY KEY,
            node_uuid UUID NOT NULL,
            traffic_bytes BIGINT NOT NULL DEFAULT 0,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    # Index for time-range queries grouped by node
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_node_traffic_snapshots_created
        ON node_traffic_snapshots (created_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_node_traffic_snapshots_node_created
        ON node_traffic_snapshots (node_uuid, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS node_traffic_snapshots")
