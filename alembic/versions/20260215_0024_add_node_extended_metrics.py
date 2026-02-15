"""Add extended node metrics columns (cpu_cores, disk I/O speeds).

Revision ID: 0024
Revises: 0023
Create Date: 2026-02-15

Adds columns for CPU core count and disk read/write speeds
collected by the Node Agent v2.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '0024'
down_revision: Union[str, None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS cpu_cores INTEGER")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS disk_read_speed_bps BIGINT DEFAULT 0")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS disk_write_speed_bps BIGINT DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS disk_write_speed_bps")
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS disk_read_speed_bps")
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS cpu_cores")
