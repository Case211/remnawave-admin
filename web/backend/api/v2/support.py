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
    # Побочные действия шаблона: ответ, статус и тег одним запросом, чтобы
    # «ответить макросом» не превращалось в три обращения из интерфейса.
    set_status: Optional[str] = Field(None, pattern=r"^(open|answered|pending|closed)$")
    add_tag_id: Optional[int] = None


class StatusRequest(BaseModel):
    status: str = Field(..., pattern=r"^(open|answered|pending|closed)$")


class PriorityRequest(BaseModel):
    priority: str = Field(..., pattern=r"^(low|normal|high|urgent)$")


class ReadRequest(BaseModel):
    last_message_id: int = Field(0, ge=0)


def _require_db() -> None:
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE, "Database is not available")


def _require_account(admin: AdminUser) -> int:
    """id администратора для строк с NOT NULL admin_id.

    У env-админа из фолбэка account_id пустой — такие действия (взять тикет,
    отметить прочитанным) ему недоступны, но валить их ошибкой базы нельзя.
    """
    if admin.account_id is None:
        raise api_error(400, E.INVALID_INPUT, "This action requires a database admin account")
    return admin.account_id


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
        # % и _ в запросе оператора — это символы, а не подстановочные знаки.
        escaped = search.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.append(f"%{escaped}%")
        where.append(f"lower(t.search_text) LIKE ${len(params)} ESCAPE '\\'")

    # account_id у env-админа бывает None: в тексте запроса это дало бы
    # «r.admin_id = None» и синтаксическую ошибку на весь список.
    params.append(admin.account_id)
    reader_param = len(params)
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
        LEFT JOIN support_reads r ON r.ticket_id = t.id AND r.admin_id = ${reader_param}
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
            *params[:-3],
        )

    return {"items": [dict(row) for row in rows], "total": total or 0, "limit": limit, "offset": offset}


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "view")),
):
    """Карточка тикета с перепиской из проекции."""
    _require_db()
    card_sql = """
        SELECT t.*, a.admin_id AS assignee_id, s.snooze_to, n.note AS customer_note
        FROM support_tickets t
        LEFT JOIN support_assignments a ON a.ticket_id = t.id
        LEFT JOIN support_snoozes s ON s.ticket_id = t.id
        LEFT JOIN support_customer_notes n ON n.bot_user_id = t.bot_user_id
        WHERE t.id = $1
    """

    async with db_service.acquire() as conn:
        ticket = await conn.fetchrow(card_sql, ticket_id)

    if not ticket:
        # Тикета может не быть просто потому, что синк до него не дошёл. Ходим
        # в бота вне транзакции: держать коннект на время HTTP-вызова нельзя.
        if not await sync_ticket(ticket_id):
            raise api_error(404, E.NOT_FOUND, "Ticket not found")
        async with db_service.acquire() as conn:
            ticket = await conn.fetchrow(card_sql, ticket_id)
        if not ticket:
            raise api_error(404, E.NOT_FOUND, "Ticket not found")

    async with db_service.acquire() as conn:

        messages = await conn.fetch(
            "SELECT * FROM support_ticket_messages WHERE ticket_id = $1 ORDER BY created_at ASC",
            ticket_id,
        )
        tags = await conn.fetch(
            """
            SELECT g.id, g.name, g.color
            FROM support_ticket_tags tt
            JOIN support_tags g ON g.id = tt.tag_id
            WHERE tt.ticket_id = $1
            ORDER BY g.name
            """,
            ticket_id,
        )

    _touch_presence(ticket_id, admin)
    return {
        "ticket": dict(ticket),
        "messages": [dict(m) for m in messages],
        "watchers": _watchers(ticket_id, exclude_admin_id=admin.account_id),
        "tags": [dict(tag) for tag in tags],
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

    # Сообщение клиенту уже ушло. Если побочное действие не удалось, честнее
    # сказать об этом отдельным флагом, чем вернуть 5xx: оператор увидит ошибку,
    # нажмёт «отправить» ещё раз и клиент получит ответ дважды.
    warnings: list[str] = []

    new_status = "closed" if data.close else data.set_status
    if new_status:
        try:
            await proxy_request(lambda: bedolaga_client.set_ticket_status(ticket_id, new_status))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Support: ответ ушёл, но статус не сменился (%s): %s", ticket_id, exc)
            warnings.append("status_not_changed")

    if data.add_tag_id and db_service.is_connected:
        try:
            async with db_service.acquire() as conn:
                await conn.execute(
                    "INSERT INTO support_ticket_tags (ticket_id, tag_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                    ticket_id, data.add_tag_id,
                )
        except Exception as exc:  # noqa: BLE001 — например, тега уже нет
            logger.warning("Support: тег %s не повесился на %s: %s", data.add_tag_id, ticket_id, exc)
            warnings.append("tag_not_added")

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
    return {"success": True, "closed": data.close, "warnings": warnings}


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
            _require_account(admin),
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
            _require_account(admin),
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


# ── Шаблоны ответов, теги и отложенные ──

class MacroRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=4000)
    shortcut: Optional[str] = Field(None, max_length=32)
    set_status: Optional[str] = Field(None, pattern=r"^(open|answered|pending|closed)$")
    add_tag_id: Optional[int] = None
    sort_order: int = 0


class TagRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    color: str = Field("slate", max_length=16)


class SnoozeRequest(BaseModel):
    minutes: int = Field(..., ge=5, le=60 * 24 * 14)


@router.get("/macros")
async def list_macros(admin: AdminUser = Depends(require_permission("bedolaga_support", "view"))):
    """Шаблоны ответов: текст плюс побочное действие, которое он выполняет."""
    _require_db()
    async with db_service.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM support_macros ORDER BY sort_order, id")
    return {"items": [dict(row) for row in rows]}


