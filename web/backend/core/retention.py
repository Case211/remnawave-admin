"""Суточная очистка истории по срокам хранения из настроек.

- уведомления и журнал алертов — `notifications_retention_days` (по умолчанию 90);
- журнал аудита — `audit_retention_days` (0 = хранить бессрочно).

Журнал аудита защищён триггером от UPDATE/DELETE (миграция 0119); удаление по
сроку помечает свою транзакцию `app.audit_cleanup`, и триггер его пропускает.
"""
import logging
from typing import Optional

from shared import timefmt

logger = logging.getLogger(__name__)

_last_run: Optional[str] = None


def _days(key: str, default: int) -> int:
    from shared.config_service import config_service
    try:
        return max(0, int(config_service.get(key, default)))
    except (TypeError, ValueError):
        return default


async def cleanup_audit_log(conn, days: int) -> str:
    """Удалить записи журнала старше days дней; 0 — ничего не трогать."""
    if days <= 0:
        return "DELETE 0"
    async with conn.transaction():
        await conn.execute("SET LOCAL app.audit_cleanup = 'on'")
        return await conn.execute(
            "DELETE FROM admin_audit_log WHERE created_at < NOW() - INTERVAL '1 day' * $1", days,
        )


async def run_daily() -> None:
    """Раз в сутки по часам панели; повторный вызов в тот же день — пустой."""
    global _last_run
    today = timefmt.now().strftime("%Y-%m-%d")
    if _last_run == today:
        return
    from shared.database import db_service
    from shared.db_schema import ALERT_RULE_LOG_TABLE
    if not db_service.is_connected:
        return
    notes_days = _days("notifications_retention_days", 90) or 90
    audit_days = _days("audit_retention_days", 0)
    try:
        async with db_service.acquire() as conn:
            notes = await conn.execute(
                "DELETE FROM notifications WHERE created_at < NOW() - INTERVAL '1 day' * $1", notes_days,
            )
            alerts = await conn.execute(
                f"DELETE FROM {ALERT_RULE_LOG_TABLE} WHERE created_at < NOW() - INTERVAL '1 day' * $1", notes_days,
            )
            audit = await cleanup_audit_log(conn, audit_days)
        _last_run = today
        logger.info("Retention cleanup: notifications %s, alert log %s, audit %s", notes, alerts, audit)
    except Exception as e:
        logger.warning("Retention cleanup failed: %s", e)
