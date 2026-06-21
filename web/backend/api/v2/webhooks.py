"""Webhook subscription management and dispatch."""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from shared.db_schema import WEBHOOK_SUBSCRIPTIONS_TABLE, WEBHOOK_DELIVERIES_TABLE
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import api_error, E
from web.backend.core.webhook_security import (
    check_url_safety,
    deliver_once,
    dispatch_event as _dispatch_event,
    sign_payload,
)

logger = logging.getLogger(__name__)
router = APIRouter()

AVAILABLE_EVENTS = [
    "user.created",
    "user.updated",
    "user.deleted",
    "user.blocked",
    "node.online",
    "node.offline",
    "violation.created",
    "automation.triggered",
    "backup.created",
]

_SIGNATURE_VERSIONS = {"v1", "v2"}


# ── Schemas ──────────────────────────────────────────────────────

class WebhookCreate(BaseModel):
    name: str
    url: str
    secret: Optional[str] = None
    events: List[str] = []
    signature_version: Optional[str] = "v2"
    description: Optional[str] = None


class WebhookUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    secret: Optional[str] = None
    events: Optional[List[str]] = None
    is_active: Optional[bool] = None
    signature_version: Optional[str] = None
    description: Optional[str] = None


class WebhookResponse(BaseModel):
    id: int
    name: str
    url: str
    has_secret: bool
    events: List[str]
    is_active: bool
    last_triggered_at: Optional[str] = None
    failure_count: int = 0
    consecutive_failures: int = 0
    auto_disabled_at: Optional[str] = None
    disabled_reason: Optional[str] = None
    signature_version: str = "v1"
    description: Optional[str] = None
    created_at: str


def _row_to_response(row) -> WebhookResponse:
    d = dict(row)
    d["has_secret"] = bool(d.pop("secret", None))
    d["events"] = list(d["events"]) if d["events"] else []
    for dt in ("last_triggered_at", "created_at", "auto_disabled_at", "updated_at"):
        if d.get(dt):
            d[dt] = d[dt].isoformat()
    d.pop("updated_at", None)
    d.pop("created_by_admin_id", None)
    d.setdefault("signature_version", "v1")
    return WebhookResponse(**d)


def _validate_events(events: List[str]) -> None:
    for e in events:
        if e not in AVAILABLE_EVENTS:
            raise api_error(400, E.INVALID_ACTION, f"Unknown event: {e}")


def _validate_signature_version(v: Optional[str]) -> None:
    if v is not None and v not in _SIGNATURE_VERSIONS:
        raise api_error(400, E.INVALID_ACTION, f"Unknown signature_version: {v}")


def _validate_url(url: str) -> None:
    ok, err = check_url_safety(url)
    if not ok:
        raise api_error(400, E.INVALID_ACTION, err or "Invalid URL")


# ── CRUD ─────────────────────────────────────────────────────────

@router.get("/", response_model=List[WebhookResponse])
async def list_webhooks(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(WEBHOOK_SUBSCRIPTIONS_TABLE,
                "id, name, url, secret, events, is_active, last_triggered_at, failure_count, consecutive_failures, auto_disabled_at, disabled_reason, signature_version, description, created_at",
                "ORDER BY created_at DESC")
        )
    return [_row_to_response(r) for r in rows]


