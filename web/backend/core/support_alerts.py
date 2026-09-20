"""Алерты поддержки: новое обращение и просроченный первый ответ.

Два повода дёрнуть оператора, и у каждого своя цена ошибки. О новом обращении
лучше сказать сразу — клиент ждёт. О просрочке нельзя говорить дважды: тикет
висит часами, и алерт на каждом круге превратился бы в шум, поэтому дедуп идёт
по ``group_key`` уведомления и по отметке в памяти процесса.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

SLA_CHECK_INTERVAL_SECONDS = 60
DEFAULT_SLA_MINUTES = 30

# Тикеты, по которым просрочка уже объявлена. Сбрасывается при рестарте — тогда
# уведомление повторится один раз, что лучше молчания.
_sla_alerted: set[int] = set()


def sla_minutes() -> int:
    from shared.config_service import config_service

    try:
        return max(1, int(config_service.get("support_sla_minutes", DEFAULT_SLA_MINUTES) or DEFAULT_SLA_MINUTES))
    except (TypeError, ValueError):
        return DEFAULT_SLA_MINUTES


def sla_enabled() -> bool:
    """Контроль срока ответа целиком: очередь, подсветка, алерты о просрочке.

    Выключатель отдельный от алертов: кому-то нужны уведомления о новых
    обращениях, но не нужна гонка за таймером.
    """
    from shared.config_service import config_service

    return bool(config_service.get("support_sla_enabled", True))


def alerts_enabled() -> bool:
    from shared.config_service import config_service

    return bool(config_service.get("support_alerts_enabled", True))


def new_ticket_alerts_enabled() -> bool:
    from shared.config_service import config_service

    return alerts_enabled() and bool(config_service.get("support_alert_new_ticket", True))


async def _notify(title: str, body: str, *, severity: str, group_key: str, ticket_id: int) -> None:
    try:
        from web.backend.core.notification_service import create_notification

        await create_notification(
            title=title,
            body=body,
            type="alert",
            severity=severity,
            channels=["in_app", "telegram"],
            topic_type="service",
            source="support",
            source_id=str(ticket_id),
            group_key=group_key,
            link=f"/support?ticket={ticket_id}",
        )
    except Exception as exc:  # noqa: BLE001 — алерт не должен ронять синк
        logger.warning("Support alert не отправлен (%s): %s", group_key, exc)


async def notify_new_ticket(ticket: dict) -> None:
    """Клиент создал обращение — сказать сразу, пока он ещё в чате."""
    if not new_ticket_alerts_enabled():
        return
    ticket_id = int(ticket.get("id") or 0)
    if not ticket_id:
        return
    customer = ticket.get("customer_name") or ticket.get("user_id") or "клиент"
    await _notify(
        f"Новое обращение #{ticket_id}",
        f"{customer}: {ticket.get('title') or 'без темы'}",
        severity="info",
        group_key=f"support_new_{ticket_id}",
        ticket_id=ticket_id,
    )


async def check_sla_breaches() -> int:
    """Найти обращения, где клиент ждёт дольше порога, и предупредить один раз."""
    from shared.database import db_service

    if not sla_enabled() or not alerts_enabled() or not db_service.is_connected:
        return 0

    threshold = datetime.now(timezone.utc) - timedelta(minutes=sla_minutes())
    alerted = list(_sla_alerted)
    async with db_service.acquire() as conn:
        # Уже объявленные отсекаем в SQL: иначе полсотни старых висяков занимали
        # бы всю страницу, и свежая просрочка не дождалась бы алерта никогда.
        rows = await conn.fetch(
            """
            SELECT t.id, t.title, t.customer_name, t.waiting_since
            FROM support_tickets t
            LEFT JOIN support_snoozes s ON s.ticket_id = t.id
            WHERE t.status <> 'closed'
              AND t.waiting_since IS NOT NULL
              AND t.waiting_since < $1
              AND (s.snooze_to IS NULL OR s.snooze_to <= NOW())
              AND NOT (t.id = ANY($2::bigint[]))
            ORDER BY t.waiting_since ASC
            LIMIT 50
            """,
            threshold, alerted,
        )
        # Отметку снимаем только с тех, кто перестал ждать — по всему списку
        # объявленных, а не по одной странице выборки.
        still_waiting = await conn.fetch(
            """
            SELECT t.id
            FROM support_tickets t
            WHERE t.id = ANY($1::bigint[])
              AND t.status <> 'closed'
              AND t.waiting_since IS NOT NULL
            """,
            alerted,
        ) if alerted else []

    _sla_alerted.intersection_update({int(r["id"]) for r in still_waiting})

    sent = 0
    for row in rows:
        ticket_id = int(row["id"])
        waited = int((datetime.now(timezone.utc) - row["waiting_since"]).total_seconds() // 60)
        await _notify(
            f"Обращение #{ticket_id} без ответа {waited} мин",
            f"{row['customer_name'] or 'клиент'}: {row['title'] or 'без темы'}",
            severity="warning",
            group_key=f"support_sla_{ticket_id}",
            ticket_id=ticket_id,
        )
        _sla_alerted.add(ticket_id)
        sent += 1

    return sent


async def support_alerts_loop() -> None:
    """Раз в минуту проверяем просрочки. Падение круга не убивает цикл."""
    while True:
        try:
            await check_sla_breaches()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Support alerts: круг проверки упал: %s", exc, exc_info=True)
        await asyncio.sleep(SLA_CHECK_INTERVAL_SECONDS)
