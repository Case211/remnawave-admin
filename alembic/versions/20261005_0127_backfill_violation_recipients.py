"""Восстановить адресатов нарушений, потерянных при сборе.

Revision ID: 0127
Revises: 0126

Сборщик получает пользователя в формате API (``telegramId``), но читал
``telegram_id``. Поэтому Telegram ID не попадал в нарушения, ручное
предупреждение возвращало ``no_recipient``, а отложенная мера после
предупреждения не ставилась в очередь. Новые записи исправляет сборщик;
эта миграция восстанавливает уже существующие снимки из локальной таблицы
пользователей.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0127"
down_revision: Union[str, None] = "0126"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE violations AS v
           SET telegram_id = COALESCE(v.telegram_id, u.telegram_id),
               email = COALESCE(v.email, u.email)
          FROM users AS u
         WHERE v.user_uuid = u.uuid
           AND ((v.telegram_id IS NULL AND u.telegram_id IS NOT NULL)
             OR (v.email IS NULL AND u.email IS NOT NULL))
        """
    )


def downgrade() -> None:
    # Data repair is intentionally irreversible: old rows do not identify
    # which values were absent because of the collector bug.
    pass
