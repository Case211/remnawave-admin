"""Notifications & alerts API endpoints."""
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from web.backend.api.deps import (
    AdminUser,
    get_current_admin,
    require_permission,
    require_superadmin,
)
from web.backend.schemas.common import PaginatedResponse, SuccessResponse
from web.backend.schemas.notification import (
    AlertLogAcknowledge,
    AlertLogItem,
    AlertRuleCreate,
    AlertRuleItem,
    AlertRuleUpdate,
    ChannelConfig,
    ChannelConfigItem,
    ChannelConfigUpdate,
    NotificationCreate,
    NotificationItem,
    NotificationMarkRead,
    NotificationUnreadCount,
    SmtpConfigRead,
    SmtpConfigUpdate,
    SmtpTestRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


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
    from src.services.database import db_service

    conditions = ["admin_id = $1"]
    params = [admin.account_id or 0]
    idx = 2

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
        total = await conn.fetchval(f"SELECT COUNT(*) FROM notifications WHERE {where}", *params)
        rows = await conn.fetch(
            f"SELECT * FROM notifications WHERE {where} ORDER BY created_at DESC "
            f"LIMIT ${idx} OFFSET ${idx + 1}",
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
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM notifications WHERE admin_id = $1 AND is_read = false",
            admin.account_id or 0,
        )

    return NotificationUnreadCount(count=count or 0)


@router.post("/notifications/mark-read", response_model=SuccessResponse)
async def mark_notifications_read(
    data: NotificationMarkRead,
    admin: AdminUser = Depends(get_current_admin),
):
    """Mark notifications as read. Empty ids = mark all."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        if data.ids:
            await conn.execute(
                "UPDATE notifications SET is_read = true WHERE admin_id = $1 AND id = ANY($2::bigint[])",
                admin.account_id or 0, data.ids,
            )
        else:
            await conn.execute(
                "UPDATE notifications SET is_read = true WHERE admin_id = $1 AND is_read = false",
                admin.account_id or 0,
            )

    return SuccessResponse(message="Marked as read")


@router.delete("/notifications/{notification_id}", response_model=SuccessResponse)
async def delete_notification(
    notification_id: int,
    admin: AdminUser = Depends(get_current_admin),
):
    """Delete a single notification."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM notifications WHERE id = $1 AND admin_id = $2 RETURNING id",
            notification_id, admin.account_id or 0,
        )

    if not deleted:
        raise HTTPException(status_code=404, detail="Notification not found")

    return SuccessResponse(message="Deleted")


@router.delete("/notifications", response_model=SuccessResponse)
async def delete_old_notifications(
    days: int = Query(30, ge=1, le=365, description="Delete notifications older than N days"),
    admin: AdminUser = Depends(require_permission("notifications", "delete")),
):
    """Delete old notifications."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        count = await conn.fetchval(
            "DELETE FROM notifications WHERE admin_id = $1 AND created_at < NOW() - ($2 || ' days')::interval RETURNING COUNT(*)",
            admin.account_id or 0, str(days),
        )

    return SuccessResponse(message=f"Deleted {count or 0} notifications")


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
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM notification_channels WHERE admin_id = $1 ORDER BY channel_type",
            admin.account_id or 0,
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
    from src.services.database import db_service

    config_json = json.dumps(data.config)
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO notification_channels (admin_id, channel_type, is_enabled, config) "
            "VALUES ($1, $2, $3, $4::jsonb) "
            "ON CONFLICT (admin_id, channel_type) DO UPDATE SET "
            "is_enabled = $3, config = $4::jsonb, updated_at = NOW() "
            "RETURNING *",
            admin.account_id or 0, data.channel_type, data.is_enabled, config_json,
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
    from src.services.database import db_service

    updates = []
    params = [channel_id, admin.account_id or 0]
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
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE notification_channels SET {', '.join(updates)} "
            f"WHERE id = $1 AND admin_id = $2 RETURNING *",
            *params,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Channel not found")

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
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM notification_channels WHERE id = $1 AND admin_id = $2 RETURNING id",
            channel_id, admin.account_id or 0,
        )

    if not deleted:
        raise HTTPException(status_code=404, detail="Channel not found")
    return SuccessResponse(message="Channel deleted")


# ══════════════════════════════════════════════════════════════════
# SMTP Config (global)
# ══════════════════════════════════════════════════════════════════

@router.get("/smtp-config", response_model=SmtpConfigRead)
async def get_smtp_config(
    admin: AdminUser = Depends(require_superadmin()),
):
    """Get SMTP configuration."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow("SELECT * FROM smtp_config ORDER BY id LIMIT 1")

    if not row:
        raise HTTPException(status_code=404, detail="SMTP not configured")

    return SmtpConfigRead(**dict(row))


