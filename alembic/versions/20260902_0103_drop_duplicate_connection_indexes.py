"""Снять дублирующий набор индексов с user_connections.

Revision ID: 0103
Revises: 0102
Create Date: 2026-09-02

После 0069 таблица партиционирована и несёт индексы idx_uc_part_*. Но схема из
shared/db/_base.py выполняется при каждом старте и заново создавала прежний
набор idx_user_connections_* — те же колонки под другими именами, поэтому
IF NOT EXISTS их не отсекал.

Цена дубля видна на живой установке (7.8 тыс. пользователей, 100+ нод):
disconnected_at входит в оба набора, из-за чего апдейт отключения перестаёт
быть HOT и пишется в двенадцать индексов вместо восьми. За трое суток это
299 ГБ записи при базе в 9.7 ГБ и 511 ГБ WAL с момента создания базы — на
порядок больше самой базы ежедневно.

idx_uc_cleanup снимается по той же причине: старые подключения уходят вместе
с партицией, а не через DELETE по connected_at, поэтому сканов у индекса нет,
и он только утяжеляет запись.

Индексы удаляются на родителе — из партиций они уходят каскадом.
"""
from alembic import op
from sqlalchemy import text


revision = '0103'
down_revision = '0102'
branch_labels = None
depends_on = None


# Дубли партиционных idx_uc_part_user_connected / _user_active / _ip / _node
_DUPLICATE_INDEXES = (
    "idx_user_connections_user",
    "idx_user_connections_ip",
    "idx_user_connections_node",
    "idx_user_connections_user_active",
    "idx_uc_cleanup",
)


def _is_partitioned(conn) -> bool:
    """Партиционирована ли user_connections (то есть накатан ли 0069)."""
    return conn.execute(text(
        "SELECT 1 FROM pg_partitioned_table pt "
        "JOIN pg_class c ON c.oid = pt.partrelid "
        "WHERE c.relname = 'user_connections'"
    )).scalar() is not None


def upgrade() -> None:
    conn = op.get_bind()
    if not _is_partitioned(conn):
        # Таблицу ещё не партиционировали — эти индексы здесь единственные рабочие
        return
    for index_name in _DUPLICATE_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")


def downgrade() -> None:
    conn = op.get_bind()
    if _is_partitioned(conn):
        # Возвращать дубли на партиционированную таблицу нечего: их роль
        # выполняют idx_uc_part_*
        return
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_user ON user_connections(user_uuid, connected_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_ip ON user_connections(ip_address)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_connections_node ON user_connections(node_uuid)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_user_connections_user_active "
        "ON user_connections(user_uuid, disconnected_at, connected_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_uc_cleanup ON user_connections(connected_at) "
        "INCLUDE (id) WHERE disconnected_at IS NOT NULL"
    )
