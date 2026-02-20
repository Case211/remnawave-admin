"""Add HWID index for cross-account lookups and hwid_score to violations.

Revision ID: 0029
Revises: 0028
Create Date: 2026-02-21
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0029'
down_revision: Union[str, None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_hwid_devices_hwid ON user_hwid_devices(hwid)"
    )
    op.execute(
        "ALTER TABLE violations ADD COLUMN IF NOT EXISTS hwid_score FLOAT"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_hwid_devices_hwid")
    op.execute("ALTER TABLE violations DROP COLUMN IF EXISTS hwid_score")
