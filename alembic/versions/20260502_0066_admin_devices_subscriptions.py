"""Push subscription preferences for admin_devices.

Revision ID: 0066
Revises: 0065
Create Date: 2026-05-02

Что добавляем:
- notifications_enabled (bool, default true) — общий выключатель пушей на этот девайс.
  Удобно когда один и тот же админ хочет получать пуши на телефон, но не на планшет.
- subscriptions (jsonb массив строк) — фильтр по категориям. NULL означает «все»;
  непустой массив означает «только перечисленные» (e.g. ['violations','alerts']).
  Хранится как jsonb, чтобы расширять список типов без миграций.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0066"
down_revision: Union[str, None] = "0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE admin_devices
            ADD COLUMN IF NOT EXISTS notifications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS subscriptions JSONB
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE admin_devices
            DROP COLUMN IF EXISTS notifications_enabled,
            DROP COLUMN IF EXISTS subscriptions
        """
    )
