"""Свои серверы в мониторинге: флаг is_external у строки nodes.

Revision ID: 0106
Revises: 0105
Create Date: 2026-09-09

Оператор может добавить в Fleet сервер, которого нет в панели Remnawave
(бот, панель, база). Такой сервер живёт той же строкой nodes — агент,
коллектор, метрики и алерты работают как для ноды, — но синк с панелью
его не трогает, а страница нод и счётчики дашборда не показывают.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0106"
down_revision: Union[str, None] = "0105"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ADD COLUMN IF NOT EXISTS is_external BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    # Без флага эти строки стали бы «нодами», которых нет в панели, и синк снёс бы их сам.
    op.execute("DELETE FROM nodes WHERE is_external")
    op.execute("ALTER TABLE nodes DROP COLUMN IF EXISTS is_external")
