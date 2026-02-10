"""Add user_hwid_devices table for storing HWID devices.

Revision ID: 0008
Revises: 0007
Create Date: 2026-02-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_hwid_devices (
            id BIGSERIAL PRIMARY KEY,
            user_uuid UUID NOT NULL,
            hwid VARCHAR(255) NOT NULL,
            platform VARCHAR(50),
            os_version VARCHAR(100),
            app_version VARCHAR(50),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_hwid_devices_user_hwid ON user_hwid_devices (user_uuid, hwid)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hwid_devices_user_uuid ON user_hwid_devices (user_uuid)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_hwid_devices_platform ON user_hwid_devices (platform)")


def downgrade() -> None:
    op.drop_index('idx_hwid_devices_platform', table_name='user_hwid_devices')
    op.drop_index('idx_hwid_devices_user_uuid', table_name='user_hwid_devices')
    op.drop_index('idx_hwid_devices_user_hwid', table_name='user_hwid_devices')
    op.drop_table('user_hwid_devices')
