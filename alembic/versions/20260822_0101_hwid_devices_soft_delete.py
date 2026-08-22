"""Устройства HWID: помним удалённые.

Revision ID: 0101
Revises: 0100
Create Date: 2026-08-22

Таблица хранила только текущее состояние: устройство отвязали — строка
исчезла. На этом строится обход детекта абуза триалов, пойманный 22.08:
человек удаляет устройство со старого аккаунта, заводит новый (через
email, чтобы не совпал telegram id), цепляет к нему тот же HWID и берёт
свежий триал. Проверка «сколько аккаунтов делят HWID» смотрит на снимок,
а в снимке аккаунт всегда один — порог не берётся никогда.

Теперь отвязка проставляет ``removed_at`` вместо удаления строки, и HWID
помнит всех, кого на нём видели. Повторная привязка к тому же аккаунту
снимает пометку, так что обычный сценарий «переустановил приложение»
ничего не ломает.

Частичный индекс — под запрос «кто ещё сидел на этом HWID»: он всегда
идёт по hwid и почти всегда с оглядкой на removed_at.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0101"
down_revision: Union[str, None] = "0100"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE user_hwid_devices
        ADD COLUMN IF NOT EXISTS removed_at TIMESTAMP WITH TIME ZONE
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS idx_hwid_devices_hwid_removed
        ON user_hwid_devices (hwid, removed_at)
    """)


def downgrade() -> None:
    # Строки отвязанных устройств остаются: без колонки их не отличить от
    # активных, но терять историю на откате хуже, чем показать лишнее.
    op.execute("DROP INDEX IF EXISTS idx_hwid_devices_hwid_removed")
    op.execute("ALTER TABLE user_hwid_devices DROP COLUMN IF EXISTS removed_at")
