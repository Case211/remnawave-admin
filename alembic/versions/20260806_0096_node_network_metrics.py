"""Сетевые метрики ноды: трафик интерфейса, conntrack, давление на TCP.

Revision ID: 0096
Revises: 0095
Create Date: 2026-08-06

Панель уже знает трафик из статистики Xray, но там виден только трафик,
который прошёл через прокси. Атака бьёт по интерфейсу и до Xray не доходит —
её видно только по сырым счётчикам хоста, которые с версии 1.3.0 шлёт агент.

NULL здесь значит «агент таких данных не прислал» (старая версия или нет
доступа к network namespace хоста) — это не то же самое, что ноль.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0096"
down_revision: Union[str, None] = "0095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# BIGINT для скоростей: 10 Гбит/с — это уже 1.25e9 байт/с, в INTEGER не влезет
COLUMNS: tuple[tuple[str, str], ...] = (
    ("net_rx_bps", "BIGINT"),
    ("net_tx_bps", "BIGINT"),
    ("net_rx_pps", "BIGINT"),
    ("net_tx_pps", "BIGINT"),
    ("net_rx_drop_ps", "BIGINT"),
    ("net_tx_drop_ps", "BIGINT"),
    ("conntrack_count", "INTEGER"),
    ("conntrack_max", "INTEGER"),
    ("tcp_established", "INTEGER"),
    ("tcp_syncookies_ps", "INTEGER"),
    ("tcp_listen_drop_ps", "INTEGER"),
)

TABLES = ("nodes", "node_metrics_snapshots")


def upgrade() -> None:
    for table in TABLES:
        for column, sql_type in COLUMNS:
            op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {sql_type}")


def downgrade() -> None:
    for table in TABLES:
        for column, _ in COLUMNS:
            op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS {column}")