@router.put("/smtp-config", response_model=SmtpConfigRead)
async def update_smtp_config(
    data: SmtpConfigUpdate,
    admin: AdminUser = Depends(require_superadmin()),
):
    """Update SMTP configuration."""
    from src.services.database import db_service

    updates = []
    params = []
    idx = 1

    for field_name, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            updates.append(f"{field_name} = ${idx}")
            params.append(value)
            idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")

    async with db_service.acquire() as conn:
        # Ensure a row exists
        exists = await conn.fetchval("SELECT id FROM smtp_config ORDER BY id LIMIT 1")
        if not exists:
            await conn.execute(
                "INSERT INTO smtp_config (host, port, from_email) VALUES ('localhost', 587, 'admin@remnawave.local')"
            )

        row = await conn.fetchrow(
            f"UPDATE smtp_config SET {', '.join(updates)} "
            f"WHERE id = (SELECT id FROM smtp_config ORDER BY id LIMIT 1) RETURNING *",
            *params,
        )

    if not row:
        raise HTTPException(status_code=500, detail="Failed to update SMTP config")

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
# Alert Rules
# ══════════════════════════════════════════════════════════════════

@router.get("/alert-rules", response_model=list)
async def list_alert_rules(
    admin: AdminUser = Depends(require_permission("notifications", "view")),
):
    """List all alert rules."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM alert_rules ORDER BY created_at DESC")

    items = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("channels"), str):
            d["channels"] = json.loads(d["channels"])
        items.append(AlertRuleItem(**d))
    return items


@router.post("/alert-rules", response_model=AlertRuleItem, status_code=201)
async def create_alert_rule(
    data: AlertRuleCreate,
    admin: AdminUser = Depends(require_permission("notifications", "create")),
):
    """Create a new alert rule."""
    from src.services.database import db_service

    channels_json = json.dumps(data.channels)
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO alert_rules "
            "(name, description, is_enabled, rule_type, metric, operator, threshold, "
            "duration_minutes, channels, severity, cooldown_minutes, "
            "escalation_admin_id, escalation_minutes, created_by, group_key) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb, $10, $11, $12, $13, $14, $15) "
            "RETURNING *",
            data.name, data.description, data.is_enabled, data.rule_type,
            data.metric, data.operator, data.threshold,
            data.duration_minutes, channels_json, data.severity,
            data.cooldown_minutes, data.escalation_admin_id, data.escalation_minutes,
            admin.account_id, f"alert_{data.metric}",
        )

    d = dict(row)
    if isinstance(d.get("channels"), str):
        d["channels"] = json.loads(d["channels"])
    return AlertRuleItem(**d)


@router.put("/alert-rules/{rule_id}", response_model=AlertRuleItem)
async def update_alert_rule(
    rule_id: int,
    data: AlertRuleUpdate,
    admin: AdminUser = Depends(require_permission("notifications", "edit")),
):
    """Update an alert rule."""
    from src.services.database import db_service

    updates = []
    params = [rule_id]
    idx = 2

    for field_name, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            if field_name == "channels":
                updates.append(f"channels = ${idx}::jsonb")
                params.append(json.dumps(value))
            else:
                updates.append(f"{field_name} = ${idx}")
                params.append(value)
            idx += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE alert_rules SET {', '.join(updates)} WHERE id = $1 RETURNING *",
            *params,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    d = dict(row)
    if isinstance(d.get("channels"), str):
        d["channels"] = json.loads(d["channels"])
    return AlertRuleItem(**d)


@router.delete("/alert-rules/{rule_id}", response_model=SuccessResponse)
async def delete_alert_rule(
    rule_id: int,
    admin: AdminUser = Depends(require_permission("notifications", "delete")),
):
    """Delete an alert rule."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        deleted = await conn.fetchval(
            "DELETE FROM alert_rules WHERE id = $1 RETURNING id", rule_id,
        )

    if not deleted:
        raise HTTPException(status_code=404, detail="Alert rule not found")
    return SuccessResponse(message="Alert rule deleted")


