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
from html import escape

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


def _ticket_button(ticket_id: int) -> dict | None:
    """Кнопка «Открыть обращение» под уведомлением в Telegram.

    Внутрипанельный путь в чате бесполезен — нужен абсолютный адрес, а его
    знает только настройка «Публичный URL панели». Telegram принимает в кнопке
    исключительно https и отклоняет всё сообщение целиком, если адрес не
    подошёл, поэтому на пустой или http-настройке кнопки просто нет: лучше
    уведомление без ссылки, чем молчание.
    """
    from shared.config_service import config_service

    base = str(config_service.get("web_panel_public_url", "") or "").strip().rstrip("/")
    if not base.startswith("https://"):
        return None
    return {
        "inline_keyboard": [
            [{"text": "🔎 Открыть обращение", "url": f"{base}/support?ticket={ticket_id}"}]
        ]
    }


async def _notify(
    title: str,
    body: str,
    *,
    severity: str,
    group_key: str,
    ticket_id: int,
    telegram_body: str | None = None,
) -> None:
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
            reply_markup=_ticket_button(ticket_id),
            telegram_body=telegram_body,
        )
    except Exception as exc:  # noqa: BLE001 — алерт не должен ронять синк
        logger.warning("Support alert не отправлен (%s): %s", group_key, exc)


def escape_line(line: str) -> str:
    """Строка контекста наполовину наша, наполовину из бота — экранируем целиком."""
    return escape(line)


def _short(text: str, limit: int = 300) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def _ticket_row(ticket_id: int) -> dict:
    """Строка проекции: событие бота приносит не все поля, которые нужны в письме."""
    from shared.database import db_service

    if not db_service.is_connected:
        return {}
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT t.*,
                       (SELECT COUNT(*) FROM support_ticket_messages m
                         WHERE m.ticket_id = t.id AND m.has_media) AS attachments
                FROM support_tickets t WHERE t.id = $1
                """,
                ticket_id,
            )
        return dict(row) if row else {}
    except Exception as exc:  # noqa: BLE001 — уведомление важнее полноты карточки
        logger.debug("Support alert: проекция по %s не прочиталась: %s", ticket_id, exc)
        return {}


async def _customer_lines(bot_user_id: int) -> list[str]:
    """Подписка, баланс, устройства — то, чего в уведомлении бота нет.

    Бот шлёт свою карточку тикета, и повторять её смысла нет: ценность нашего
    письма в том, что мы знаем про клиента то, что видно в панели.
    """
    if not bot_user_id:
        return []
    from shared.bedolaga_client import bedolaga_client

    try:
        user = await bedolaga_client.get_user(bot_user_id)
    except Exception as exc:  # noqa: BLE001 — бот недоступен: обойдёмся без контекста
        logger.debug("Support alert: клиент %s не прочитался: %s", bot_user_id, exc)
        return []

    lines: list[str] = []
    subscription = (user or {}).get("subscription") or {}
    if subscription:
        status = str(subscription.get("actual_status") or subscription.get("status") or "")
        end = str(subscription.get("end_date") or "")[:10]
        parts = [SUBSCRIPTION_STATUS.get(status, status or "—")]
        if end:
            parts.append(f"до {end}")
        if subscription.get("is_trial"):
            parts.append("триал")
        if subscription.get("device_limit"):
            parts.append(f"устройств: {subscription['device_limit']}")
        lines.append("💳 Подписка: " + " · ".join(parts))
    else:
        lines.append("💳 Подписки нет")

    balance = (user or {}).get("balance_rubles")
    if balance is not None:
        lines.append(f"💰 Баланс: {balance} ₽")
    return lines


SUBSCRIPTION_STATUS = {
    "active": "активна",
    "expired": "истекла",
    "disabled": "отключена",
    "trial": "триал",
}


async def notify_new_ticket(ticket: dict) -> None:
    """Клиент создал обращение — сказать сразу, пока он ещё в чате.

    В чат уходит карточка: кто написал, о чём, с чем пришёл и что у него с
    подпиской. Одной строки «имя: тема» оператору не хватало — чтобы понять,
    срочное ли это, всё равно приходилось открывать панель.
    """
    if not new_ticket_alerts_enabled():
        return
    ticket_id = int(ticket.get("id") or 0)
    if not ticket_id:
        return

    row = await _ticket_row(ticket_id)
    data = {**ticket, **row}
    customer = str(data.get("customer_name") or "") or f"#{data.get('bot_user_id') or '—'}"
    title = str(data.get("title") or "без темы")

    lines = [f"👤 <b>{escape(customer)}</b>"]
    telegram_id = data.get("telegram_id")
    channel = f"Telegram {telegram_id}" if telegram_id else "кабинет"
    lines.append(f"🆔 Клиент #{data.get('bot_user_id') or '—'} · {escape(channel)}")
    lines.append(f"📝 {escape(title)}")

    message = _short(data.get("last_message_text") or "")
    if message:
        lines.append(f"💬 {escape(message)}")
    attachments = int(data.get("attachments") or 0)
    if attachments:
        lines.append(f"📎 Вложений: {attachments}")

    context = await _customer_lines(int(data.get("bot_user_id") or 0))
    if context:
        lines.append("")
        lines.extend(escape_line(line) for line in context)

    await _notify(
        f"Новое обращение #{ticket_id}",
        f"{customer}: {title}",
        severity="info",
        group_key=f"support_new_{ticket_id}",
        ticket_id=ticket_id,
        telegram_body="\n".join(lines),
    )


async def notify_auto_reply(ticket_id: int, customer: str) -> None:
    """Робот ответил за оператора — сказать об этом, но не тревожным тоном.

    Уведомление уходит обычным порядком: спящий телефон его всё равно не
    покажет, а утром в ленте видно, что клиент не остался в тишине.
    """
    if not alerts_enabled():
        return
    await _notify(
        f"Автоответ по обращению #{ticket_id}",
        f"{customer or 'клиент'} написал в часы тишины — робот подтвердил приём, ответ за вами.",
        severity="info",
        group_key=f"support_auto_{ticket_id}",
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
