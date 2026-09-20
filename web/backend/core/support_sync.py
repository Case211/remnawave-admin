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
import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx

logger = logging.getLogger(__name__)

SYNC_INTERVAL_SECONDS = 300
PAGE_SIZE = 200
MAX_PAGES = 25
SEARCH_TEXT_LIMIT = 20_000

# Имена клиентов бот в списке тикетов не отдаёт — их приходится добирать по
# одному. Меняются они редко, поэтому держим в памяти процесса.
_name_cache: dict[int, str | None] = {}
_NAME_CACHE_LIMIT = 5000


def _ensure_client() -> bool:
    """Настроить клиент Bedolaga для фоновой работы.

    ``ensure_configured`` живёт в слое HTTP-ручек и вызывается из
    ``proxy_request``. Фоновым циклам никто его не дёргал: на свежем процессе
    клиент оставался без базового URL и токена, синк падал на первом запросе, а
    очереди оператора оставались пустыми до первого захода в другой раздел.
    """
    from web.backend.api.v2.bedolaga import ensure_configured

    try:
        ensure_configured()
        return True
    except Exception as exc:  # noqa: BLE001 — не настроен Bedolaga API: молча ждём
        logger.debug("Support sync: клиент Bedolaga не настроен (%s)", exc)
        return False


async def _customer_title(user_id: int) -> str | None:
    """Имя клиента по его id в боте; None — бот не ответил."""
    if not user_id:
        return None
    if user_id in _name_cache:
        return _name_cache[user_id]

    from shared.bedolaga_client import bedolaga_client

    try:
        user = await bedolaga_client.get_user(user_id)
    except Exception:  # noqa: BLE001 — имя не критично, покажем номер
        return None

    name = None
    for key in ("username", "first_name", "email"):
        value = (user or {}).get(key)
        if value:
            name = str(value)
            break
    if name and (user or {}).get("last_name") and key == "first_name":
        name = f"{name} {user['last_name']}".strip()

    if len(_name_cache) >= _NAME_CACHE_LIMIT:
        _name_cache.clear()
    _name_cache[user_id] = name
    return name


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


def derive_fields(ticket: dict, messages: list[dict], auto_ids: set[int] | None = None) -> dict:
    """Производные поля проекции: по ним строятся очереди, SLA и поиск.

    ``waiting_since`` заполнен, только когда последним написал клиент — это и
    есть «ждут нас». Как только ответил оператор, ожидание обнуляется, и тикет
    уходит из очереди, не мозоля глаза.

    ``auto_ids`` — сообщения робота. Живой лентой они остаются (клиент их
    видел), но ответом оператора не считаются: иначе автоответ в часы тишины
    убирал бы обращение из очереди и портил метрику первого ответа.
    """
    ordered = sorted(messages, key=lambda m: _parse_dt(m.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc))
    last = ordered[-1] if ordered else None
    robots = auto_ids or set()
    human = [m for m in ordered if int(m.get("id") or 0) not in robots]
    last_human = human[-1] if human else None
    first_admin = next((m for m in human if m.get("is_from_admin")), None)

    waiting_since = None
    if last_human is not None and not last_human.get("is_from_admin") and ticket.get("status") != "closed":
        waiting_since = _parse_dt(last_human.get("created_at"))

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


