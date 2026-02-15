"""Add fleet management tables and agent v2 columns.

Revision ID: 0025
Revises: 0024
Create Date: 2026-02-15

Creates tables for fleet command audit log, script catalog,
provisioning sessions, and adds agent v2 connectivity columns to nodes.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Agent v2 columns on nodes ──
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS agent_v2_connected BOOLEAN DEFAULT false")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS agent_v2_last_ping TIMESTAMPTZ")

    # ── node_command_log — audit trail for all fleet commands ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS node_command_log (
            id BIGSERIAL PRIMARY KEY,
            node_uuid VARCHAR(255) NOT NULL,
            admin_id INTEGER,
            admin_username VARCHAR(100),
            command_type VARCHAR(50) NOT NULL,
            command_data TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            output TEXT,
            exit_code INTEGER,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            duration_ms INTEGER
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_node_command_log_node_uuid ON node_command_log (node_uuid)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_node_command_log_admin_id ON node_command_log (admin_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_node_command_log_started_at ON node_command_log (started_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_node_command_log_command_type ON node_command_log (command_type)")

    # ── node_scripts — built-in and custom scripts catalog ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS node_scripts (
            id SERIAL PRIMARY KEY,
            name VARCHAR(100) NOT NULL UNIQUE,
            display_name VARCHAR(200) NOT NULL,
            description TEXT,
            category VARCHAR(50) NOT NULL DEFAULT 'system',
            script_content TEXT NOT NULL,
            timeout_seconds INTEGER NOT NULL DEFAULT 60,
            requires_root BOOLEAN NOT NULL DEFAULT false,
            is_builtin BOOLEAN NOT NULL DEFAULT false,
            created_by INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_node_scripts_category ON node_scripts (category)")

    # ── node_provision_sessions — VPS provisioning tracking ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS node_provision_sessions (
            id SERIAL PRIMARY KEY,
            admin_id INTEGER,
            admin_username VARCHAR(100),
            target_host VARCHAR(255) NOT NULL,
            target_port INTEGER NOT NULL DEFAULT 22,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            current_step VARCHAR(100),
            steps_completed INTEGER NOT NULL DEFAULT 0,
            steps_total INTEGER NOT NULL DEFAULT 0,
            error_message TEXT,
            node_uuid VARCHAR(255),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_node_provision_sessions_admin_id ON node_provision_sessions (admin_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_node_provision_sessions_status ON node_provision_sessions (status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS node_provision_sessions")
    op.execute("DROP TABLE IF EXISTS node_scripts")
    op.execute("DROP TABLE IF EXISTS node_command_log")
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS agent_v2_last_ping")
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS agent_v2_connected")
