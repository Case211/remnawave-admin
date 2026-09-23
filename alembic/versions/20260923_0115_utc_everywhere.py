"""Единое время: в базе только UTC с поясом, время отчётов — по зоне отображения.

Revision ID: 0115
Revises: 0114
Create Date: 2026-09-23

1. Колонки TIMESTAMP без пояса (финансовый модуль) становятся TIMESTAMPTZ.
   NOW() писал в них время сессии Postgres — в наших образах это UTC, поэтому
   старые значения читаются как UTC. Колонку, которую не удалось перевести
   (например, на неё опирается представление), пропускаем с предупреждением,
   а не валим всю миграцию.

2. Время отчётов и авто-бэкапа раньше задавалось в UTC, теперь — в зоне из
   настройки display_timezone (по умолчанию Europe/Moscow, UTC+3). Чтобы
   расписания не сдвинулись, заданное вручную время переводим из UTC в Москву;
   если отчёт при этом переезжает через полночь, сдвигаем и день недели
   (для ежемесячного — день месяца, в пределах 1–28).
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0115"
down_revision: Union[str, None] = "0114"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Смещение Москвы от UTC: зона по умолчанию, летнего времени в ней нет
_MSK_HOURS = 3


#: Настройки времени расписаний → настройка дня, которая сдвигается вместе с ним
_TIME_KEYS = {
    "reports_daily_time": None,
    "reports_weekly_time": "reports_weekly_day",
    "reports_monthly_time": "reports_monthly_day",
    "backup_auto_time": None,
}


def _get(conn, key):
    return conn.exec_driver_sql("SELECT value FROM bot_config WHERE key = %(k)s", {"k": key}).scalar()


def _set(conn, key, value):
    conn.exec_driver_sql("UPDATE bot_config SET value = %(v)s WHERE key = %(k)s", {"v": value, "k": key})


def _shift(conn, time_key, day_key, hours_delta):
    """Сдвинуть заданное вручную время; перескочили полночь — сдвинуть и день."""
    raw = _get(conn, time_key)
    if not raw:
        return  # не задано вручную — берётся значение по умолчанию
    try:
        hours, minutes = (int(part) for part in str(raw).strip().split(":"))
    except ValueError:
        return
    total = hours + hours_delta
    _set(conn, time_key, f"{total % 24:02d}:{minutes:02d}")
    day_delta = total // 24  # +1 — на следующий день, -1 — на предыдущий
    if not day_delta or not day_key:
        return
    day = _get(conn, day_key)
    if day_key == "reports_weekly_day":
        _set(conn, day_key, str((int(day or 0) + day_delta) % 7))
    else:
        _set(conn, day_key, str((int(day or 1) - 1 + day_delta) % 28 + 1))


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE c record;
        BEGIN
            FOR c IN
                SELECT cols.table_name, cols.column_name
                FROM information_schema.columns cols
                JOIN information_schema.tables t
                  ON t.table_schema = cols.table_schema AND t.table_name = cols.table_name
                WHERE cols.table_schema = current_schema()
                  AND cols.data_type = 'timestamp without time zone'
                  AND t.table_type = 'BASE TABLE'
            LOOP
                BEGIN
                    EXECUTE format(
                        'ALTER TABLE %I ALTER COLUMN %I TYPE TIMESTAMPTZ USING %I AT TIME ZONE ''UTC''',
                        c.table_name, c.column_name, c.column_name
                    );
                EXCEPTION WHEN others THEN
                    RAISE WARNING 'utc_everywhere: %.% не переведена в TIMESTAMPTZ: %',
                        c.table_name, c.column_name, SQLERRM;
                END;
            END LOOP;
        END $$;
        """
    )

    conn = op.get_bind()
    for time_key, day_key in _TIME_KEYS.items():
        _shift(conn, time_key, day_key, _MSK_HOURS)

    # Тихие часы поддержки без своей зоны теперь идут по общей. Строки настроек
    # при старте не перезаписываются, поэтому старый дефолт «UTC» убираем здесь;
    # зону, которую админ выбрал сам (value), не трогаем.
    op.execute("UPDATE bot_config SET default_value = '' WHERE key = 'support_quiet_hours_tz'")


def downgrade() -> None:
    # Тип колонок назад не возвращаем: TIMESTAMPTZ старый код читает так же.
    # Время расписаний переводим обратно в UTC.
    conn = op.get_bind()
    for time_key, day_key in _TIME_KEYS.items():
        _shift(conn, time_key, day_key, -_MSK_HOURS)
