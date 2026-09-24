"""Notifications API endpoints. Пороговые алерты — правила автоматизаций."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from web.backend.api.deps import (
    AdminUser,
    get_current_admin,
    require_permission,
    require_superadmin,
)
from web.backend.core.errors import api_error, E
from web.backend.schemas.common import PaginatedResponse, SuccessResponse
from web.backend.schemas.notification import (
    ChannelConfig,
    ChannelConfigItem,
    ChannelConfigUpdate,
    NotificationCreate,
    NotificationDeleteResult,
    NotificationItem,
    NotificationMarkRead,
    NotificationUnreadCount,
    SmtpConfigRead,
    SmtpConfigUpdate,
    SmtpTestRequest,
)
from shared.db_schema import ADMIN_TABLE, ADMIN_ROLES_TABLE, NOTIFICATIONS_TABLE, NOTIFICATION_CHANNELS_TABLE, SMTP_CONFIG_TABLE
from shared.db_query import select_sql, insert_sql, update_sql

router = APIRouter()
logger = logging.getLogger(__name__)


def _get_admin_id(admin: AdminUser) -> Optional[int]:
    """Return the admin's account_id or None for legacy admins."""
    return admin.account_id if admin.account_id else None


async def _require_account_id(admin: AdminUser) -> int:
    """Return account_id, auto-resolving for legacy admins.

    If the admin was authenticated via ADMINS env / .env password fallback
    and thus lacks an account_id, attempt to find their admin_accounts row
    by telegram_id or username.  If none exists, create one automatically
    so that channel & per-admin features work without manual migration.
    """
    if admin.account_id:
        return admin.account_id

    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            row = None
            if admin.telegram_id:
                row = await conn.fetchrow(
                    select_sql(
                        ADMIN_TABLE,
                        "id",
                        "WHERE telegram_id = $1",
                    ),
                    admin.telegram_id,
                )
            if not row and admin.username:
                row = await conn.fetchrow(
                    select_sql(
                        ADMIN_TABLE,
                        "id",
                        "WHERE username = $1",
                    ),
                    admin.username,
                )
            if row:
                return row["id"]

            # Auto-create account for legacy admin
            role_row = await conn.fetchrow(
                select_sql(
                    ADMIN_ROLES_TABLE,
                    "id",
                    "WHERE name = 'superadmin'",
                ),
            )
            role_id = role_row["id"] if role_row else None
            new_row = await conn.fetchrow(
                insert_sql(
                    ADMIN_TABLE,
                    ["username", "telegram_id", "role_id", "is_active"],
                    values="$1, $2, $3, true",
                    suffix="ON CONFLICT (username) DO UPDATE SET updated_at = NOW()",
                    returning="id",
                ),
                admin.username or f"admin_{admin.telegram_id}",
                admin.telegram_id,
                role_id,
            )
            if new_row:
                logger.info("Auto-created admin account for legacy admin '%s' (id=%d)", admin.username, new_row["id"])
                return new_row["id"]
    except Exception as e:
        logger.error("Failed to resolve account_id for '%s': %s", admin.username, e)

    raise HTTPException(
        status_code=400,
        detail="Could not resolve admin account. Please contact the administrator.",
    )


# ══════════════════════════════════════════════════════════════════
# Notifications
# ══════════════════════════════════════════════════════════════════

@router.get("/notifications", response_model=PaginatedResponse)
async def list_notifications(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    is_read: Optional[bool] = None,
    type: Optional[str] = None,
    severity: Optional[str] = None,
    admin: AdminUser = Depends(require_permission("notifications", "view")),
):
    """List notifications for the current admin."""
    from shared.database import db_service

    aid = _get_admin_id(admin)
    if aid is not None:
        conditions = ["(admin_id = $1 OR admin_id IS NULL)"]
        params: list = [aid]
    else:
        # Legacy admin — show broadcast (NULL) notifications
        conditions = ["admin_id IS NULL"]
        params = []
    idx = len(params) + 1

    if is_read is not None:
        conditions.append(f"is_read = ${idx}")
        params.append(is_read)
        idx += 1

    if type:
        conditions.append(f"type = ${idx}")
        params.append(type)
        idx += 1

    if severity:
        conditions.append(f"severity = ${idx}")
        params.append(severity)
        idx += 1

    where = " AND ".join(conditions)

    async with db_service.acquire() as conn:
        total = await conn.fetchval(select_sql(NOTIFICATIONS_TABLE, "COUNT(*)", f"WHERE {where}"), *params)
        rows = await conn.fetch(
            select_sql(NOTIFICATIONS_TABLE, "*", f"WHERE {where} ORDER BY created_at DESC LIMIT ${idx} OFFSET ${idx + 1}"),
            *params, per_page, (page - 1) * per_page,
        )

    items = [NotificationItem(**dict(r)) for r in rows]
    pages = max(1, (total + per_page - 1) // per_page)

    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page, pages=pages)


