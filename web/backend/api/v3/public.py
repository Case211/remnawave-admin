"""Public API v3 — users, nodes, hosts, stats, bulk operations.

Authenticated via X-API-Key header. Scopes control access.
"""
import logging
from typing import Any, List, Optional
from uuid import UUID as _UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, model_validator

from web.backend.api.v3.deps import ApiKeyUser, require_scope

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────


class _PublicBase(BaseModel):
    """Base for v3 response models. Coerces asyncpg UUID objects to str so
    pydantic-v2 strict validation does not 500 on the response.
    """

    @model_validator(mode="before")
    @classmethod
    def _coerce_uuid_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            for k, v in list(values.items()):
                if isinstance(v, _UUID):
                    values[k] = str(v)
        return values


class UserPublic(_PublicBase):
    uuid: str
    username: str
    status: Optional[str] = None
    traffic_limit_bytes: Optional[int] = None
    used_traffic_bytes: Optional[int] = None
    expire_at: Optional[str] = None
    online: Optional[bool] = None


class UserCreate(BaseModel):
    username: str
    expire_at: str
    traffic_limit_bytes: Optional[int] = None
    traffic_limit_strategy: str = "MONTH"
    hwid_device_limit: Optional[int] = None
    description: Optional[str] = None
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    tag: Optional[str] = None
    status: Optional[str] = None


class NodePublic(_PublicBase):
    uuid: str
    name: str
    country_code: Optional[str] = None
    is_connected: Optional[bool] = None
    is_disabled: Optional[bool] = None
    users_online: Optional[int] = None


class HostPublic(_PublicBase):
    uuid: str
    remark: Optional[str] = None
    address: Optional[str] = None
    port: Optional[int] = None
    is_disabled: Optional[bool] = None


class StatsPublic(BaseModel):
    total_users: int
    active_users: int
    online_users: int
    total_nodes: int
    connected_nodes: int
    total_traffic_bytes: int


class BulkUuidsRequest(BaseModel):
    uuids: List[str] = Field(..., min_length=1, max_length=500)


class BulkResult(BaseModel):
    success: int
    failed: int
    errors: List[dict] = []


class SuccessResult(BaseModel):
    success: bool
    message: str = ""


# ── Helpers ──────────────────────────────────────────────────────

def _service_unavailable():
    return HTTPException(status_code=503, detail="Service unavailable")


def _not_found(entity: str = "Resource"):
    return HTTPException(status_code=404, detail=f"{entity} not found")


def _get_api_client():
    from shared.api_client import api_client
    return api_client


# ══════════════════════════════════════════════════════════════════
# Users — Read
# ══════════════════════════════════════════════════════════════════

@router.get("/users", response_model=List[UserPublic])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    api_key: ApiKeyUser = Depends(require_scope("users:read")),
):
    """List users with pagination and optional filtering."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []

    conditions = []
    args = []
    idx = 0

    if status:
        idx += 1
        conditions.append(f"LOWER(status) = LOWER(${idx})")
        args.append(status)

    if search:
        idx += 1
        conditions.append(
            f"(LOWER(username) LIKE LOWER(${idx}) OR LOWER(email) LIKE LOWER(${idx}) "
            f"OR uuid::text LIKE ${idx})"
        )
        args.append(f"%{search}%")

    where = " AND ".join(conditions) if conditions else "TRUE"
    idx += 1
    args.append(limit)
    idx += 1
    args.append(offset)

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT uuid, username, status, traffic_limit_bytes, "
            f"used_traffic_bytes, expire_at "
            f"FROM users WHERE {where} ORDER BY username LIMIT ${idx - 1} OFFSET ${idx}",
            *args,
        )

    result = []
    for r in rows:
        d = dict(r)
        if d.get("expire_at"):
            d["expire_at"] = d["expire_at"].isoformat()
        result.append(UserPublic(**d))
    return result


@router.get("/users/{uuid}", response_model=UserPublic)
async def get_user(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("users:read")),
):
    """Get user details by UUID."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise _service_unavailable()

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT uuid, username, status, traffic_limit_bytes, "
            "used_traffic_bytes, expire_at "
            "FROM users WHERE uuid = $1",
            uuid,
        )
    if not row:
        raise _not_found("User")

    d = dict(row)
    if d.get("expire_at"):
        d["expire_at"] = d["expire_at"].isoformat()
    return UserPublic(**d)


# ══════════════════════════════════════════════════════════════════
# Users — Write
# ══════════════════════════════════════════════════════════════════

