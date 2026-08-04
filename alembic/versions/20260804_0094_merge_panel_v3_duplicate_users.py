"""Сливает задвоенных пользователей после перехода панели на v3.

Миграция 0092 добавила users.id (панельный числовой идентификатор), но не
заполнила его — предполагалось, что колонку проставит синк. На деле панель
v3 не отдаёт uuid вообще, поэтому синк уходит в ветку
``INSERT ... ON CONFLICT (id)``, а у всех существующих строк id пустой:
конфликта нет, и вместо обновления вставляется вторая строка с новым uuid
из ``gen_random_uuid()``. В результате каждый пользователь двоится — строка
со всей историей (подключения, нарушения, базлайны, трафик) и вторая,
которую синк с этого момента и обновляет.

Пары ищутся по short_uuid (панель сохраняет его при обновлении), для строк
без него — по username; берутся только однозначные 1:1. Дочерние записи
переезжают на оригинал, панельный id и свежие поля тоже, вторая строка
убирается. История остаётся на месте, а синк дальше попадает
в ON CONFLICT (id) и обновляет нужную строку.

Revision ID: 0094
Revises: 0093
"""
import logging
from typing import Optional, Sequence, Tuple, Union

from alembic import op
from sqlalchemy import text

revision: str = "0094"
down_revision: Union[str, None] = "0093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

# Таблицы с user_uuid: имя, колонки уникального ключа рядом с user_uuid,
# дополнительное условие этого ключа. None — уникального ключа нет,
# перевешивание конфликта не даст. Пустой кортеж — уникален сам user_uuid.
#
# Там, где ключ есть, строка второй записи уступает первой: у оригинала
# данные копились месяцами, у второй строки — с момента обновления панели.
_CHILD_TABLES: Tuple[Tuple[str, Optional[Tuple[str, ...]], str], ...] = (
    # Уникальный индекс частичный: только среди незакрытых подключений.
    ("user_connections", ("ip_address",), "d.disconnected_at IS NULL AND o.disconnected_at IS NULL"),
    ("user_hwid_devices", ("hwid",), ""),
    ("user_baselines", (), ""),
    ("user_node_traffic", ("node_uuid",), ""),
    ("violation_whitelist", (), ""),
    ("violations", None, ""),
    ("torrent_events", None, ""),
    ("subscription_request_history", None, ""),
    ("user_node_traffic_history", None, ""),
)

# Поля, которые переезжают на оригинал: вторая строка синхронизировалась
# с панелью, оригинал стоит с момента обновления. created_at и
# created_by_admin_id остаются от оригинала — там привязка к админу.
_FRESH_COLUMNS: Tuple[str, ...] = (
    "short_uuid", "username", "subscription_uuid", "telegram_id", "email",
    "status", "expire_at", "traffic_limit_bytes", "used_traffic_bytes",
    "hwid_device_limit", "description", "raw_data", "external_squad_uuid", "tag",
)


def _column_exists(conn, table: str, column: str) -> bool:
    return bool(conn.execute(text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar())


def _build_pairs(conn) -> int:
    """Собирает однозначные пары «оригинал → вторая строка»."""
    conn.execute(text("DROP TABLE IF EXISTS _v3_user_merge"))
    conn.execute(text("""
        CREATE TEMP TABLE _v3_user_merge (
            orig_uuid UUID PRIMARY KEY,
            dup_uuid UUID NOT NULL UNIQUE,
            panel_id BIGINT NOT NULL
        )
    """))

    # Только однозначное сопоставление 1:1. Неоднозначное не трогаем —
    # разобрать руками безопаснее, чем склеить не тех.
    for key in ("short_uuid", "username"):
        conn.execute(text(f"""
            INSERT INTO _v3_user_merge (orig_uuid, dup_uuid, panel_id)
            SELECT o.uuid, d.uuid, d.panel_id
            FROM (
                SELECT {key} AS k, min(uuid::text)::uuid AS uuid, count(*) AS n
                FROM users
                WHERE id IS NULL AND {key} IS NOT NULL
                GROUP BY {key}
            ) o
            JOIN (
                SELECT {key} AS k, min(uuid::text)::uuid AS uuid,
                       min(id) AS panel_id, count(*) AS n
                FROM users
                WHERE id IS NOT NULL AND {key} IS NOT NULL
                GROUP BY {key}
            ) d ON d.k = o.k
            WHERE o.n = 1 AND d.n = 1
            ON CONFLICT DO NOTHING
        """))

    return int(conn.execute(text("SELECT count(*) FROM _v3_user_merge")).scalar() or 0)


def _reassign_children(conn) -> None:
    for table, unique_cols, extra_where in _CHILD_TABLES:
        if not _column_exists(conn, table, "user_uuid"):
            continue

        if unique_cols is not None:
            match = "".join(f" AND o.{col} = d.{col}" for col in unique_cols)
            if extra_where:
                match += f" AND {extra_where}"
            conn.execute(text(f"""
                DELETE FROM {table} d
                USING _v3_user_merge m
                WHERE d.user_uuid = m.dup_uuid
                  AND EXISTS (
                      SELECT 1 FROM {table} o
                      WHERE o.user_uuid = m.orig_uuid{match}
                  )
            """))

        mirror = ", user_id = m.panel_id" if _column_exists(conn, table, "user_id") else ""
        moved = conn.execute(text(f"""
            UPDATE {table} d
            SET user_uuid = m.orig_uuid{mirror}
            FROM _v3_user_merge m
            WHERE d.user_uuid = m.dup_uuid
        """)).rowcount
        if moved:
            logger.info("0094: перевешено %s строк в %s", moved, table)


def upgrade() -> None:
    conn = op.get_bind()

    if not _column_exists(conn, "users", "id"):
        return

    pairs = _build_pairs(conn)
    if not pairs:
        conn.execute(text("DROP TABLE IF EXISTS _v3_user_merge"))
        return
    logger.info("0094: найдено %s задвоенных пользователей", pairs)

    _reassign_children(conn)

    fresh = ", ".join(f"{col} = d.{col}" for col in _FRESH_COLUMNS)
    conn.execute(text(f"""
        UPDATE users o
        SET {fresh}, updated_at = NOW()
        FROM _v3_user_merge m
        JOIN users d ON d.uuid = m.dup_uuid
        WHERE o.uuid = m.orig_uuid
    """))

    # Вторую строку убираем до проставления id: на users(id) уникальный индекс.
    conn.execute(text("DELETE FROM users WHERE uuid IN (SELECT dup_uuid FROM _v3_user_merge)"))
    conn.execute(text("""
        UPDATE users o SET id = m.panel_id
        FROM _v3_user_merge m
        WHERE o.uuid = m.orig_uuid
    """))

    conn.execute(text("DROP TABLE IF EXISTS _v3_user_merge"))
    logger.info("0094: слито %s пользователей", pairs)


def downgrade() -> None:
    """Слияние необратимо: вторые строки убраны, их записи перевешены."""
