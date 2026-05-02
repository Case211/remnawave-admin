"""Add admin_devices for FCM push tokens.

Revision ID: 0065
Revises: 0064
Create Date: 2026-05-02

Admins зарегистрированных мобильных приложений хранят свои FCM-токены
здесь. Один админ может иметь несколько устройств (телефон + планшет).
fcm_token — UNIQUE: при переустановке приложения Firebase выдаст новый,
а старый вычистим по 404 от FCM либо по последнему last_seen_at.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0065"
down_revision: Union[str, None] = "0064"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_devices (
            id            BIGSERIAL PRIMARY KEY,
            admin_id      INTEGER NOT NULL REFERENCES admin_accounts(id) ON DELETE CASCADE,
            fcm_token     TEXT NOT NULL UNIQUE,
            platform      VARCHAR(16) NOT NULL DEFAULT 'android',
            app_version   VARCHAR(32),
            device_label  VARCHAR(128),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_seen_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_admin_devices_admin_id ON admin_devices(admin_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS admin_devices")
