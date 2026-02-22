"""Add source_url and imported_at fields to node_scripts.

Revision ID: 0031
Revises: 0030
Create Date: 2026-02-22

Tracks where imported scripts came from (GitHub URL)
and when they were imported.
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0031'
down_revision: Union[str, None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE node_scripts ADD COLUMN IF NOT EXISTS source_url TEXT")
    op.execute("ALTER TABLE node_scripts ADD COLUMN IF NOT EXISTS imported_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE node_scripts DROP COLUMN IF EXISTS imported_at")
    op.execute("ALTER TABLE node_scripts DROP COLUMN IF EXISTS source_url")
