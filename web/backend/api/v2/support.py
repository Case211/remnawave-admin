"""Поддержка: очереди операторов поверх проекции тикетов Bedolaga.

Читаем из своей проекции (`support_tickets`) — только она умеет очереди, поиск
и сортировку по времени ожидания. Пишем всегда через бота: ответ, статус и
приоритет уходят в его Web API, а проекция обновляется сразу после успешного
ответа, чтобы оператор увидел своё сообщение, не дожидаясь круга синка.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from shared.bedolaga_client import bedolaga_client
from shared.database import db_service
from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.api.v2.bedolaga import proxy_request
from web.backend.core.audit import write_audit_log
from web.backend.core.errors import E, api_error
from web.backend.core.support_alerts import sla_minutes
from web.backend.core.support_sync import sync_ticket, sync_tickets

logger = logging.getLogger(__name__)
router = APIRouter()

# Кто сейчас смотрит тикет: admin_id → время последнего «я здесь». Живёт в
# памяти процесса — презенс переживать рестарт не обязан, зато не нагружает БД
# записью на каждый тик.
PRESENCE_TTL_SECONDS = 45
_presence: dict[int, dict[int, dict]] = {}

QUEUE_WAIT_US = "wait_us"
QUEUE_MINE = "mine"
QUEUE_LATE = "late"
QUEUE_WAIT_CLIENT = "wait_client"
QUEUE_SNOOZED = "snoozed"
QUEUE_ALL = "all"


class ReplyRequest(BaseModel):
    message_text: str = Field(..., min_length=1, max_length=4000)
    close: bool = False


class StatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(open|answered|pending|closed)$")


class PriorityRequest(BaseModel):
    priority: str = Field(..., pattern=r"^(low|normal|high|urgent)$")


class ReadRequest(BaseModel):
    last_message_id: int = Field(0, ge=0)


def _require_db() -> None:
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE, "Database is not available")


def _touch_presence(ticket_id: int, admin: AdminUser) -> None:
    watchers = _presence.setdefault(ticket_id, {})
    watchers[admin.account_id] = {
        "admin_id": admin.account_id,
        "username": admin.username,
        "seen_at": datetime.now(timezone.utc),
    }


def _watchers(ticket_id: int, exclude_admin_id: int | None = None) -> list[dict]:
    """Кто ещё открыт на этом тикете прямо сейчас — защита от двух ответов."""
    fresh_after = datetime.now(timezone.utc) - timedelta(seconds=PRESENCE_TTL_SECONDS)
    watchers = _presence.get(ticket_id, {})
    stale = [admin_id for admin_id, data in watchers.items() if data["seen_at"] < fresh_after]
    for admin_id in stale:
        watchers.pop(admin_id, None)
    if not watchers:
        _presence.pop(ticket_id, None)
    return [
        {"admin_id": data["admin_id"], "username": data["username"]}
        for admin_id, data in watchers.items()
        if admin_id != exclude_admin_id
    ]


def _queue_condition(queue: str, admin_id: int, params: list) -> str:
    """SQL-условие очереди. Параметры добавляются в ``params`` по ходу."""
    late_before = datetime.now(timezone.utc) - timedelta(minutes=sla_minutes())

    if queue == QUEUE_MINE:
        params.append(admin_id)
        return f"t.status <> 'closed' AND a.admin_id = ${len(params)}"
    if queue == QUEUE_LATE:
        params.append(late_before)
        return f"t.waiting_since IS NOT NULL AND t.waiting_since < ${len(params)}"
    if queue == QUEUE_WAIT_CLIENT:
        return "t.status <> 'closed' AND t.waiting_since IS NULL"
    if queue == QUEUE_SNOOZED:
        return "s.snooze_to IS NOT NULL AND s.snooze_to > NOW()"
    if queue == QUEUE_ALL:
        return "TRUE"
    # по умолчанию — «ждут нас»: последним написал клиент и тикет не отложен
    return "t.waiting_since IS NOT NULL AND (s.snooze_to IS NULL OR s.snooze_to <= NOW())"


@router.get("/queues")
async def get_queues(admin: AdminUser = Depends(require_permission("bedolaga_support", "view"))):
    """Счётчики очередей — то, что оператор видит слева."""
    _require_db()
    late_before = datetime.now(timezone.utc) - timedelta(minutes=sla_minutes())

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE t.waiting_since IS NOT NULL
                      AND (s.snooze_to IS NULL OR s.snooze_to <= NOW())
                ) AS wait_us,
                COUNT(*) FILTER (WHERE t.status <> 'closed' AND a.admin_id = $1) AS mine,
                COUNT(*) FILTER (WHERE t.waiting_since IS NOT NULL AND t.waiting_since < $2) AS late,
                COUNT(*) FILTER (WHERE t.status <> 'closed' AND t.waiting_since IS NULL) AS wait_client,
                COUNT(*) FILTER (WHERE s.snooze_to IS NOT NULL AND s.snooze_to > NOW()) AS snoozed,
                COUNT(*) AS all
            FROM support_tickets t
            LEFT JOIN support_assignments a ON a.ticket_id = t.id
            LEFT JOIN support_snoozes s ON s.ticket_id = t.id
            """,
            admin.account_id,
            late_before,
        )

    return {
        "wait_us": row["wait_us"],
        "mine": row["mine"],
        "late": row["late"],
        "wait_client": row["wait_client"],
        "snoozed": row["snoozed"],
        "all": row["all"],
        "sla_minutes": sla_minutes(),
    }