@router.get("/notifications/unread-count", response_model=NotificationUnreadCount)
async def get_unread_count(
    admin: AdminUser = Depends(get_current_admin),
):
    """Get count of unread notifications for the current admin."""
    from shared.database import db_service

    aid = _get_admin_id(admin)
    async with db_service.acquire() as conn:
        if aid is not None:
            count = await conn.fetchval(
                select_sql(NOTIFICATIONS_TABLE, "COUNT(*)", "WHERE (admin_id = $1 OR admin_id IS NULL) AND is_read = false"),
                aid,
            )
        else:
            count = await conn.fetchval(
                select_sql(NOTIFICATIONS_TABLE, "COUNT(*)", "WHERE admin_id IS NULL AND is_read = false"),
            )

    return NotificationUnreadCount(count=count or 0)


@router.post("/notifications/mark-read", response_model=SuccessResponse)
async def mark_notifications_read(
    data: NotificationMarkRead,
    admin: AdminUser = Depends(get_current_admin),
):
    """Mark notifications as read. Empty ids = mark all."""
    from shared.database import db_service

    aid = _get_admin_id(admin)
    async with db_service.acquire() as conn:
        if data.ids:
            if aid is not None:
                await conn.execute(
                    "UPDATE notifications SET is_read = true WHERE (admin_id = $1 OR admin_id IS NULL) AND id = ANY($2::bigint[])",
                    aid, data.ids,
                )
            else:
                await conn.execute(
                    "UPDATE notifications SET is_read = true WHERE admin_id IS NULL AND id = ANY($1::bigint[])",
                    data.ids,
                )
        else:
            if aid is not None:
                await conn.execute(
                    "UPDATE notifications SET is_read = true WHERE (admin_id = $1 OR admin_id IS NULL) AND is_read = false",
                    aid,
                )
            else:
                await conn.execute(
                    "UPDATE notifications SET is_read = true WHERE admin_id IS NULL AND is_read = false",
                )

    return SuccessResponse(message="Marked as read")


@router.delete("/notifications/read", response_model=NotificationDeleteResult)
async def delete_read_notifications(
    admin: AdminUser = Depends(require_permission("notifications", "delete")),
):
    """Удалить все прочитанные уведомления текущего админа, без ограничения по возрасту.

    Объявлен раньше DELETE /notifications/{notification_id}: иначе «read»
    попадёт в int-параметр маршрута и вернётся 422.
    """
    from shared.database import db_service

    aid = _get_admin_id(admin)
    async with db_service.acquire() as conn:
        if aid is not None:
            result = await conn.execute(
                "DELETE FROM notifications WHERE (admin_id = $1 OR admin_id IS NULL) AND is_read = true",
                aid,
            )
        else:
            result = await conn.execute(
                "DELETE FROM notifications WHERE admin_id IS NULL AND is_read = true",
            )
    # result вида "DELETE 1700"
    return NotificationDeleteResult(deleted=int(result.split()[-1]) if result else 0)


@router.delete("/notifications/{notification_id}", response_model=SuccessResponse)
async def delete_notification(
    notification_id: int,
    admin: AdminUser = Depends(get_current_admin),
):
    """Delete a single notification."""
    from shared.database import db_service

    aid = _get_admin_id(admin)
    async with db_service.acquire() as conn:
        if aid is not None:
            deleted = await conn.fetchval(
                "DELETE FROM notifications WHERE id = $1 AND (admin_id = $2 OR admin_id IS NULL) RETURNING id",
                notification_id, aid,
            )
        else:
            deleted = await conn.fetchval(
                "DELETE FROM notifications WHERE id = $1 AND admin_id IS NULL RETURNING id",
                notification_id,
            )

    if not deleted:
        raise api_error(404, E.NOTIFICATION_NOT_FOUND)

    return SuccessResponse(message="Deleted")


