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
    op.add_column("nodes", sa.Column("cpu_usage", sa.Float(), nullable=True))
    op.add_column("nodes", sa.Column("memory_usage", sa.Float(), nullable=True))
    op.add_column("nodes", sa.Column("memory_total_bytes", sa.BigInteger(), nullable=True))
    op.add_column("nodes", sa.Column("memory_used_bytes", sa.BigInteger(), nullable=True))
    op.add_column("nodes", sa.Column("disk_usage", sa.Float(), nullable=True))
    op.add_column("nodes", sa.Column("disk_total_bytes", sa.BigInteger(), nullable=True))
    op.add_column("nodes", sa.Column("disk_used_bytes", sa.BigInteger(), nullable=True))
    op.add_column("nodes", sa.Column("uptime_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "nodes",
        sa.Column(
            "metrics_updated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


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