async def _upsert_ticket(conn, ticket: dict, messages: list[dict], customer: dict | None = None) -> None:
    from web.backend.core.support_auto_reply import auto_message_ids

    derived = derive_fields(ticket, messages, await auto_message_ids(conn, int(ticket["id"])))
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
        ticket.get("telegram_id") or (customer or {}).get("telegram_id"),
        _customer_name(ticket) or (customer or {}).get("name"),
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
                id, ticket_id, is_from_admin, author_name, text, has_media, media_type, media_items, created_at
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO UPDATE SET
                text = EXCLUDED.text,
                has_media = EXCLUDED.has_media,
                media_type = EXCLUDED.media_type,
                media_items = EXCLUDED.media_items
            """,
            int(message["id"]),
            int(ticket["id"]),
            bool(message.get("is_from_admin")),
            message.get("author_name"),
            str(message.get("message_text") or ""),
            bool(message.get("has_media")),
            message.get("media_type"),
            # Пачку храним как есть: её элементы качаются по file_id.
            json.dumps(message.get("media_items")) if message.get("media_items") else None,
            _parse_dt(message.get("created_at")) or datetime.now(timezone.utc),
        )


async def forget_ticket(ticket_id: int) -> bool:
    """Убрать из проекции обращение, которого больше нет в боте.

    Бот — источник правды: если он отвечает 404, держать копию незачем, иначе
    обращение висит в очереди вечно и открывается ошибкой. Всё связанное
    (переписка, назначение, отложка, метки прочтения, теги) уезжает каскадом;
    заметка о клиенте привязана к человеку, а не к обращению, и остаётся.
    Скачанные вложения не трогаем — их сметёт обычная чистка кэша по сроку.
    """
    from shared.database import db_service

    if not db_service.is_connected:
        return False
    async with db_service.acquire() as conn:
        result = await conn.execute("DELETE FROM support_tickets WHERE id = $1", ticket_id)
    removed = result.rsplit(" ", 1)[-1] not in ("0", "")
    if removed:
        logger.info("Support sync: тикет %s исчез в боте, убран из проекции", ticket_id)
    return removed


async def sync_ticket(ticket_id: int) -> bool:
    """Подтянуть один тикет целиком. False — бот недоступен или тикета нет."""
    from shared.bedolaga_client import bedolaga_client
    from shared.database import db_service

    if not db_service.is_connected or not _ensure_client():
        return False
    try:
        ticket = await bedolaga_client.get_ticket(ticket_id)
    except httpx.HTTPStatusError as exc:
        # 404 — это ответ бота «такого обращения нет», а не сбой связи.
        if exc.response.status_code == 404:
            await forget_ticket(ticket_id)
        else:
            logger.warning("Support sync: тикет %s не получен: %s", ticket_id, exc)
        return False
    except Exception as exc:  # noqa: BLE001 — бот недоступен: синк молча ждёт следующего круга
        logger.warning("Support sync: тикет %s не получен: %s", ticket_id, exc)
        return False

    messages = list(ticket.get("messages") or [])
    customer = {"name": await _customer_title(int(ticket.get("user_id") or 0))}
    async with db_service.acquire() as conn:
        await _upsert_ticket(conn, ticket, messages, customer)
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

    if not db_service.is_connected or not _ensure_client():
        return {"scanned": 0, "updated": 0, "skipped": 0, "forgotten": 0}

    started_at = datetime.now(timezone.utc)
    scanned = updated = skipped = forgotten = 0
    # Чистим проекцию только после честного полного прохода: оборвался он на
    # ошибке или упёрся в потолок страниц — удалять нельзя, иначе снесём живые
    # обращения, до которых просто не дошли.
    seen: set[int] = set()
    walked_to_end = False
    # Соединение берём точечно: проход по тысяче тикетов — это тысяча HTTP-вызовов
    # к боту, и держать всё это время занятым коннект из пула нельзя.
    if full:
        known: dict[int, datetime] = {}
    else:
        async with db_service.acquire() as conn:
            known = await _known_updated_at(conn)

    for page in range(MAX_PAGES):
        try:
            batch = await bedolaga_client.list_tickets(limit=PAGE_SIZE, offset=page * PAGE_SIZE)
        except Exception as exc:  # noqa: BLE001 — бот недоступен, продолжим в следующий раз
            logger.warning("Support sync: список тикетов не получен: %s", exc)
            break

        items: Iterable[dict] = batch if isinstance(batch, list) else (batch or {}).get("items") or []
        items = list(items)
        if not items:
            walked_to_end = True
            break

        for ticket in items:
            scanned += 1
            ticket_id = int(ticket.get("id") or 0)
            if not ticket_id:
                continue
            seen.add(ticket_id)

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

            customer = {"name": await _customer_title(int(ticket.get("user_id") or 0))}
            async with db_service.acquire() as conn:
                await _upsert_ticket(conn, ticket, messages, customer)
            updated += 1

            # Страховка на случай, когда события бота до нас не доходят: без WS
            # обращение находит только этот проход. От рассылки по всей истории
            # защищает возраст обращения, который проверяет сам автоответ.
            if ticket_id not in known:
                from web.backend.core.support_auto_reply import maybe_auto_reply

                await maybe_auto_reply({**ticket, "messages": messages})

        if len(items) < PAGE_SIZE:
            walked_to_end = True
            break

    # Проход идёт по всем страницам списка, даже когда почти всё пропускается по
    # ``updated_at``, — значит после честного завершения ``seen`` описывает всё,
    # что есть в боте, и лишнее в проекции можно убрать.
    if walked_to_end and seen:
        async with db_service.acquire() as conn:
            # Обращение, появившееся уже во время прохода, синк тронуть не мог —
            # его защищает synced_at.
            missing = await conn.fetchval(
                "SELECT COUNT(*) FROM support_tickets WHERE synced_at < $1 AND NOT (id = ANY($2::bigint[]))",
                started_at,
                list(seen),
            )
            total = await conn.fetchval("SELECT COUNT(*) FROM support_tickets")
            # Бот, отдавший обрезанный список из-за своей ошибки, не должен
            # уносить с собой всю очередь: массовое расхождение — повод
            # пожаловаться в лог, а не удалять.
            if missing and total > 20 and missing > total / 2:
                logger.warning(
                    "Support sync: бот не вернул %s из %s обращений — чистку пропускаем",
                    missing, total,
                )
            elif missing:
                gone = await conn.fetch(
                    """
                    DELETE FROM support_tickets
                     WHERE synced_at < $1 AND NOT (id = ANY($2::bigint[]))
                    RETURNING id
                    """,
                    started_at,
                    list(seen),
                )
                forgotten = len(gone)
                logger.info("Support sync: убрано %s обращений, которых больше нет в боте", forgotten)

    if updated:
        logger.info("Support sync: обновлено %s тикетов из %s просмотренных", updated, scanned)
    return {"scanned": scanned, "updated": updated, "skipped": skipped, "forgotten": forgotten}


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