@router.delete("/notifications", response_model=SuccessResponse)
async def delete_old_notifications(
    days: int = Query(30, ge=1, le=365, description="Delete notifications older than N days"),
    admin: AdminUser = Depends(require_permission("notifications", "delete")),
):
    """Delete old notifications."""
    from shared.database import db_service

    aid = _get_admin_id(admin)
    async with db_service.acquire() as conn:
        if aid is not None:
            result = await conn.execute(
                "DELETE FROM notifications WHERE (admin_id = $1 OR admin_id IS NULL) AND created_at < NOW() - make_interval(days => $2)",
                aid, days,
            )
        else:
            result = await conn.execute(
                "DELETE FROM notifications WHERE admin_id IS NULL AND created_at < NOW() - make_interval(days => $1)",
                days,
            )
        # result is like "DELETE 42"
        count = int(result.split()[-1]) if result else 0

    return SuccessResponse(message=f"Deleted {count} notifications")


@router.post("/notifications/create", response_model=SuccessResponse)
async def create_notification_endpoint(
    data: NotificationCreate,
    admin: AdminUser = Depends(require_permission("notifications", "create")),
):
    """Create a notification (admin-initiated)."""
    from web.backend.core.notification_service import create_notification

    nid = await create_notification(
        title=data.title,
        body=data.body,
        type=data.type,
        severity=data.severity,
        admin_id=data.admin_id,
        link=data.link,
        source=data.source or "manual",
        source_id=data.source_id,
    )

    return SuccessResponse(message=f"Notification created (id={nid})")


# ══════════════════════════════════════════════════════════════════
# Notification Channels (per admin)
# ══════════════════════════════════════════════════════════════════

@router.get("/notification-channels", response_model=list)
async def list_channels(
    admin: AdminUser = Depends(get_current_admin),
):
    """Get notification channels for the current admin."""
    from shared.database import db_service

    aid = await _require_account_id(admin)
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(NOTIFICATION_CHANNELS_TABLE, "*", "WHERE admin_id = $1 ORDER BY channel_type"),
            aid,
        )

    items = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("config"), str):
            d["config"] = json.loads(d["config"])
        items.append(ChannelConfigItem(**d))
    return items


@router.post("/notification-channels", response_model=ChannelConfigItem)
async def create_channel(
    data: ChannelConfig,
    admin: AdminUser = Depends(get_current_admin),
):
    """Create or update a notification channel for the current admin."""
    from shared.database import db_service

    aid = await _require_account_id(admin)
    config_json = json.dumps(data.config)
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            insert_sql(NOTIFICATION_CHANNELS_TABLE, ["admin_id", "channel_type", "is_enabled", "config"], "ON CONFLICT (admin_id, channel_type) DO UPDATE SET is_enabled = $3, config = $4::jsonb, updated_at = NOW() RETURNING *"),
            aid, data.channel_type, data.is_enabled, config_json,
        )

    d = dict(row)
    if isinstance(d.get("config"), str):
        d["config"] = json.loads(d["config"])
    return ChannelConfigItem(**d)


@router.put("/notification-channels/{channel_id}", response_model=ChannelConfigItem)
async def update_channel(
    channel_id: int,
    data: ChannelConfigUpdate,
    admin: AdminUser = Depends(get_current_admin),
):
    """Update a notification channel."""
    from shared.database import db_service

    aid = await _require_account_id(admin)
    updates = []
    params = [channel_id, aid]
    idx = 3

    if data.is_enabled is not None:
        updates.append(f"is_enabled = ${idx}")
        params.append(data.is_enabled)
        idx += 1

    if data.config is not None:
        updates.append(f"config = ${idx}::jsonb")
        params.append(json.dumps(data.config))
        idx += 1

    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    updates.append("updated_at = NOW()")

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE notification_channels SET {', '.join(updates)} "
            f"WHERE id = $1 AND admin_id = $2 RETURNING *",
            *params,
        )

    if not row:
        raise api_error(404, E.CHANNEL_NOT_FOUND)

    d = dict(row)
    if isinstance(d.get("config"), str):
        d["config"] = json.loads(d["config"])
    return ChannelConfigItem(**d)


