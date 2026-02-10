"""Add missing device_model and user_agent columns to user_hwid_devices.

The initial migration 0008 omitted these columns, but the application code
(upsert_hwid_device, sync_user_hwid_devices) references them in INSERT/UPDATE
statements. This caused all webhook-driven device upserts to fail silently,
leaving user_hwid_devices empty and HWID counts showing 0 in the web panel.

Revision ID: 0016
Revises: 0015
Create Date: 2026-02-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = '0016'
down_revision: Union[str, None] = '0015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_hwid_devices
        ADD COLUMN IF NOT EXISTS device_model VARCHAR(255),
        ADD COLUMN IF NOT EXISTS user_agent TEXT
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE user_hwid_devices DROP COLUMN IF EXISTS user_agent")
    op.execute("ALTER TABLE user_hwid_devices DROP COLUMN IF EXISTS device_model")
