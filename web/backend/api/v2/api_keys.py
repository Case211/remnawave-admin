"""API key management endpoints."""
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import api_error, E

logger = logging.getLogger(__name__)
router = APIRouter()

AVAILABLE_SCOPES = [
    "users:read",
    "users:write",
    "nodes:read",
    "stats:read",
]


@router.get("/status")
async def api_status(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """Check if external API v3 is enabled."""
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    return {
        "external_api_enabled": settings.external_api_enabled,
        "external_api_docs": settings.external_api_docs,
    }


# ── Schemas ──────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str] = []
    expires_at: Optional[str] = None


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: List[str]
    is_active: bool
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    created_by_username: Optional[str] = None
    created_at: str


class ApiKeyCreated(ApiKeyResponse):
    raw_key: str


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    scopes: Optional[List[str]] = None
    is_active: Optional[bool] = None


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/", response_model=List[ApiKeyResponse])
async def list_api_keys(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """List all API keys (without hashes)."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, name, key_prefix, scopes, is_active, expires_at, "
            "last_used_at, created_by_username, created_at "
            "FROM api_keys ORDER BY created_at DESC"
        )

    result = []
    for r in rows:
        d = dict(r)
        d["scopes"] = list(d["scopes"]) if d["scopes"] else []
        for dt in ("expires_at", "last_used_at", "created_at"):
            if d.get(dt):
                d[dt] = d[dt].isoformat()
        result.append(ApiKeyResponse(**d))
    return result


@router.get("/scopes")
async def list_available_scopes(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """List all available API scopes."""
    return {"scopes": AVAILABLE_SCOPES}


@router.post("/", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    admin: AdminUser = Depends(require_permission("api_keys", "create")),
):
    """Create a new API key. The raw key is returned only once."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    # Validate scopes
    for scope in body.scopes:
        if scope not in AVAILABLE_SCOPES:
            raise api_error(400, E.INVALID_ACTION, f"Unknown scope: {scope}")

    expires_at = None
    if body.expires_at:
        try:
            expires_at = datetime.fromisoformat(body.expires_at)
        except ValueError:
            raise api_error(400, E.INVALID_ACTION, "Invalid expires_at format")

    admin_id = admin.id if hasattr(admin, "id") else (admin.account_id or None)
    admin_username = admin.username or str(admin.telegram_id)

    from web.backend.core.api_key_auth import create_api_key_record
    raw_key, record = await create_api_key_record(
        name=body.name,
        scopes=body.scopes,
        admin_id=admin_id,
        admin_username=admin_username,
        expires_at=expires_at,
    )

    record["scopes"] = list(record["scopes"]) if record["scopes"] else []
    return ApiKeyCreated(raw_key=raw_key, **{
        k: v for k, v in record.items()
        if k in ApiKeyResponse.model_fields or k == "raw_key"
    })


@router.patch("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: int,
    body: ApiKeyUpdate,
    admin: AdminUser = Depends(require_permission("api_keys", "edit")),
):
    """Update API key name, scopes, or active status."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    if "scopes" in updates:
        for scope in updates["scopes"]:
            if scope not in AVAILABLE_SCOPES:
                raise api_error(400, E.INVALID_ACTION, f"Unknown scope: {scope}")

    set_clauses = []
    params = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        params.append(val)
        idx += 1
    params.append(key_id)

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE api_keys SET {', '.join(set_clauses)}, updated_at = NOW() "
            f"WHERE id = ${idx} RETURNING id, name, key_prefix, scopes, is_active, "
            f"expires_at, last_used_at, created_by_username, created_at",
            *params,
        )

    if not row:
        raise api_error(404, E.ADMIN_NOT_FOUND, "API key not found")

    d = dict(row)
    d["scopes"] = list(d["scopes"]) if d["scopes"] else []
    for dt in ("expires_at", "last_used_at", "created_at"):
        if d.get(dt):
            d[dt] = d[dt].isoformat()
    return ApiKeyResponse(**d)


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    admin: AdminUser = Depends(require_permission("api_keys", "delete")),
):
    """Delete an API key."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    async with db_service.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM api_keys WHERE id = $1", key_id,
        )
    if result == "DELETE 0":
        raise api_error(404, E.ADMIN_NOT_FOUND, "API key not found")
