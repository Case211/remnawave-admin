"""Add users_online column to nodes table.

Revision ID: 0055
Revises: 0054
Create Date: 2026-04-08

Panel API returns usersOnline for each node, but the column was missing
from the database schema, causing errors in dashboard WebSocket queries.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0055"
down_revision: Union[str, None] = "0054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS users_online INTEGER DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS users_online")