@router.delete("/notification-channels/{channel_id}", response_model=SuccessResponse)
async def delete_channel(
    channel_id: int,
    admin: AdminUser = Depends(get_current_admin),
):
    """Delete a notification channel."""
    from shared.database import db_service

    aid = await _require_account_id(admin)
    async with db_service.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM notification_channels WHERE id = $1 AND admin_id = $2 RETURNING id",
            channel_id, aid,
        )

    if not deleted:
        raise api_error(404, E.CHANNEL_NOT_FOUND)
    return SuccessResponse(message="Channel deleted")


# ══════════════════════════════════════════════════════════════════
# SMTP Config (global)
# ══════════════════════════════════════════════════════════════════

@router.get("/smtp-config", response_model=SmtpConfigRead)
async def get_smtp_config(
    admin: AdminUser = Depends(require_superadmin()),
):
    """Get SMTP configuration."""
    from shared.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(select_sql(SMTP_CONFIG_TABLE, "*", "ORDER BY id LIMIT 1"))

    if not row:
        raise api_error(404, E.SMTP_NOT_CONFIGURED)

    return SmtpConfigRead(**dict(row))


@router.put("/smtp-config", response_model=SmtpConfigRead)
async def update_smtp_config(
    data: SmtpConfigUpdate,
    admin: AdminUser = Depends(require_superadmin()),
):
    """Update SMTP configuration."""
    from shared.database import db_service

    updates = []
    params = []
    idx = 1

    for field_name, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            updates.append(f"{field_name} = ${idx}")
            params.append(value)
            idx += 1

    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    updates.append("updated_at = NOW()")

    async with db_service.acquire() as conn:
        # Ensure a row exists
        exists = await conn.fetchval(select_sql(SMTP_CONFIG_TABLE, "id", "ORDER BY id LIMIT 1"))
        if not exists:
            await conn.execute(
                insert_sql(SMTP_CONFIG_TABLE, ["host", "port", "from_email"], "VALUES ('localhost', 587, 'admin@remnawave.local')"),
            )

        row = await conn.fetchrow(
            update_sql(
                SMTP_CONFIG_TABLE, ", ".join(updates),
                "id = (SELECT id FROM smtp_config ORDER BY id LIMIT 1)",
                returning="*",
            ),
            *params,
        )

    if not row:
        raise api_error(500, E.SMTP_UPDATE_FAILED)

    return SmtpConfigRead(**dict(row))


@router.post("/smtp-config/test", response_model=dict)
async def test_smtp_endpoint(
    data: SmtpTestRequest,
    admin: AdminUser = Depends(require_superadmin()),
):
    """Send a test email to verify SMTP settings."""
    from web.backend.core.notification_service import test_smtp
    result = await test_smtp(data.to_email)
    return result


# ══════════════════════════════════════════════════════════════════
# Do not disturb (per admin)
# ══════════════════════════════════════════════════════════════════

class DndSettings(BaseModel):
    """Окно «не беспокоить» по часам панели; пусто — выключено."""
    dnd_from: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    dnd_to: Optional[str] = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


@router.get("/notification-dnd", response_model=DndSettings)
async def get_dnd(admin: AdminUser = Depends(get_current_admin)):
    if admin.account_id is None:
        return DndSettings()
    from shared.database import db_service
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(f"SELECT dnd_from, dnd_to FROM {ADMIN_TABLE} WHERE id = $1", admin.account_id)
    return DndSettings(**dict(row)) if row else DndSettings()


@router.put("/notification-dnd", response_model=DndSettings)
async def set_dnd(data: DndSettings, admin: AdminUser = Depends(get_current_admin)):
    if admin.account_id is None:
        raise api_error(400, E.INVALID_ACTION, "Legacy admin has no account to store settings")
    if bool(data.dnd_from) != bool(data.dnd_to):
        raise api_error(400, E.INVALID_INPUT, "Set both dnd_from and dnd_to or neither")
    from shared.database import db_service
    async with db_service.acquire() as conn:
        await conn.execute(
            f"UPDATE {ADMIN_TABLE} SET dnd_from = $2, dnd_to = $3 WHERE id = $1",
            admin.account_id, data.dnd_from or None, data.dnd_to or None,
        )
    return DndSettings(dnd_from=data.dnd_from or None, dnd_to=data.dnd_to or None)
