"""Отметки об автоответах в часы тишины.

Revision ID: 0109
Revises: 0108
Create Date: 2026-09-20

Автоответ уходит клиенту от имени админа, и без отметки очередь считала бы его
настоящим ответом: ожидание обнулялось бы, а ночное обращение уезжало из «в
обработке» в «ждёт клиента» — то есть пряталось от единственного оператора.
Здесь запоминаем, какое сообщение отправил робот, чтобы исключать его из
расчёта ожидания и из метрики первого ответа. Ключ по тикету заодно страхует
от второго автоответа на то же обращение.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0109"
down_revision: Union[str, None] = "0108"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS support_auto_replies (
            ticket_id  BIGINT PRIMARY KEY REFERENCES support_tickets(id) ON DELETE CASCADE,
            message_id BIGINT,
            sent_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS support_auto_replies")