@router.post("/users", response_model=SuccessResult, status_code=201)
async def create_user(
    body: UserCreate,
    api_key: ApiKeyUser = Depends(require_scope("users:write")),
):
    """Create a new user via Remnawave Panel API."""
    try:
        api = _get_api_client()
        await api.create_user(
            username=body.username,
            expire_at=body.expire_at,
            traffic_limit_bytes=body.traffic_limit_bytes,
            traffic_limit_strategy=body.traffic_limit_strategy,
            hwid_device_limit=body.hwid_device_limit,
            description=body.description,
            telegram_id=body.telegram_id,
            email=body.email,
            tag=body.tag,
            status=body.status,
        )
        return SuccessResult(success=True, message=f"User {body.username} created")
    except Exception as e:
        logger.error("v3 create_user failed: %s", e)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/{uuid}/enable", response_model=SuccessResult)
async def enable_user(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("users:write")),
):
    """Enable a user."""
    try:
        api = _get_api_client()
        await api.enable_user(uuid)
        return SuccessResult(success=True, message="User enabled")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/{uuid}/disable", response_model=SuccessResult)
async def disable_user(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("users:write")),
):
    """Disable a user."""
    try:
        api = _get_api_client()
        await api.disable_user(uuid)
        return SuccessResult(success=True, message="User disabled")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/users/{uuid}/reset-traffic", response_model=SuccessResult)
async def reset_user_traffic(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("users:write")),
):
    """Reset user traffic counter."""
    try:
        api = _get_api_client()
        await api.reset_user_traffic(uuid)
        return SuccessResult(success=True, message="Traffic reset")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{uuid}", response_model=SuccessResult)
async def delete_user(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("users:delete")),
):
    """Delete a user."""
    try:
        api = _get_api_client()
        await api.delete_user(uuid)
        return SuccessResult(success=True, message="User deleted")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ══════════════════════════════════════════════════════════════════
# Nodes — Read
# ══════════════════════════════════════════════════════════════════

@router.get("/nodes", response_model=List[NodePublic])
async def list_nodes(
    api_key: ApiKeyUser = Depends(require_scope("nodes:read")),
):
    """List all nodes with status."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT uuid, name, country_code, is_connected, is_disabled, users_online "
            "FROM nodes ORDER BY name"
        )

    return [NodePublic(**dict(r)) for r in rows]


@router.get("/nodes/{uuid}", response_model=NodePublic)
async def get_node(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("nodes:read")),
):
    """Get node details by UUID."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise _service_unavailable()

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT uuid, name, country_code, is_connected, is_disabled, users_online "
            "FROM nodes WHERE uuid = $1",
            uuid,
        )
    if not row:
        raise _not_found("Node")

    return NodePublic(**dict(row))


# ══════════════════════════════════════════════════════════════════
# Nodes — Write
# ══════════════════════════════════════════════════════════════════

@router.post("/nodes/{uuid}/enable", response_model=SuccessResult)
async def enable_node(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("nodes:write")),
):
    """Enable a node."""
    try:
        api = _get_api_client()
        await api.enable_node(uuid)
        return SuccessResult(success=True, message="Node enabled")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/{uuid}/disable", response_model=SuccessResult)
async def disable_node(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("nodes:write")),
):
    """Disable a node."""
    try:
        api = _get_api_client()
        await api.disable_node(uuid)
        return SuccessResult(success=True, message="Node disabled")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/nodes/{uuid}/restart", response_model=SuccessResult)
async def restart_node(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("nodes:write")),
):
    """Restart a node."""
    try:
        api = _get_api_client()
        await api.restart_node(uuid)
        return SuccessResult(success=True, message="Node restarted")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ══════════════════════════════════════════════════════════════════
# Hosts — Read
# ══════════════════════════════════════════════════════════════════

@router.get("/hosts", response_model=List[HostPublic])
async def list_hosts(
    api_key: ApiKeyUser = Depends(require_scope("hosts:read")),
):
    """List all hosts."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT uuid, remark, address, port, is_disabled "
            "FROM hosts ORDER BY remark"
        )

    return [HostPublic(**dict(r)) for r in rows]


@router.get("/hosts/{uuid}", response_model=HostPublic)
async def get_host(
    uuid: str,
    api_key: ApiKeyUser = Depends(require_scope("hosts:read")),
):
    """Get host details by UUID."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise _service_unavailable()

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT uuid, remark, address, port, is_disabled "
            "FROM hosts WHERE uuid = $1",
            uuid,
        )
    if not row:
        raise _not_found("Host")

    return HostPublic(**dict(row))


# ══════════════════════════════════════════════════════════════════
# Stats
# ══════════════════════════════════════════════════════════════════

