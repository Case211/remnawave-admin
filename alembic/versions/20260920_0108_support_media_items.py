"""Галерея вложений в проекции сообщений тикета.

Revision ID: 0108
Revises: 0107
Create Date: 2026-09-20

Клиент присылает несколько скриншотов одной пачкой. Бот отдаёт её списком
`media_items` (BEDOLAGA-DEV#3269); старые версии поля не присылают, и тогда
колонка просто остаётся пустой — сообщение показывается одним вложением.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0108"
down_revision: Union[str, None] = "0107"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE support_ticket_messages ADD COLUMN IF NOT EXISTS media_items JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE support_ticket_messages DROP COLUMN IF EXISTS media_items")
