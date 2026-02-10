"""Initial schema for Remnawave Admin Bot database.

Revision ID: 0001
Revises:
Create Date: 2026-01-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users table
    op.execute("""
        CREATE TABLE IF NOT EXISTS users (
            uuid UUID NOT NULL,
            short_uuid VARCHAR(16),
            username VARCHAR(255),
            subscription_uuid UUID,
            telegram_id BIGINT,
            email VARCHAR(255),
            status VARCHAR(50),
            expire_at TIMESTAMP WITH TIME ZONE,
            traffic_limit_bytes BIGINT,
            used_traffic_bytes BIGINT,
            hwid_device_limit INTEGER,
            created_at TIMESTAMP WITH TIME ZONE,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users (username)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users (telegram_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_status ON users (status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_short_uuid ON users (short_uuid)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_subscription_uuid ON users (subscription_uuid)")

    # Nodes table
    op.execute("""
        CREATE TABLE IF NOT EXISTS nodes (
            uuid UUID NOT NULL,
            name VARCHAR(255),
            address VARCHAR(255),
            port INTEGER,
            is_disabled BOOLEAN DEFAULT false,
            is_connected BOOLEAN DEFAULT false,
            traffic_limit_bytes BIGINT,
            traffic_used_bytes BIGINT,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes (name)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_nodes_is_connected ON nodes (is_connected)")

    # Hosts table
    op.execute("""
        CREATE TABLE IF NOT EXISTS hosts (
            uuid UUID NOT NULL,
            remark VARCHAR(255),
            address VARCHAR(255),
            port INTEGER,
            is_disabled BOOLEAN DEFAULT false,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_hosts_remark ON hosts (remark)")

    # Config profiles table
    op.execute("""
        CREATE TABLE IF NOT EXISTS config_profiles (
            uuid UUID NOT NULL,
            name VARCHAR(255),
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            raw_data JSON,
            PRIMARY KEY (uuid)
        )
    """)

    # Sync metadata table
    op.execute("""
        CREATE TABLE IF NOT EXISTS sync_metadata (
            key VARCHAR(100) NOT NULL,
            last_sync_at TIMESTAMP WITH TIME ZONE,
            sync_status VARCHAR(50),
            error_message TEXT,
            records_synced INTEGER DEFAULT 0,
            PRIMARY KEY (key)
        )
    """)

    # User connections table
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_connections (
            id SERIAL NOT NULL,
            user_uuid UUID REFERENCES users(uuid) ON DELETE CASCADE,
            ip_address VARCHAR(45),
            node_uuid UUID REFERENCES nodes(uuid) ON DELETE SET NULL,
            connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            disconnected_at TIMESTAMP WITH TIME ZONE,
            device_info JSON,
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_user ON user_connections (user_uuid, connected_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_ip ON user_connections (ip_address)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_node ON user_connections (node_uuid)")


def downgrade() -> None:
    op.drop_table('user_connections')
    op.drop_table('sync_metadata')
    op.drop_table('config_profiles')
    op.drop_table('hosts')
    op.drop_table('nodes')
    op.drop_table('users')