@router.get("/events")
async def list_available_events(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    return {"events": AVAILABLE_EVENTS}


@router.post("/", response_model=WebhookResponse, status_code=201)
async def create_webhook(
    body: WebhookCreate,
    admin: AdminUser = Depends(require_permission("api_keys", "create")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    _validate_url(body.url)
    _validate_events(body.events)
    _validate_signature_version(body.signature_version)

    admin_id = admin.id if hasattr(admin, "id") else (admin.account_id or None)
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            insert_sql(WEBHOOK_SUBSCRIPTIONS_TABLE,
                ["name", "url", "secret", "events", "created_by_admin_id", "signature_version", "description"],
                returning="id, name, url, secret, events, is_active, last_triggered_at, failure_count, consecutive_failures, auto_disabled_at, disabled_reason, signature_version, description, created_at"),
            body.name, body.url, body.secret, body.events, admin_id,
            body.signature_version or "v2", body.description,
        )
    return _row_to_response(row)


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(
    webhook_id: int,
    body: WebhookUpdate,
    admin: AdminUser = Depends(require_permission("api_keys", "edit")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)
    if "events" in updates:
        _validate_events(updates["events"])
    if "signature_version" in updates:
        _validate_signature_version(updates["signature_version"])
    if "url" in updates:
        _validate_url(updates["url"])

    # Re-enable clears auto-disable state and resets consecutive failures.
    if updates.get("is_active") is True:
        updates["auto_disabled_at"] = None
        updates["disabled_reason"] = None
        updates["consecutive_failures"] = 0

    set_clauses = []
    params = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        params.append(val)
        idx += 1
    params.append(webhook_id)

    async with db_service.acquire() as conn:
        set_str = ', '.join(set_clauses)
        row = await conn.fetchrow(
            update_sql(WEBHOOK_SUBSCRIPTIONS_TABLE, f"{set_str}, updated_at = NOW()", f"id = ${idx}", returning="id, name, url, secret, events, is_active, last_triggered_at, failure_count, consecutive_failures, auto_disabled_at, disabled_reason, signature_version, description, created_at"),
            *params,
        )
    if not row:
        raise api_error(404, E.ADMIN_NOT_FOUND, "Webhook not found")
    return _row_to_response(row)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(
    webhook_id: int,
    admin: AdminUser = Depends(require_permission("api_keys", "delete")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    async with db_service.acquire() as conn:
        result = await conn.execute(
            delete_sql(WEBHOOK_SUBSCRIPTIONS_TABLE, "id = $1"), webhook_id,
        )
    if result == "DELETE 0":
        raise api_error(404, E.ADMIN_NOT_FOUND, "Webhook not found")


# ── Test & Delivery History ──────────────────────────────────────

class WebhookTestResult(BaseModel):
    status_code: Optional[int] = None
    response_body: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None


class WebhookDeliveryResponse(BaseModel):
    id: int
    webhook_id: int
    event: str
    status_code: int
    response_body: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[int] = None
    sent_at: str


@router.post("/{webhook_id}/test", response_model=WebhookTestResult)
async def test_webhook(
    webhook_id: int,
    admin: AdminUser = Depends(require_permission("api_keys", "edit")),
):
    """Send a synthetic payload to the webhook URL. Not persisted to deliveries."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)
    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            select_sql(WEBHOOK_SUBSCRIPTIONS_TABLE, "id, url, secret, signature_version", "WHERE id = $1"),
            webhook_id,
        )
    if not row:
        raise api_error(404, E.ADMIN_NOT_FOUND, "Webhook not found")

    ok, err = check_url_safety(row["url"])
    if not ok:
        return WebhookTestResult(error=err, duration_ms=0)

    payload = {"message": "This is a test payload from Remnawave Admin.", "webhook_id": webhook_id}
    _ok, status_code, response_body, error, elapsed = await deliver_once(
        webhook_id, row["url"], row["secret"],
        row["signature_version"] or "v1",
        "webhook.test", payload,
    )
    return WebhookTestResult(
        status_code=status_code or None,
        response_body=response_body[:5000] if response_body else None,
        error=error,
        duration_ms=elapsed,
    )


@router.get("/{webhook_id}/deliveries", response_model=List[WebhookDeliveryResponse])
async def list_deliveries(
    webhook_id: int,
    limit: int = Query(50, ge=1, le=200),
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(WEBHOOK_DELIVERIES_TABLE,
                "id, webhook_id, event, status_code, response_body, error, duration_ms, sent_at",
                "WHERE webhook_id = $1 ORDER BY sent_at DESC LIMIT $2"),
            webhook_id, limit,
        )
    result = []
    for r in rows:
        d = dict(r)
        if d.get("sent_at"):
            d["sent_at"] = d["sent_at"].isoformat()
        result.append(WebhookDeliveryResponse(**d))
    return result


# ── Dispatch (public re-export) ──────────────────────────────────

async def dispatch_webhook_event(event: str, payload: dict) -> None:
    """Backward-compatible alias — dispatches via webhook_security module."""
    await _dispatch_event(event, payload)
