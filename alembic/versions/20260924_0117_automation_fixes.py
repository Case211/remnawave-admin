"""Автоматизации: замок срабатывания по цели, cron в зоне панели, чистка полей.

Revision ID: 0117
Revises: 0116

1. automation_trigger_locks — замок срабатывания на пару «правило + цель».
   Раньше замок стоял на правило целиком: второе нарушение в пределах 30 с
   молча терялось, а из нескольких упавших нод уведомляли об одной.

2. Метрика «аптайм ноды, %» убрана — она была фиктивной (100 или 0).
   Правила с ней выключаются, а не удаляются: админ увидит их и решит сам.

3. Поля условий приводятся к тем, что реально приходят в данных:
   online_count → users_online. Условие «дней с истечения» у очистки истёкших
   удаляется — оно дублировало older_than_days и никогда не выполнялось.

4. Cron правил раньше считался в UTC, теперь — в зоне из display_timezone
   (как отчёты и бэкапы после 0115). Чтобы правила не сдвинулись, фиксированные
   часы переводим из UTC в эту зону; при переходе через полночь сдвигаем и
   день недели. Выражения, которые так не перевести (фиксированный день месяца
   с переходом через полночь, шаги по часам), оставляем и пишем в лог.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op

revision: str = "0117"
down_revision: Union[str, None] = "0116"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.0117")


def _zone_offset_hours(conn) -> int:
    """Смещение зоны отображения от UTC сейчас, целыми часами."""
    name = conn.exec_driver_sql(
        "SELECT value FROM bot_config WHERE key = 'display_timezone'"
    ).scalar() or "Europe/Moscow"
    try:
        from zoneinfo import ZoneInfo
        offset = datetime.now(ZoneInfo(str(name))).utcoffset()
    except Exception:
        return 3
    return int(offset.total_seconds() // 3600) if offset else 0


def _shift_cron(expr: str, delta: int):
    """UTC-cron → cron в зоне со смещением delta часов; None — не переводится."""
    parts = expr.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts
    if not hour.replace(",", "").isdigit():
        return expr if hour == "*" else None  # «каждый час» не зависит от зоны
    hours = [int(h) for h in hour.split(",")]
    shifted = [h + delta for h in hours]
    day_moves = {s // 24 for s in shifted}
    new_hour = ",".join(str(s % 24) for s in shifted)
    if day_moves == {0}:
        return " ".join([minute, new_hour, dom, month, dow])
    if len(day_moves) != 1 or dom != "*":
        return None
    move = day_moves.pop()
    if dow == "*":
        return " ".join([minute, new_hour, dom, month, dow])
    if not dow.replace(",", "").isdigit():
        return None
    new_dow = ",".join(str((int(d) % 7 + move) % 7) for d in dow.split(","))
    return " ".join([minute, new_hour, dom, month, new_dow])


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS automation_trigger_locks (
            rule_id INTEGER NOT NULL REFERENCES automation_rules(id) ON DELETE CASCADE,
            target TEXT NOT NULL,
            last_triggered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (rule_id, target)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_automation_trigger_locks_time "
        "ON automation_trigger_locks (last_triggered_at)"
    )

    op.execute("""
        UPDATE automation_rules SET is_enabled = false, updated_at = NOW()
        WHERE trigger_type = 'threshold' AND trigger_config->>'metric' = 'node_uptime_percent'
    """)

    conn = op.get_bind()
    delta = _zone_offset_hours(conn)
    rows = conn.exec_driver_sql(
        "SELECT id, trigger_type, trigger_config::text, conditions::text, action_type FROM automation_rules"
    ).fetchall()
    for rule_id, trigger_type, trigger_raw, conditions_raw, action_type in rows:
        trigger = json.loads(trigger_raw or "{}")
        conditions = json.loads(conditions_raw or "[]")
        changed = False

        new_conditions = []
        for cond in conditions if isinstance(conditions, list) else []:
            field = cond.get("field")
            if field == "online_count":
                cond = {**cond, "field": "users_online"}
                changed = True
            elif field in ("expired_days", "days_expired") and action_type == "cleanup_expired":
                changed = True
                continue
            new_conditions.append(cond)

        cron = trigger.get("cron")
        if trigger_type == "schedule" and cron and delta:
            shifted = _shift_cron(str(cron).strip(), delta)
            if shifted is None:
                logger.warning("0117: cron %r правила %s не переведён в зону панели", cron, rule_id)
            elif shifted != cron:
                trigger = {**trigger, "cron": shifted}
                changed = True

        if changed:
            conn.exec_driver_sql(
                "UPDATE automation_rules SET trigger_config = %(t)s::jsonb, conditions = %(c)s::jsonb, "
                "updated_at = %(u)s WHERE id = %(id)s",
                {"t": json.dumps(trigger), "c": json.dumps(new_conditions),
                 "u": datetime.now(timezone.utc), "id": rule_id},
            )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS automation_trigger_locks")