@router.get("/tickets")
async def list_tickets(
    queue: str = Query(QUEUE_WAIT_US),
    search: Optional[str] = Query(None, max_length=200),
    priority: Optional[str] = Query(None, pattern=r"^(low|normal|high|urgent)$"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("bedolaga_support", "view")),
):
    """Список тикетов очереди: дольше всех ждут — сверху."""
    _require_db()
    params: list = []
    where = [_queue_condition(queue, admin.account_id, params)]

    if priority:
        params.append(priority)
        where.append(f"t.priority = ${len(params)}")
    if search:
        params.append(f"%{search.lower()}%")
        where.append(f"lower(t.search_text) LIKE ${len(params)}")

    params.extend([limit, offset])
    sql = f"""
        SELECT t.*, a.admin_id AS assignee_id, s.snooze_to,
               COALESCE(r.last_read_message_id, 0) AS last_read_message_id,
               (SELECT COUNT(*) FROM support_ticket_messages m
                 WHERE m.ticket_id = t.id AND m.id > COALESCE(r.last_read_message_id, 0)
                   AND NOT m.is_from_admin) AS unread_count
        FROM support_tickets t
        LEFT JOIN support_assignments a ON a.ticket_id = t.id
        LEFT JOIN support_snoozes s ON s.ticket_id = t.id
        LEFT JOIN support_reads r ON r.ticket_id = t.id AND r.admin_id = {admin.account_id}
        WHERE {' AND '.join(where)}
        ORDER BY t.waiting_since ASC NULLS LAST, t.updated_at DESC
        LIMIT ${len(params) - 1} OFFSET ${len(params)}
    """

    async with db_service.acquire() as conn:
        rows = await conn.fetch(sql, *params)
        total = await conn.fetchval(
            f"""
            SELECT COUNT(*)
            FROM support_tickets t
            LEFT JOIN support_assignments a ON a.ticket_id = t.id
            LEFT JOIN support_snoozes s ON s.ticket_id = t.id
            WHERE {' AND '.join(where)}
            """,
            *params[:-2],
        )

    return {"items": [dict(row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "view")),
):
    """Карточка тикета с перепиской из проекции."""
    _require_db()
    async with db_service.acquire() as conn:
        ticket = await conn.fetchrow(
            """
            SELECT t.*, a.admin_id AS assignee_id, s.snooze_to, n.note AS customer_note
            FROM support_tickets t
            LEFT JOIN support_assignments a ON a.ticket_id = t.id
            LEFT JOIN support_snoozes s ON s.ticket_id = t.id
            LEFT JOIN support_customer_notes n ON n.bot_user_id = t.bot_user_id
            WHERE t.id = $1
            """,
            ticket_id,
        )
        if not ticket:
            # Тикета может не быть просто потому, что синк до него не дошёл.
            if not await sync_ticket(ticket_id):
                raise api_error(404, E.NOT_FOUND, "Ticket not found")
            ticket = await conn.fetchrow("SELECT * FROM support_tickets WHERE id = $1", ticket_id)
            if not ticket:
                raise api_error(404, E.NOT_FOUND, "Ticket not found")

        messages = await conn.fetch(
            "SELECT * FROM support_ticket_messages WHERE ticket_id = $1 ORDER BY created_at ASC",
            ticket_id,
        )

    _touch_presence(ticket_id, admin)
    return {
        "ticket": dict(ticket),
        "messages": [dict(m) for m in messages],
        "watchers": _watchers(ticket_id, exclude_admin_id=admin.account_id),
    }