@router.get("/stats", response_model=StatsPublic)
async def get_stats(
    api_key: ApiKeyUser = Depends(require_scope("stats:read")),
):
    """Get aggregated system stats."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise _service_unavailable()

    async with db_service.acquire() as conn:
        user_stats = await conn.fetchrow(
            "SELECT "
            "  COUNT(*) AS total_users, "
            "  COUNT(*) FILTER (WHERE LOWER(status) = 'active') AS active_users, "
            "  COUNT(*) FILTER ("
            "    WHERE NULLIF(raw_data->'userTraffic'->>'onlineAt', '')::timestamptz"
            "      >= NOW() - INTERVAL '5 minutes'"
            "  ) AS online_users, "
            "  COALESCE(SUM(used_traffic_bytes), 0)::bigint AS total_traffic_bytes "
            "FROM users"
        )
        node_stats = await conn.fetchrow(
            "SELECT "
            "  COUNT(*) AS total_nodes, "
            "  COUNT(*) FILTER (WHERE is_connected = true AND NOT is_disabled) AS connected_nodes "
            "FROM nodes"
        )

    return StatsPublic(
        total_users=int(user_stats["total_users"]),
        active_users=int(user_stats["active_users"]),
        online_users=int(user_stats["online_users"]),
        total_nodes=int(node_stats["total_nodes"]),
        connected_nodes=int(node_stats["connected_nodes"]),
        total_traffic_bytes=int(user_stats["total_traffic_bytes"]),
    )


# ══════════════════════════════════════════════════════════════════
# Bulk Operations
# ══════════════════════════════════════════════════════════════════

@router.post("/users/bulk/enable", response_model=BulkResult)
async def bulk_enable_users(
    body: BulkUuidsRequest,
    api_key: ApiKeyUser = Depends(require_scope("bulk:write")),
):
    """Enable multiple users at once."""
    api = _get_api_client()
    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api.enable_user(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"uuid": uuid, "error": str(e)})
    return BulkResult(success=success, failed=failed, errors=errors)


@router.post("/users/bulk/disable", response_model=BulkResult)
async def bulk_disable_users(
    body: BulkUuidsRequest,
    api_key: ApiKeyUser = Depends(require_scope("bulk:write")),
):
    """Disable multiple users at once."""
    api = _get_api_client()
    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api.disable_user(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"uuid": uuid, "error": str(e)})
    return BulkResult(success=success, failed=failed, errors=errors)


@router.post("/users/bulk/delete", response_model=BulkResult)
async def bulk_delete_users(
    body: BulkUuidsRequest,
    api_key: ApiKeyUser = Depends(require_scope("bulk:write")),
):
    """Delete multiple users at once. Requires both bulk:write scope."""
    api = _get_api_client()
    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api.delete_user(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"uuid": uuid, "error": str(e)})
    return BulkResult(success=success, failed=failed, errors=errors)


@router.post("/users/bulk/reset-traffic", response_model=BulkResult)
async def bulk_reset_traffic(
    body: BulkUuidsRequest,
    api_key: ApiKeyUser = Depends(require_scope("bulk:write")),
):
    """Reset traffic for multiple users at once."""
    api = _get_api_client()
    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api.reset_user_traffic(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append({"uuid": uuid, "error": str(e)})
    return BulkResult(success=success, failed=failed, errors=errors)


# ══════════════════════════════════════════════════════════════════
# API docs
# ══════════════════════════════════════════════════════════════════

@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def api_v3_docs():
    """Swagger UI for public API v3."""
    from web.backend.core.config import get_web_settings
    if not get_web_settings().external_api_docs:
        raise HTTPException(status_code=404)

    from fastapi.openapi.docs import get_swagger_ui_html
    return get_swagger_ui_html(
        openapi_url="/api/v3/openapi.json",
        title="Remnawave Public API v3",
        swagger_js_url="/api/v3/swagger-ui/swagger-ui-bundle.js",
        swagger_css_url="/api/v3/swagger-ui/swagger-ui.css",
    )


@router.get("/openapi.json", include_in_schema=False)
async def api_v3_openapi():
    """OpenAPI schema for public API v3 endpoints only."""
    from web.backend.core.config import get_web_settings
    if not get_web_settings().external_api_docs:
        raise HTTPException(status_code=404)

    from fastapi.openapi.utils import get_openapi
    from fastapi import FastAPI

    temp = FastAPI()
    temp.include_router(router, prefix="")

    return get_openapi(
        title="Remnawave Public API",
        version="3.0.0",
        description="Public API authenticated via X-API-Key header. "
        "Scopes: users:read, users:write, users:delete, nodes:read, nodes:write, "
        "hosts:read, bulk:write, stats:read",
        routes=temp.routes,
    )