@router.post("/macros", status_code=201)
async def create_macro(
    data: MacroRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO support_macros (title, body, shortcut, set_status, add_tag_id, sort_order, created_by)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            data.title, data.body, data.shortcut, data.set_status, data.add_tag_id,
            data.sort_order, admin.account_id,
        )
    return dict(row)


@router.put("/macros/{macro_id}")
async def update_macro(
    macro_id: int,
    data: MacroRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE support_macros
               SET title = $2, body = $3, shortcut = $4, set_status = $5,
                   add_tag_id = $6, sort_order = $7, updated_at = NOW()
             WHERE id = $1
            RETURNING *
            """,
            macro_id, data.title, data.body, data.shortcut, data.set_status,
            data.add_tag_id, data.sort_order,
        )
    if not row:
        raise api_error(404, E.NOT_FOUND, "Macro not found")
    return dict(row)


@router.delete("/macros/{macro_id}", status_code=204)
async def delete_macro(
    macro_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        await conn.execute("DELETE FROM support_macros WHERE id = $1", macro_id)


@router.get("/tags")
async def list_tags(admin: AdminUser = Depends(require_permission("bedolaga_support", "view"))):
    _require_db()
    async with db_service.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM support_tags ORDER BY name")
    return {"items": [dict(row) for row in rows]}


@router.post("/tags", status_code=201)
async def create_tag(
    data: TagRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO support_tags (name, color) VALUES ($1, $2)
            ON CONFLICT (name) DO UPDATE SET color = EXCLUDED.color
            RETURNING *
            """,
            data.name, data.color,
        )
    return dict(row)


@router.post("/tickets/{ticket_id}/tags/{tag_id}", status_code=204)
async def attach_tag(
    ticket_id: int,
    tag_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        await conn.execute(
            "INSERT INTO support_ticket_tags (ticket_id, tag_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            ticket_id, tag_id,
        )


@router.delete("/tickets/{ticket_id}/tags/{tag_id}", status_code=204)
async def detach_tag(
    ticket_id: int,
    tag_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        await conn.execute(
            "DELETE FROM support_ticket_tags WHERE ticket_id = $1 AND tag_id = $2", ticket_id, tag_id
        )


@router.post("/tickets/{ticket_id}/snooze")
async def snooze(
    ticket_id: int,
    data: SnoozeRequest,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    """Отложить обращение: уходит из «ждут нас», пока не истечёт срок."""
    _require_db()
    until = datetime.now(timezone.utc) + timedelta(minutes=data.minutes)
    async with db_service.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO support_snoozes (ticket_id, snooze_to, admin_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (ticket_id) DO UPDATE SET snooze_to = EXCLUDED.snooze_to, admin_id = EXCLUDED.admin_id
            """,
            ticket_id, until, admin.account_id,
        )
    return {"success": True, "snooze_to": until}


@router.delete("/tickets/{ticket_id}/snooze", status_code=204)
async def unsnooze(
    ticket_id: int,
    admin: AdminUser = Depends(require_permission("bedolaga_support", "edit")),
):
    _require_db()
    async with db_service.acquire() as conn:
        await conn.execute("DELETE FROM support_snoozes WHERE ticket_id = $1", ticket_id)


# ── Метрики ──

@router.get("/metrics")
async def metrics(
    days: int = Query(7, ge=1, le=90),
    admin: AdminUser = Depends(require_permission("bedolaga_support", "view")),
):
    """Сводка за период: сколько пришло, как быстро отвечали, где просрочили.

    Время первого ответа считается по проекции: разница между созданием тикета
    и первым сообщением оператора. Тикеты без ответа в среднее не попадают —
    иначе один висящий месяцами перекосил бы картину, — но видны отдельным
    числом.
    """
    _require_db()
    since = datetime.now(timezone.utc) - timedelta(days=days)
    threshold_minutes = sla_minutes()

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) AS created,
                COUNT(*) FILTER (WHERE first_response_at IS NOT NULL) AS answered,
                COUNT(*) FILTER (WHERE first_response_at IS NULL AND status <> 'closed') AS still_waiting,
                COUNT(*) FILTER (WHERE status = 'closed') AS closed,
                COALESCE(AVG(EXTRACT(EPOCH FROM (first_response_at - created_at)) / 60)
                         FILTER (WHERE first_response_at IS NOT NULL), 0) AS avg_first_response_minutes,
                COUNT(*) FILTER (
                    WHERE first_response_at IS NOT NULL
                      AND EXTRACT(EPOCH FROM (first_response_at - created_at)) / 60 > $2
                ) AS breached
            FROM support_tickets
            WHERE created_at >= $1
            """,
            since, threshold_minutes,
        )
        by_admin = await conn.fetch(
            """
            SELECT a.admin_id, COUNT(*) AS tickets
            FROM support_assignments a
            JOIN support_tickets t ON t.id = a.ticket_id
            WHERE t.updated_at >= $1
            GROUP BY a.admin_id
            ORDER BY tickets DESC
            LIMIT 20
            """,
            since,
        )

    created = int(row["created"] or 0)
    breached = int(row["breached"] or 0)
    return {
        "days": days,
        "sla_minutes": threshold_minutes,
        "created": created,
        "answered": int(row["answered"] or 0),
        "still_waiting": int(row["still_waiting"] or 0),
        "closed": int(row["closed"] or 0),
        "avg_first_response_minutes": round(float(row["avg_first_response_minutes"] or 0), 1),
        "breached": breached,
        "breached_percent": round(breached * 100 / created, 1) if created else 0.0,
        "by_admin": [dict(r) for r in by_admin],
    }
