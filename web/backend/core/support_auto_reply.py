"""Автоответ клиенту, пока оператор спит.

Когда поддержку держит один человек, ночное обращение всё равно ждёт до утра —
но клиент об этом не знает и сидит в тишине. Робот здесь делает ровно одно:
подтверждает, что обращение принято, и называет час, когда им займутся.

Два правила, из которых всё остальное следует:

* автоответ не считается ответом оператора. Он уходит от имени админа, и без
  отметки очередь решила бы, что человеку уже ответили: ожидание обнулилось бы,
  обращение уехало из «в обработке» в «ждёт клиента» и утром не попалось бы
  оператору на глаза. Поэтому id отправленного сообщения запоминается в
  ``support_auto_replies``, а :func:`derive_fields` его игнорирует.
* один автоответ на обращение. Ключ таблицы по тикету — клиент, написавший
  ночью три сообщения подряд, получит робота один раз.
"""

from __future__ import annotations

import logging
from datetime import datetime, time, timedelta, timezone

logger = logging.getLogger(__name__)

DEFAULT_START = "22:00"
DEFAULT_END = "08:00"
# Отвечаем только на свежее. Первый запуск синка видит всю историю разом, и без
# этого порога робот написал бы каждому, кто когда-либо обращался.
FRESH_MINUTES = 30


def enabled() -> bool:
    from shared.config_service import config_service

    return bool(config_service.get("support_auto_reply_enabled", False))


def _parse_time(value: str | None, fallback: str) -> time:
    raw = str(value or fallback).strip()
    try:
        hours, minutes = raw.split(":")
        return time(hour=int(hours) % 24, minute=int(minutes) % 60)
    except (ValueError, AttributeError):
        logger.warning("Support auto-reply: время «%s» не разобрано, беру %s", raw, fallback)
        hours, minutes = fallback.split(":")
        return time(hour=int(hours), minute=int(minutes))


def _zone():
    """Часовой пояс часов тишины: своя зона, если задана, иначе общая зона панели.

    Неизвестная зона — UTC: ронять автоответ в фоновом цикле из-за опечатки
    в настройке глупо.
    """
    from shared import timefmt
    from shared.config_service import config_service

    name = str(config_service.get("support_quiet_hours_tz", "") or "").strip()
    return timefmt.zone(name) if name else timefmt.display_tz()


def quiet_window() -> tuple[time, time]:
    from shared.config_service import config_service

    start = _parse_time(config_service.get("support_quiet_hours_start", DEFAULT_START), DEFAULT_START)
    end = _parse_time(config_service.get("support_quiet_hours_end", DEFAULT_END), DEFAULT_END)
    return start, end


def in_quiet_hours(moment: datetime | None = None) -> bool:
    """Идут ли сейчас часы тишины. Окно через полночь — обычный случай, а не край."""
    start, end = quiet_window()
    if start == end:
        return False
    local = (moment or datetime.now(timezone.utc)).astimezone(_zone()).time()
    if start < end:
        return start <= local < end
    return local >= start or local < end


def reply_text(ticket_id: int) -> str:
    from shared.config_service import config_service

    _, end = quiet_window()
    template = str(config_service.get("support_auto_reply_text", "") or "").strip()
    if not template:
        return ""
    return template.replace("{id}", str(ticket_id)).replace("{until}", end.strftime("%H:%M"))


async def maybe_auto_reply(ticket: dict) -> bool:
    """Ответить роботом, если обращение пришло в часы тишины.

    Возвращает True, только когда сообщение действительно ушло клиенту. Функция
    идемпотентна: повторный вызов по тому же обращению упрётся в ключ таблицы.
    """
    from shared.bedolaga_client import bedolaga_client
    from shared.database import db_service

    ticket_id = int(ticket.get("id") or 0)
    if not ticket_id or not enabled() or not db_service.is_connected:
        return False
    if not in_quiet_hours():
        return False
    if str(ticket.get("status") or "") == "closed":
        return False
    if any(m.get("is_from_admin") for m in (ticket.get("messages") or [])):
        # Оператор уже отвечал — роботу тут делать нечего.
        return False

    from web.backend.core.support_sync import _parse_dt

    created = _parse_dt(ticket.get("created_at"))
    if created and datetime.now(timezone.utc) - created > timedelta(minutes=FRESH_MINUTES):
        return False

    text = reply_text(ticket_id)
    if not text:
        logger.warning("Support auto-reply: текст пустой, обращение %s остаётся без ответа", ticket_id)
        return False

    # Место занимаем до отправки: два события о том же обращении приходят
    # одновременно чаще, чем кажется.
    async with db_service.acquire() as conn:
        claimed = await conn.fetchrow(
            """
            INSERT INTO support_auto_replies (ticket_id) VALUES ($1)
            ON CONFLICT (ticket_id) DO NOTHING
            RETURNING ticket_id
            """,
            ticket_id,
        )
    if not claimed:
        return False

    try:
        response = await bedolaga_client.reply_ticket(ticket_id, text)
    except Exception as exc:  # noqa: BLE001 — бот недоступен: снимаем бронь, попробуем позже
        logger.warning("Support auto-reply: ответ по %s не ушёл: %s", ticket_id, exc)
        async with db_service.acquire() as conn:
            await conn.execute("DELETE FROM support_auto_replies WHERE ticket_id = $1", ticket_id)
        return False

    message_id = None
    try:
        message_id = int(((response or {}).get("message") or {}).get("id") or 0) or None
    except (TypeError, ValueError):
        message_id = None
    if message_id is None:
        # Без id автоответ не отличить от живого ответа, и обращение уедет в
        # «ждёт клиента». Бот такое поле отдаёт всегда, поэтому просто шумим в
        # лог, а не городим опознание по тексту.
        logger.warning("Support auto-reply: бот не вернул id сообщения по обращению %s", ticket_id)

    async with db_service.acquire() as conn:
        await conn.execute(
            "UPDATE support_auto_replies SET message_id = $2, sent_at = NOW() WHERE ticket_id = $1",
            ticket_id,
            message_id,
        )

    from web.backend.core.support_sync import sync_ticket

    await sync_ticket(ticket_id)

    from web.backend.core.support_alerts import notify_auto_reply

    await notify_auto_reply(ticket_id, ticket.get("customer_name") or ticket.get("title") or "")
    logger.info("Support auto-reply: обращению %s ответил робот", ticket_id)
    return True


async def auto_message_ids(conn, ticket_id: int) -> set[int]:
    """Сообщения обращения, которые написал робот."""
    rows = await conn.fetch(
        "SELECT message_id FROM support_auto_replies WHERE ticket_id = $1 AND message_id IS NOT NULL",
        ticket_id,
    )
    return {int(row["message_id"]) for row in rows}
