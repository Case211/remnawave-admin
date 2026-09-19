"""Живая подписка на события тикетов Bedolaga.

Бот отдаёт события по своему WebSocket (`/ws?token=…`): `ticket.created`,
`ticket.message_added`, `ticket.status_changed`. Догоняющий синк раз в пять
минут для переписки слишком медленный — оператор должен видеть сообщение
клиента сразу, поэтому событие лишь дёргает точечный :func:`sync_ticket`.

Сокет — не гарантия: разрывы, перезапуск бота, старая версия без событий. Всё,
что здесь может сломаться, приводит к молчанию, а не к потере данных: круг
синка всё равно заберёт изменения.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging

logger = logging.getLogger(__name__)

RECONNECT_MIN_SECONDS = 5
RECONNECT_MAX_SECONDS = 300
TICKET_EVENTS = {"ticket.created", "ticket.message_added", "ticket.status_changed"}


def _ws_url() -> str | None:
    """ws(s)://host/ws?token=… из настроек Bedolaga API; None — не настроено."""
    from web.backend.core.config import get_web_settings

    settings = get_web_settings()
    base = (settings.bedolaga_api_url or "").strip().rstrip("/")
    token = (settings.bedolaga_api_token or "").strip()
    if not base or not token:
        return None

    if base.startswith("https://"):
        scheme_base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        scheme_base = "ws://" + base[len("http://") :]
    else:
        scheme_base = "ws://" + base

    # Токен уходит в query — так требует бот; в логи url не пишем.
    return f"{scheme_base}/ws?token={token}"


def _ticket_id(payload: dict) -> int | None:
    for key in ("ticket_id", "id"):
        value = payload.get(key)
        if value:
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    ticket = payload.get("ticket")
    if isinstance(ticket, dict):
        return _ticket_id(ticket)
    return None


async def handle_event(event: str, payload: dict) -> bool:
    """Обработать одно событие бота. True — проекция обновлена."""
    if event not in TICKET_EVENTS:
        return False

    ticket_id = _ticket_id(payload or {})
    if ticket_id is None:
        logger.debug("Support WS: событие %s без id тикета", event)
        return False

    from web.backend.core.support_sync import sync_ticket

    synced = await sync_ticket(ticket_id)

    if event == "ticket.created":
        from web.backend.core.support_alerts import notify_new_ticket
        from shared.database import db_service

        ticket = dict(payload or {})
        if synced and db_service.is_connected:
            async with db_service.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT id, title, customer_name FROM support_tickets WHERE id = $1", ticket_id
                )
            if row:
                ticket = dict(row)
        await notify_new_ticket(ticket)

    return synced


async def _consume(url: str) -> None:
    import websockets

    async with websockets.connect(url, ping_interval=20, ping_timeout=20) as socket:
        logger.info("Support WS: подключились к событиям бота")
        async for raw in socket:
            try:
                message = json.loads(raw)
            except (TypeError, ValueError):
                continue
            event = str(message.get("type") or "")
            if event in TICKET_EVENTS:
                payload = message.get("payload") or message.get("data") or {}
                await handle_event(event, payload if isinstance(payload, dict) else {})


async def support_ws_loop() -> None:
    """Держать подписку живой. Бот недоступен — ждём с нарастающей паузой."""
    delay = RECONNECT_MIN_SECONDS
    while True:
        url = _ws_url()
        if not url:
            await asyncio.sleep(RECONNECT_MAX_SECONDS)
            continue

        try:
            await _consume(url)
            delay = RECONNECT_MIN_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — любой обрыв лечится переподключением
            logger.warning("Support WS: соединение потеряно (%s), повтор через %s с", exc, delay)

        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(delay)
        delay = min(delay * 2, RECONNECT_MAX_SECONDS)
