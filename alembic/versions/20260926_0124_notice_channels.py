"""Каналы и отдельное письмо у шаблонов предупреждений.

Revision ID: 0124
Revises: 0123

Раньше Telegram уходил всегда, а флаг «и на почту» лишь добавлял письмо.
Теперь каналы равноправны: у шаблона два выключателя, Telegram и Email, и
предупреждение идёт строго по отмеченным. Письму — свой HTML: у Telegram
урезанная разметка и живые переносы строк, письму нужна обычная вёрстка.
Пустой HTML — письмо собирается из текста Telegram, как раньше.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0124"
down_revision: Union[str, None] = "0123"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE violation_notice_templates "
        "ADD COLUMN IF NOT EXISTS send_telegram BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute("ALTER TABLE violation_notice_templates ADD COLUMN IF NOT EXISTS email_html_ru TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE violation_notice_templates DROP COLUMN IF EXISTS email_html_ru")
    op.execute("ALTER TABLE violation_notice_templates DROP COLUMN IF EXISTS send_telegram")
