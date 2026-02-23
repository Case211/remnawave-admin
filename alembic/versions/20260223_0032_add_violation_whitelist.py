"""Add violation_whitelist table.

Revision ID: 0032
Revises: 0031
Create Date: 2026-02-23

Allows excluding specific users from violation detection.
Supports optional expiration (expires_at).
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0032'
down_revision: Union[str, None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS violation_whitelist (
            id BIGSERIAL PRIMARY KEY,
            user_uuid UUID NOT NULL UNIQUE,
            reason TEXT,
            added_by_admin_id BIGINT,
            added_by_username VARCHAR(255),
            added_at TIMESTAMPTZ DEFAULT NOW(),
            expires_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_vw_user_uuid ON violation_whitelist (user_uuid)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_vw_expires ON violation_whitelist (expires_at) WHERE expires_at IS NOT NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_vw_expires")
    op.execute("DROP INDEX IF EXISTS idx_vw_user_uuid")
    op.execute("DROP TABLE IF EXISTS violation_whitelist")
