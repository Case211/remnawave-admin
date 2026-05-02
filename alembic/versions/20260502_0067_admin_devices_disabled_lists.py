"""Add explicit disabled_categories / disabled_events to admin_devices.

Revision ID: 0067
Revises: 0066
Create Date: 2026-05-02

Старый `subscriptions` (jsonb массив-whitelist) оставляем для обратной
совместимости с уже установленными клиентами. Новый клиент пишет в эти
два явных списка-блеклиста — это позволяет точечно отключать конкретные
event_id (например `user.expires_in_72_hours`) без потери остальных событий
той же категории.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0067"
down_revision: Union[str, None] = "0066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE admin_devices
            ADD COLUMN IF NOT EXISTS disabled_categories JSONB NOT NULL DEFAULT '[]'::jsonb,
            ADD COLUMN IF NOT EXISTS disabled_events JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE admin_devices
            DROP COLUMN IF EXISTS disabled_categories,
            DROP COLUMN IF EXISTS disabled_events
        """
    )
