"""Add system metrics columns to nodes table.

Revision ID: 0010
Revises: 0009
Create Date: 2026-02-10

Stores CPU, memory, disk metrics and uptime collected by Node Agent.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS cpu_usage FLOAT")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS memory_usage FLOAT")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS memory_total_bytes BIGINT")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS memory_used_bytes BIGINT")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS disk_usage FLOAT")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS disk_total_bytes BIGINT")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS disk_used_bytes BIGINT")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS uptime_seconds INTEGER")
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS metrics_updated_at TIMESTAMPTZ")


def downgrade() -> None:
    op.drop_column("nodes", "metrics_updated_at")
    op.drop_column("nodes", "uptime_seconds")
    op.drop_column("nodes", "disk_used_bytes")
    op.drop_column("nodes", "disk_total_bytes")
    op.drop_column("nodes", "disk_usage")
    op.drop_column("nodes", "memory_used_bytes")
    op.drop_column("nodes", "memory_total_bytes")
    op.drop_column("nodes", "memory_usage")
    op.drop_column("nodes", "cpu_usage")
