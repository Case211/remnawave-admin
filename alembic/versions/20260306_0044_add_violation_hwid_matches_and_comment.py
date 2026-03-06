"""Add hwid_matched_users and admin_comment to violations.

Revision ID: 0044
Revises: 0043
Create Date: 2026-03-06
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0044'
down_revision: Union[str, None] = '0043'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # JSONB with matched HWID users: [{"uuid": "...", "username": "...", "hwid": "...", "platform": "..."}]
    op.execute(
        "ALTER TABLE violations ADD COLUMN IF NOT EXISTS hwid_matched_users JSONB"
    )
    # Admin comment when resolving/annulling violation
    op.execute(
        "ALTER TABLE violations ADD COLUMN IF NOT EXISTS admin_comment TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE violations DROP COLUMN IF EXISTS hwid_matched_users")
    op.execute("ALTER TABLE violations DROP COLUMN IF EXISTS admin_comment")
