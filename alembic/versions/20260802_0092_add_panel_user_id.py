"""Добавляет панельный числовой id пользователя (Remnawave v3).

Remnawave v3.0.0 убрал uuid из API пользователей: пользователи
идентифицируются числовым id. Локальный uuid остаётся первичным ключом
нашей БД (для v3-синка uuid генерируется на нашей стороне), а панельный
id хранится в users.id и зеркалится в дочерние таблицы как user_id.
Заполнение колонок делает синк (после подключения к панели v3).

Revision ID: 0092
Revises: 0091
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0092"
down_revision: Union[str, None] = "0091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Дочерние таблицы с user_uuid, которым нужен зеркальный user_id.
# violation_reports пропущен — это агрегатные отчёты без user_uuid.
_CHILD_TABLES: tuple[str, ...] = (
    "user_connections",
    "user_hwid_devices",
    "violations",
    "violation_whitelist",
    "torrent_events",
    "subscription_request_history",
    "user_baselines",
    "user_node_traffic_history",
    "user_node_traffic",
)


def _table_exists(conn, table: str) -> bool:
    return bool(conn.execute(text(f"SELECT to_regclass('public.{table}') IS NOT NULL")).scalar())


def upgrade() -> None:
    conn = op.get_bind()

    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS id BIGINT")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id ON users(id)")

    # Для синка с v3 (uuid в ответах панели отсутствует) локальный uuid
    # генерируется автоматически.
    op.execute("ALTER TABLE users ALTER COLUMN uuid SET DEFAULT gen_random_uuid()")

    for table in _CHILD_TABLES:
        if not _table_exists(conn, table):
            continue
        op.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id BIGINT")
        op.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_user_id ON {table}(user_id)")


def downgrade() -> None:
    conn = op.get_bind()

    for table in reversed(_CHILD_TABLES):
        if not _table_exists(conn, table):
            continue
        op.execute(f"DROP INDEX IF EXISTS idx_{table}_user_id")
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS user_id")

    op.execute("ALTER TABLE users ALTER COLUMN uuid DROP DEFAULT")
    op.execute("DROP INDEX IF EXISTS idx_users_id")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS id")
