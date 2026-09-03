"""fillfactor 90 для user_connections: апдейты активных соединений должны быть HOT.

Revision ID: 0105
Revises: 0104
Create Date: 2026-09-03

Каждый цикл синка переписывает device_info у всех активных соединений, а
закрытие ставит disconnected_at. На живой установке за месяц вышло 7,2 млн
апдейтов на 245 тыс. строк, из них HOT — 0,03 %: партиция заполняется
вставками под завязку, новой версии строки не находится места на той же
странице, и каждый апдейт дописывает все пять индексов. Запас в 10 % на
странице возвращает HOT всем апдейтам, не трогающим индексированные колонки,
то есть всем, кроме закрытия.

Партиционированный родитель fillfactor не принимает — ставим на каждую
партицию, включая созданные заранее пустые; будущие получают его при
создании (ensure_connection_partitions). Без 0069 таблица обычная — ставим
на неё саму. Уже заполненные страницы это не переупаковывает: место на них
появится по мере того, как autovacuum вычистит старые версии.
"""
from alembic import op
from sqlalchemy import text


revision = '0105'
down_revision = '0104'
branch_labels = None
depends_on = None

FILLFACTOR = 90


def _targets(conn) -> list:
    partitions = conn.execute(text(
        "SELECT c.relname FROM pg_inherits i "
        "JOIN pg_class c ON c.oid = i.inhrelid "
        "JOIN pg_class p ON p.oid = i.inhparent "
        "WHERE p.relname = 'user_connections'"
    )).scalars().all()
    if partitions:
        return list(partitions)
    plain = conn.execute(text(
        "SELECT 1 FROM pg_class WHERE relname = 'user_connections' AND relkind = 'r'"
    )).scalar()
    return ["user_connections"] if plain else []


def upgrade() -> None:
    for name in _targets(op.get_bind()):
        op.execute(f"ALTER TABLE {name} SET (fillfactor = {FILLFACTOR})")


def downgrade() -> None:
    for name in _targets(op.get_bind()):
        op.execute(f"ALTER TABLE {name} RESET (fillfactor)")
