"""Зеркало тикетов Bedolaga: из бота в нашу проекцию.

Web API бота отдаёт список тикетов и переписку, но фильтрует только по статусу,
приоритету и пользователю. Очередь оператора («ждут нас», «просрочены»), поиск
по тексту и время ожидания по такому API не построить — поэтому лента живёт у
нас копией, а бот остаётся источником правды: ответы, статусы и приоритеты
пишутся только через него.

Синк догоняющий: раз в интервал проходим список, обновляем изменившиеся тикеты
и подтягиваем переписку тех, у кого сдвинулся ``updated_at``. Реалтайм поверх
этого добавляет WebSocket бота (`ticket.message_added`) — он лишь зовёт
:func:`sync_ticket` раньше, чем это сделает цикл.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 300
PAGE_SIZE = 200
MAX_PAGES = 25
SEARCH_TEXT_LIMIT = 20_000


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _customer_name(ticket: dict) -> str | None:
    user = ticket.get("user") or {}
    for key in ("full_name", "username", "first_name", "email"):
        value = user.get(key) or ticket.get(key)
        if value:
            return str(value)
    return None


def derive_fields(ticket: dict, messages: list[dict]) -> dict:
    """Производные поля проекции: по ним строятся очереди, SLA и поиск.

    ``waiting_since`` заполнен, только когда последним написал клиент — это и
    есть «ждут нас». Как только ответил оператор, ожидание обнуляется, и тикет
    уходит из очереди, не мозоля глаза.
    """
    ordered = sorted(messages, key=lambda m: _parse_dt(m.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))
    last = ordered[-1] if ordered else None
    first_admin = next((m for m in ordered if m.get("is_from_admin")), None)

    waiting_since = None
    if last is not None and not last.get("is_from_admin") and ticket.get("status") != "closed":
        waiting_since = _parse_dt(last.get("created_at"))

    search_parts: list[str] = [str(ticket.get("title") or ""), _customer_name(ticket) or ""]
    search_parts.extend(str(m.get("message_text") or "") for m in ordered)
    search_text = " ".join(part for part in search_parts if part)[:SEARCH_TEXT_LIMIT]

    return {
        "messages_count": len(ordered),
        "last_message_at": _parse_dt(last.get("created_at")) if last else None,
        "last_message_from": ("admin" if last.get("is_from_admin") else "user") if last else None,
        "last_message_text": (str(last.get("message_text") or "")[:500] if last else None),
        "first_response_at": _parse_dt(first_admin.get("created_at")) if first_admin else None,
        "waiting_since": waiting_since,
        "search_text": search_text,
    }


async def _upsert_ticket(conn, ticket: dict, messages: list[dict]) -> None:
    derived = derive_fields(ticket, messages)
    await conn.execute(
        """
        INSERT INTO support_tickets (
            id, bot_user_id, telegram_id, customer_name, title, status, priority,
            user_reply_blocked, messages_count, last_message_at, last_message_from,
            last_message_text, first_response_at, waiting_since, created_at, updated_at,
            closed_at, synced_at, search_text
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, NOW(), $18
        )
        ON CONFLICT (id) DO UPDATE SET
            customer_name = EXCLUDED.customer_name,
            title = EXCLUDED.title,
            status = EXCLUDED.status,
            priority = EXCLUDED.priority,
            user_reply_blocked = EXCLUDED.user_reply_blocked,
            messages_count = EXCLUDED.messages_count,
            last_message_at = EXCLUDED.last_message_at,
            last_message_from = EXCLUDED.last_message_from,
            last_message_text = EXCLUDED.last_message_text,
            first_response_at = EXCLUDED.first_response_at,
            waiting_since = EXCLUDED.waiting_since,
            updated_at = EXCLUDED.updated_at,
            closed_at = EXCLUDED.closed_at,
            synced_at = NOW(),
            search_text = EXCLUDED.search_text
        """,
        int(ticket["id"]),
        int(ticket.get("user_id") or 0),
        ticket.get("telegram_id"),
        _customer_name(ticket),
        str(ticket.get("title") or ""),
        str(ticket.get("status") or "open"),
        str(ticket.get("priority") or "normal"),
        bool(ticket.get("user_reply_block_permanent") or ticket.get("user_reply_block_until")),
        derived["messages_count"],
        derived["last_message_at"],
        derived["last_message_from"],
        derived["last_message_text"],
        derived["first_response_at"],
        derived["waiting_since"],
        _parse_dt(ticket.get("created_at")) or datetime.now(timezone.utc),
        _parse_dt(ticket.get("updated_at")) or datetime.now(timezone.utc),
        _parse_dt(ticket.get("closed_at")),
        derived["search_text"],
    )

    for message in messages:
        await conn.execute(
            """
            INSERT INTO support_ticket_messages (
                id, ticket_id, is_from_admin, author_name, text, has_media, media_type, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (id) DO UPDATE SET
                text = EXCLUDED.text,
                has_media = EXCLUDED.has_media,
                media_type = EXCLUDED.media_type
            """,
            int(message["id"]),
            int(ticket["id"]),
            bool(message.get("is_from_admin")),
            message.get("author_name"),
            str(message.get("message_text") or ""),
            bool(message.get("has_media")),
            message.get("media_type"),
            _parse_dt(message.get("created_at")) or datetime.now(timezone.utc),
        )


async def sync_ticket(ticket_id: int) -> bool:
    """Подтянуть один тикет целиком. False — бот недоступен или тикета нет."""
    from shared.bedolaga_client import bedolaga_client
    from shared.database import db_service

    if not db_service.is_connected:
        return False
    try:
        ticket = await bedolaga_client.get_ticket(ticket_id)
    except Exception as exc:  # noqa: BLE001 — бот недоступен: синк молча ждёт следующего круга
        logger.warning("Support sync: тикет %s не получен: %s", ticket_id, exc)
        return False

    messages = list(ticket.get("messages") or [])
    async with db_service.acquire() as conn:
        await _upsert_ticket(conn, ticket, messages)
    return True


async def _known_updated_at(conn) -> dict[int, datetime]:
    rows = await conn.fetch("SELECT id, updated_at FROM support_tickets")
    return {int(row["id"]): row["updated_at"] for row in rows}


async def sync_tickets(*, full: bool = False) -> dict:
    """Догоняющий проход по списку тикетов.

    Переписку тянем только у тех, у кого сдвинулся ``updated_at`` — иначе на
    каждом круге пришлось бы выкачивать всю историю всех обращений.
    """
    from shared.bedolaga_client import bedolaga_client
    from shared.database import db_service

    if not db_service.is_connected:
        return {"scanned": 0, "updated": 0, "skipped": 0}

    scanned = updated = skipped = 0
    async with db_service.acquire() as conn:
        known = {} if full else await _known_updated_at(conn)

        for page in range(MAX_PAGES):
            try:
                batch = await bedolaga_client.list_tickets(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
            except Exception as exc:  # noqa: BLE001 — бот недоступен, продолжим в следующий раз
                logger.warning("Support sync: список тикетов не получен: %s", exc)
                break

            items: Iterable[dict] = batch if isinstance(batch, list) else (batch or {}).get("items") or []
            items = list(items)
            if not items:
                break

            for ticket in items:
                scanned += 1
                ticket_id = int(ticket.get("id") or 0)
                if not ticket_id:
                    continue

                remote_updated = _parse_dt(ticket.get("updated_at"))
                local_updated = known.get(ticket_id)
                if local_updated and remote_updated and remote_updated <= local_updated:
                    skipped += 1
                    continue

                messages = list(ticket.get("messages") or [])
                if not messages:
                    try:
                        detailed = await bedolaga_client.get_ticket(ticket_id)
                        messages = list(detailed.get("messages") or [])
                        ticket = {**ticket, **detailed}
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("Support sync: переписка %s не получена: %s", ticket_id, exc)
                        continue

                await _upsert_ticket(conn, ticket, messages)
                updated += 1

            if len(items) < PAGE_SIZE:
                break

    if updated:
        logger.info("Support sync: обновлено %s тикетов из %s просмотренных", updated, scanned)
    return {"scanned": scanned, "updated": updated, "skipped": skipped}


async def support_sync_loop() -> None:
    """Фоновый догоняющий синк. Падение круга не должно убивать цикл."""
    while True:
        try:
            await sync_tickets()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("Support sync: круг синка упал: %s", exc, exc_info=True)
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)
