"""Squads management — proxy CRUD to Remnawave Panel API."""
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from web.backend.api.deps import require_permission, AdminUser
from web.backend.core.errors import api_error, E
from web.backend.core.rate_limit import limiter, RATE_BULK
from web.backend.core.rbac import get_scope, check_access, resolve_allowed_actions_map

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Schemas ──────────────────────────────────────────────────────

class CreateInternalSquadRequest(BaseModel):
    name: str
    inbounds: List[str] = []


class UpdateInternalSquadRequest(BaseModel):
    name: Optional[str] = None
    inbounds: Optional[List[str]] = None


class CreateExternalSquadRequest(BaseModel):
    name: str


class UpdateExternalSquadRequest(BaseModel):
    name: Optional[str] = None


# ── Internal Squads ──────────────────────────────────────────────

@router.get("/internal")
async def list_internal_squads(
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """List internal squads from Panel API."""
    from shared.api_client import api_client
    try:
        result = await api_client.get_internal_squads()
        payload = result.get("response", result) if isinstance(result, dict) else result
        squads = payload.get("internalSquads", []) if isinstance(payload, dict) else payload
        squads = squads if isinstance(squads, list) else []
        scope = await get_scope(admin, "squad", "view")
        if scope is not None:
            squads = [s for s in squads if str(s.get("uuid", "")).lower() in scope]
        actions_map = await resolve_allowed_actions_map(
            admin, "squad", [str(s.get("uuid", "")) for s in squads if s.get("uuid")],
        )
        for s in squads:
            uid = str(s.get("uuid", "")).lower()
            if uid in actions_map:
                s["allowed_actions"] = actions_map[uid]
        return squads
    except Exception as e:
        logger.error("Failed to list internal squads: %s", e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.post("/internal", status_code=201)
@limiter.limit(RATE_BULK)
async def create_internal_squad(
    request: Request,
    body: CreateInternalSquadRequest,
    admin: AdminUser = Depends(require_permission("users", "create")),
):
    """Create an internal squad via Panel API."""
    from shared.api_client import api_client
    try:
        result = await api_client.create_internal_squad(body.name, body.inbounds)
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to create internal squad: %s", e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.patch("/internal/{squad_uuid}")
async def update_internal_squad(
    squad_uuid: str,
    body: UpdateInternalSquadRequest,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Update an internal squad via Panel API."""
    if not await check_access(admin, "squad", squad_uuid, "edit"):
        raise api_error(403, E.FORBIDDEN)
    from shared.api_client import api_client
    try:
        result = await api_client.update_internal_squad(
            squad_uuid, name=body.name, inbounds=body.inbounds,
        )
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to update internal squad %s: %s", squad_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.delete("/internal/{squad_uuid}")
async def delete_internal_squad(
    squad_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "delete")),
):
    """Delete an internal squad via Panel API."""
    if not await check_access(admin, "squad", squad_uuid, "delete"):
        raise api_error(403, E.FORBIDDEN)
    from shared.api_client import api_client
    try:
        await api_client.delete_internal_squad(squad_uuid)
        return {"success": True}
    except Exception as e:
        logger.error("Failed to delete internal squad %s: %s", squad_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


# ── External Squads ──────────────────────────────────────────────

@router.get("/external")
async def list_external_squads(
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """List external squads from Panel API."""
    from shared.api_client import api_client
    try:
        result = await api_client.get_external_squads()
        payload = result.get("response", result) if isinstance(result, dict) else result
        squads = payload.get("externalSquads", []) if isinstance(payload, dict) else payload
        squads = squads if isinstance(squads, list) else []
        scope = await get_scope(admin, "squad", "view")
        if scope is not None:
            squads = [s for s in squads if str(s.get("uuid", "")).lower() in scope]
        actions_map = await resolve_allowed_actions_map(
            admin, "squad", [str(s.get("uuid", "")) for s in squads if s.get("uuid")],
        )
        for s in squads:
            uid = str(s.get("uuid", "")).lower()
            if uid in actions_map:
                s["allowed_actions"] = actions_map[uid]
        return squads
    except Exception as e:
        logger.error("Failed to list external squads: %s", e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.post("/external", status_code=201)
@limiter.limit(RATE_BULK)
async def create_external_squad(
    request: Request,
    body: CreateExternalSquadRequest,
    admin: AdminUser = Depends(require_permission("users", "create")),
):
    """Create an external squad via Panel API."""
    from shared.api_client import api_client
    try:
        result = await api_client.create_external_squad(body.name)
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to create external squad: %s", e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.patch("/external/{squad_uuid}")
async def update_external_squad(
    squad_uuid: str,
    body: UpdateExternalSquadRequest,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Update an external squad via Panel API."""
    if not await check_access(admin, "squad", squad_uuid, "edit"):
        raise api_error(403, E.FORBIDDEN)
    from shared.api_client import api_client
    try:
        payload = {"uuid": squad_uuid}
        if body.name is not None:
            payload["name"] = body.name
        result = await api_client.update_external_squad(payload)
        resp = result.get("response", result) if isinstance(result, dict) else result
        return resp
    except Exception as e:
        logger.error("Failed to update external squad %s: %s", squad_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.delete("/external/{squad_uuid}")
async def delete_external_squad(
    squad_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "delete")),
):
    """Delete an external squad via Panel API."""
    if not await check_access(admin, "squad", squad_uuid, "delete"):
        raise api_error(403, E.FORBIDDEN)
    from shared.api_client import api_client
    try:
        await api_client.delete_external_squad(squad_uuid)
        return {"success": True}
    except Exception as e:
        logger.error("Failed to delete external squad %s: %s", squad_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


# ── Inbounds (for squad editing) ─────────────────────────────────

@router.get("/inbounds")
async def list_inbounds(
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """List all available inbounds from Panel API."""
    from shared.api_client import api_client
    try:
        result = await api_client.get_all_inbounds()
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload if isinstance(payload, list) else []
    except Exception as e:
        logger.error("Failed to list inbounds: %s", e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)