@router.post("/tickets/{ticket_id}/reply")
async def reply(
    ticket_id: int,
    data: ReplyRequest,
    request: Request,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "create")),
):
    """Ответить клиенту. Пишет бот — он же разошлёт в Telegram или кабинет."""
    await proxy_request(lambda: bedolaga_client.reply_ticket(ticket_id, data.message_text))
    if data.close:
        await proxy_request(lambda: bedolaga_client.set_ticket_status(ticket_id, "closed"))

    # Ответ уже ушёл; проекция догонит сама, даже если синк сейчас упадёт.
    await sync_ticket(ticket_id)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="support.reply",
        resource="support",
        resource_id=str(ticket_id),
        ip_address=get_client_ip(request),
    )
    return {"success": True, "closed": data.close}


@router.post("/tickets/{ticket_id}/status")
async def set_status(
    ticket_id: int,
    data: StatusRequest,
    request: Request,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    await proxy_request(lambda: bedolaga_client.set_ticket_status(ticket_id, data.status))
    await sync_ticket(ticket_id)
    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="support.status",
        resource="support",
        resource_id=str(ticket_id),
        details=data.status,
        ip_address=get_client_ip(request),
    )
    return {"success": True, "status": data.status}


@router.post("/tickets/{ticket_id}/priority")
async def set_priority(
    ticket_id: int,
    data: PriorityRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    await proxy_request(lambda: bedolaga_client.set_ticket_priority(ticket_id, data.priority))
    await sync_ticket(ticket_id)
    return {"success": True, "priority": data.priority}


@router.post("/tickets/{ticket_id}/assign")
async def assign(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    """Взять тикет себе. Повторный вызов другим оператором перехватывает его."""
    _require_db()
    async with db_service.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO support_assignments (ticket_id, admin_id, claimed_at)
            VALUES ($1, $2, NOW())
            ON CONFLICT (ticket_id) DO UPDATE SET admin_id = EXCLUDED.admin_id, claimed_at = NOW()
            """,
            ticket_id,
            admin.account_id,
        )
    return {"success": True, "assignee_id": admin.account_id}


@router.delete("/tickets/{ticket_id}/assign")
async def unassign(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        await conn.execute("DELETE FROM support_assignments WHERE ticket_id = $1", ticket_id)
    return {"success": True}


@router.post("/tickets/{ticket_id}/read")
async def mark_read(
    ticket_id: int,
    data: ReadRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "view")),
):
    """Отметить переписку прочитанной до указанного сообщения."""
    _require_db()
    async with db_service.acquire() as conn:
        last_id = data.last_message_id or await conn.fetchval(
            "SELECT COALESCE(MAX(id), 0) FROM support_ticket_messages WHERE ticket_id = $1",
            ticket_id,
        )
        await conn.execute(
            """
            INSERT INTO support_reads (ticket_id, admin_id, last_read_message_id, read_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (ticket_id, admin_id) DO UPDATE
                SET last_read_message_id = GREATEST(support_reads.last_read_message_id, EXCLUDED.last_read_message_id),
                    read_at = NOW()
            """,
            ticket_id,
            admin.account_id,
            int(last_id or 0),
        )
    return {"success": True, "last_read_message_id": int(last_id or 0)}


@router.post("/sync")
async def run_sync(
    full: bool = Query(False, description="Полный проход, а не только изменившиеся"),
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    """Ручной догоняющий синк — на случай, если бот был недоступен."""
    return await sync_tickets(full=full)


@router.post("/tickets/{ticket_id}/presence")
async def heartbeat(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "view")),
):
    """«Я смотрю этот тикет» — чтобы коллега увидел и не ответил вторым."""
    _touch_presence(ticket_id, admin)
    return {"watchers": _watchers(ticket_id, exclude_admin_id=admin.account_id)}
