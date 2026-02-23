"""Public API v3 — users, nodes, stats.

Authenticated via X-API-Key header. Scopes control access.
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from web.backend.api.v3.deps import ApiKeyUser, require_scope

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class UserPublic(BaseModel):
    uuid: str
    username: str
    status: Optional[str] = None
    traffic_limit_bytes: Optional[int] = None
    used_traffic_bytes: Optional[int] = None
    expire_at: Optional[str] = None
    online: Optional[bool] = None


class NodePublic(BaseModel):
    uuid: str
    name: str
    country_code: Optional[str] = None
    is_connected: Optional[bool] = None
    is_disabled: Optional[bool] = None
    users_online: Optional[int] = None


class StatsPublic(BaseModel):
    total_users: int
    active_users: int
    online_users: int
    total_nodes: int
    connected_nodes: int
    total_traffic_bytes: int


# ── Users ────────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserPublic])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None),
    api_key: ApiKeyUser = Depends(require_scope("users:read")),
):
    """List users with pagination."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []

    async with db_service.acquire() as conn:
        if status:
            rows = await conn.fetch(
                "SELECT uuid, username, status, traffic_limit_bytes, "
                "used_traffic_bytes, expire_at, online "
                "FROM users WHERE status = $1 ORDER BY username LIMIT $2 OFFSET $3",
                status, limit, offset,
            )
        else:
            rows = await conn.fetch(
                "SELECT uuid, username, status, traffic_limit_bytes, "
                "used_traffic_bytes, expire_at, online "
                "FROM users ORDER BY username LIMIT $1 OFFSET $2",
                limit, offset,
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
            "used_traffic_bytes, expire_at, online "
            "FROM users WHERE uuid = $1",
            uuid,
        )
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")

    d = dict(row)
    if d.get("expire_at"):
        d["expire_at"] = d["expire_at"].isoformat()
    return UserPublic(**d)


# ── Nodes ────────────────────────────────────────────────────────

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
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Node not found")

    return NodePublic(**dict(row))


# ── Stats ────────────────────────────────────────────────────────

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
            "  COUNT(*) FILTER (WHERE status = 'active') AS active_users, "
            "  COUNT(*) FILTER (WHERE online = true) AS online_users, "
            "  COALESCE(SUM(used_traffic_bytes), 0) AS total_traffic_bytes "
            "FROM users"
        )
        node_stats = await conn.fetchrow(
            "SELECT "
            "  COUNT(*) AS total_nodes, "
            "  COUNT(*) FILTER (WHERE is_connected = true) AS connected_nodes "
            "FROM nodes"
        )

    return StatsPublic(
        total_users=user_stats["total_users"],
        active_users=user_stats["active_users"],
        online_users=user_stats["online_users"],
        total_nodes=node_stats["total_nodes"],
        connected_nodes=node_stats["connected_nodes"],
        total_traffic_bytes=user_stats["total_traffic_bytes"],
    )


def _service_unavailable():
    from fastapi import HTTPException
    return HTTPException(status_code=503, detail="Service unavailable")


# ── API docs (always enabled) ───────────────────────────────────

@router.get("/docs", response_class=HTMLResponse, include_in_schema=False)
async def api_v3_docs():
    """Swagger UI for public API v3."""
    return """<!DOCTYPE html>
<html><head><title>Remnawave Public API v3</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head><body>
<div id="swagger-ui"></div>
<script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>
SwaggerUIBundle({
  url: '/api/v3/openapi.json',
  dom_id: '#swagger-ui',
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
  layout: 'BaseLayout'
})
</script></body></html>"""


@router.get("/openapi.json", include_in_schema=False)
async def api_v3_openapi():
    """OpenAPI schema for public API v3 endpoints only."""
    from fastapi.openapi.utils import get_openapi
    from fastapi import FastAPI

    # Build a temporary app just to generate v3 schema
    temp = FastAPI()
    temp.include_router(router, prefix="")

    return get_openapi(
        title="Remnawave Public API",
        version="3.0.0",
        description="Public API authenticated via X-API-Key header.",
        routes=temp.routes,
    )
