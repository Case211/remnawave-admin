"""Partition user_connections by connected_at (monthly range).

Revision ID: 0069
Revises: 0068
Create Date: 2026-05-27

Converts user_connections to a partitioned table for:
- Fast time-range queries (partition pruning)
- Instant cleanup via DROP PARTITION instead of batched DELETE
- Smaller per-partition indexes

Strategy: CREATE new partitioned table → INSERT data → RENAME swap.
Downtime: ~30-60s for the swap (collector INSERT will fail during rename).
"""
from typing import Sequence, Union
from alembic import op
from sqlalchemy import text

revision: str = '0069'
down_revision: Union[str, None] = '0068'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotency guard (added in 2.15.1 after the partition incident):
    # if user_connections is already a partitioned table (pg_class.relkind = 'p'),
    # a previous run already completed the RENAME swap. Re-running the body would
    # create a second empty partitioned table and re-swap, leaving duplicate
    # tables/indexes. This happens when the backend container restarts mid-migration.
    # Bail out cleanly so the run is a no-op.
    conn = op.get_bind()
    relkind = conn.execute(text(
        "SELECT relkind FROM pg_class "
        "WHERE relname = 'user_connections' AND relnamespace = 'public'::regnamespace"
    )).scalar()
    if relkind == 'p':
        return

    # 1. Create partitioned table (same schema, no FK — partitioned tables
    #    can have FK referencing other tables but need partition key in PK)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_partitioned (
            id BIGSERIAL NOT NULL,
            user_uuid UUID NOT NULL,
            ip_address VARCHAR(45),
            node_uuid UUID,
            connected_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            disconnected_at TIMESTAMP WITH TIME ZONE,
            device_info JSONB,
            PRIMARY KEY (id, connected_at)
        ) PARTITION BY RANGE (connected_at)
    """)

    # 2. Create partitions: 3 months back + current + 2 months forward + default
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_p2026_03
            PARTITION OF user_connections_partitioned
            FOR VALUES FROM ('2026-03-01') TO ('2026-04-01')
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_p2026_04
            PARTITION OF user_connections_partitioned
            FOR VALUES FROM ('2026-04-01') TO ('2026-05-01')
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_p2026_05
            PARTITION OF user_connections_partitioned
            FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_p2026_06
            PARTITION OF user_connections_partitioned
            FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_p2026_07
            PARTITION OF user_connections_partitioned
            FOR VALUES FROM ('2026-07-01') TO ('2026-08-01')
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_default
            PARTITION OF user_connections_partitioned DEFAULT
    """)

    # 3. Create indexes on partitioned table (auto-propagate to partitions)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_uc_part_user_connected
        ON user_connections_partitioned (user_uuid, connected_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_uc_part_user_active
        ON user_connections_partitioned (user_uuid, disconnected_at, connected_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_uc_part_ip
        ON user_connections_partitioned (ip_address)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_uc_part_node
        ON user_connections_partitioned (node_uuid)
    """)
    # Partial index for active connection lookups (UPDATE + WHERE NOT EXISTS)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_uc_part_active_user_ip
        ON user_connections_partitioned (user_uuid, ip_address)
        WHERE disconnected_at IS NULL
    """)

    # 4. Copy data from old table (only recent — last 60 days)
    # host() strips CIDR suffix from INET columns (e.g. "1.2.3.4/32" → "1.2.3.4")
    op.execute("""
        INSERT INTO user_connections_partitioned
            (user_uuid, ip_address, node_uuid, connected_at, disconnected_at, device_info)
        SELECT user_uuid,
               CASE WHEN ip_address IS NOT NULL THEN host(ip_address::inet) ELSE NULL END,
               node_uuid,
               COALESCE(connected_at, NOW()), disconnected_at, device_info::jsonb
        FROM user_connections
        WHERE connected_at > NOW() - INTERVAL '60 days'
        ON CONFLICT DO NOTHING
    """)

    # 5. Atomic swap via RENAME
    op.execute("ALTER TABLE user_connections RENAME TO user_connections_old")
    op.execute("ALTER TABLE user_connections_partitioned RENAME TO user_connections")

    # 6. Drop old table
    op.execute("DROP TABLE IF EXISTS user_connections_old CASCADE")


def downgrade() -> None:
    # Recreate original non-partitioned table
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections_regular (
            id BIGSERIAL NOT NULL,
            user_uuid UUID REFERENCES users(uuid) ON DELETE CASCADE,
            ip_address VARCHAR(45),
            node_uuid UUID REFERENCES nodes(uuid) ON DELETE SET NULL,
            connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            disconnected_at TIMESTAMP WITH TIME ZONE,
            device_info JSON,
            PRIMARY KEY (id)
        )
    """)

    # Copy data back
    op.execute("""
        INSERT INTO user_connections_regular
            (user_uuid, ip_address, node_uuid, connected_at, disconnected_at, device_info)
        SELECT user_uuid, ip_address, node_uuid, connected_at, disconnected_at, device_info
        FROM user_connections
    """)

    # Swap
    op.execute("DROP TABLE IF EXISTS user_connections CASCADE")
    op.execute("ALTER TABLE user_connections_regular RENAME TO user_connections")

    # Recreate original indexes
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_user ON user_connections (user_uuid, connected_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_ip ON user_connections (ip_address)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_node ON user_connections (node_uuid)")
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_user_connections_active_uq
        ON user_connections (user_uuid, ip_address)
        WHERE disconnected_at IS NULL
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_connections_user_active
        ON user_connections (user_uuid, disconnected_at, connected_at DESC)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_connections_user_connected_at
        ON user_connections (user_uuid, connected_at DESC)
    """)