@router.post("/alert-rules/{rule_id}/toggle", response_model=AlertRuleItem)
async def toggle_alert_rule(
    rule_id: int,
    admin: AdminUser = Depends(require_permission("notifications", "edit")),
):
    """Toggle an alert rule's enabled state."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE alert_rules SET is_enabled = NOT is_enabled, updated_at = NOW() "
            "WHERE id = $1 RETURNING *",
            rule_id,
        )

    if not row:
        raise HTTPException(status_code=404, detail="Alert rule not found")

    d = dict(row)
    if isinstance(d.get("channels"), str):
        d["channels"] = json.loads(d["channels"])
    return AlertRuleItem(**d)


# ══════════════════════════════════════════════════════════════════
# Alert Logs
# ══════════════════════════════════════════════════════════════════

@router.get("/alert-logs", response_model=PaginatedResponse)
async def list_alert_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    rule_id: Optional[int] = None,
    acknowledged: Optional[bool] = None,
    admin: AdminUser = Depends(require_permission("notifications", "view")),
):
    """List alert logs."""
    from src.services.database import db_service

    conditions = ["1=1"]
    params = []
    idx = 1

    if rule_id is not None:
        conditions.append(f"rule_id = ${idx}")
        params.append(rule_id)
        idx += 1

    if acknowledged is not None:
        conditions.append(f"acknowledged = ${idx}")
        params.append(acknowledged)
        idx += 1

    where = " AND ".join(conditions)

    async with db_service.acquire() as conn:
        total = await conn.fetchval(f"SELECT COUNT(*) FROM alert_rule_log WHERE {where}", *params)
        rows = await conn.fetch(
            f"SELECT * FROM alert_rule_log WHERE {where} ORDER BY created_at DESC "
            f"LIMIT ${idx} OFFSET ${idx + 1}",
            *params, per_page, (page - 1) * per_page,
        )

    items = []
    for r in rows:
        d = dict(r)
        if isinstance(d.get("channels_notified"), str):
            d["channels_notified"] = json.loads(d["channels_notified"])
        items.append(AlertLogItem(**d))

    pages = max(1, (total + per_page - 1) // per_page)
    return PaginatedResponse(items=items, total=total, page=page, per_page=per_page, pages=pages)


@router.post("/alert-logs/acknowledge", response_model=SuccessResponse)
async def acknowledge_alerts(
    data: AlertLogAcknowledge,
    admin: AdminUser = Depends(require_permission("notifications", "edit")),
):
    """Acknowledge alert log entries."""
    from src.services.database import db_service

    async with db_service.acquire() as conn:
        if data.ids:
            await conn.execute(
                "UPDATE alert_rule_log SET acknowledged = true, acknowledged_by = $1, "
                "acknowledged_at = NOW() WHERE id = ANY($2::bigint[])",
                admin.account_id or 0, data.ids,
            )
        else:
            await conn.execute(
                "UPDATE alert_rule_log SET acknowledged = true, acknowledged_by = $1, "
                "acknowledged_at = NOW() WHERE acknowledged = false",
                admin.account_id or 0,
            )

    return SuccessResponse(message="Acknowledged")
