"""Webhook subscription management and dispatch."""
import hashlib
import hmac
import json
import logging
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import api_error, E

logger = logging.getLogger(__name__)
router = APIRouter()

AVAILABLE_EVENTS = [
    "user.created",
    "user.updated",
    "user.deleted",
    "node.online",
    "node.offline",
    "violation.created",
    "backup.created",
]


# ── Schemas ──────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    name: str
    url: str
    secret: Optional[str] = None
    events: List[str] = []


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    has_secret: bool
    events: List[str]
    is_active: bool
    last_triggered_at: Optional[str] = None
    failure_count: int = 0
    created_at: str


# ── CRUD ─────────────────────────────────────────────────────────

@router.get("/", response_model=List[WebhookResponse])
async def list_webhooks(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """List all webhook subscriptions."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, url, secret, events, is_active, "
            "last_triggered_at, failure_count, created_at "
            "FROM webhook_subscriptions ORDER BY created_at DESC"
        )

    result = []
    for r in rows:
        d = dict(r)
        d["has_secret"] = bool(d.pop("secret", None))
        d["events"] = list(d["events"]) if d["events"] else []
        for dt in ("last_triggered_at", "created_at"):
            if d.get(dt):
                d[dt] = d[dt].isoformat()
        result.append(WebhookResponse(**d))
    return result


@router.get("/events")
async def list_available_events(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """List all available webhook event types."""
    return {"events": AVAILABLE_EVENTS}


@router.post("/", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    body: WebhookCreate,
    admin: AdminUser = Depends(require_permission("api_keys", "create")),
):
    """Create a new webhook subscription."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    for event in body.events:
        if event not in AVAILABLE_EVENTS:
            raise api_error(400, E.INVALID_ACTION, f"Unknown event: {event}")

    admin_id = admin.id if hasattr(admin, "id") else (admin.account_id or None)

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO webhook_subscriptions (name, url, secret, events, created_by_admin_id) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING *",
            body.name, body.url, body.secret, body.events, admin_id,
        )

    d = dict(row)
    d["has_secret"] = bool(d.pop("secret", None))
    d["events"] = list(d["events"]) if d["events"] else []
    for dt in ("last_triggered_at", "created_at", "updated_at"):
        if d.get(dt):
            d[dt] = d[dt].isoformat()
    d.pop("updated_at", None)
    d.pop("created_by_admin_id", None)
    return WebhookResponse(**d)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdate,
    admin: AdminUser = Depends(require_permission("api_keys", "edit")),
):
    """Update a webhook subscription."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    if "events" in updates:
        for event in updates["events"]:
            if event not in AVAILABLE_EVENTS:
                raise api_error(400, E.INVALID_ACTION, f"Unknown event: {event}")

    set_clauses = []
    params = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        params.append(val)
        idx += 1
    params.append(webhook_id)

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE webhook_subscriptions SET {', '.join(set_clauses)}, updated_at = NOW() "
            f"WHERE id = ${idx} "
            f"RETURNING id, name, url, secret, events, is_active, last_triggered_at, failure_count, created_at",
            *params,
        )

    if not row:
        raise api_error(404, E.ADMIN_NOT_FOUND, "Webhook not found")

    d = dict(row)
    d["has_secret"] = bool(d.pop("secret", None))
    d["events"] = list(d["events"]) if d["events"] else []
    for dt in ("last_triggered_at", "created_at"):
        if d.get(dt):
            d[dt] = d[dt].isoformat()
    return WebhookResponse(**d)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    admin: AdminUser = Depends(require_permission("api_keys", "delete")),
):
    """Delete a webhook subscription."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    async with db_service.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM webhook_subscriptions WHERE id = $1", webhook_id,
        )
    if result == "DELETE 0":
        raise api_error(404, E.ADMIN_NOT_FOUND, "Webhook not found")


# ── Dispatch ─────────────────────────────────────────────────────

async def dispatch_webhook_event(event: str, payload: dict) -> None:
    """Send webhook event to all active subscriptions matching this event.

    Fire-and-forget: errors are logged, not raised.
    """
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, url, secret FROM webhook_subscriptions "
                "WHERE is_active = true AND $1 = ANY(events)",
                event,
            )

        if not rows:
            return

        body = json.dumps({"event": event, "data": payload}, default=str)

        async with httpx.AsyncClient(timeout=10.0) as client:
            for row in rows:
                try:
                    headers = {"Content-Type": "application/json"}
                    if row["secret"]:
                        sig = hmac.new(
                            row["secret"].encode(),
                            body.encode(),
                            hashlib.sha256,
                        ).hexdigest()
                        headers["X-Webhook-Signature"] = f"sha256={sig}"

                    resp = await client.post(row["url"], content=body, headers=headers)

                    async with db_service.acquire() as conn:
                        if resp.is_success:
                            await conn.execute(
                                "UPDATE webhook_subscriptions SET last_triggered_at = NOW(), "
                                "failure_count = 0 WHERE id = $1",
                                row["id"],
                            )
                        else:
                            await conn.execute(
                                "UPDATE webhook_subscriptions SET failure_count = failure_count + 1 "
                                "WHERE id = $1",
                                row["id"],
                            )
                            logger.warning(
                                "Webhook %d returned %d for event %s",
                                row["id"], resp.status_code, event,
                            )
                except Exception as e:
                    logger.warning("Webhook %d dispatch failed: %s", row["id"], e)
                    try:
                        async with db_service.acquire() as conn:
                            await conn.execute(
                                "UPDATE webhook_subscriptions SET failure_count = failure_count + 1 "
                                "WHERE id = $1",
                                row["id"],
                            )
                    except Exception:
                        pass
    except Exception as e:
        logger.error("Webhook dispatch error: %s", e)
