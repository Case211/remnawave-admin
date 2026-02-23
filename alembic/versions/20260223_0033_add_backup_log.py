"""Add backup_log table.

Revision ID: 0033
Revises: 0032
Create Date: 2026-02-23

Tracks backup/restore operations with metadata.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0033'
down_revision: Union[str, None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS backup_log (
            id BIGSERIAL PRIMARY KEY,
            filename VARCHAR(512) NOT NULL,
            backup_type VARCHAR(50) NOT NULL DEFAULT 'database',
            size_bytes BIGINT DEFAULT 0,
            status VARCHAR(50) NOT NULL DEFAULT 'completed',
            created_by_admin_id BIGINT,
            created_by_username VARCHAR(255),
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_backup_log_created ON backup_log (created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_backup_log_type ON backup_log (backup_type)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_backup_log_type")
    op.execute("DROP INDEX IF EXISTS idx_backup_log_created")
    op.execute("DROP TABLE IF EXISTS backup_log")
