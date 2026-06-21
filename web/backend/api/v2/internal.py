"""Internal API proxy for bot → backend → Panel communication.

This router provides a catch-all proxy endpoint that the bot's
InternalApiClient uses to forward Panel API calls through the backend.
This ensures all operations pass through backend audit logging,
RBAC checks, quota enforcement, and rate limiting.

Over time, the bot should migrate to using the typed endpoints
(like /api/v2/nodes, /api/v2/users, etc.) as they gain full schema support.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from web.backend.api.deps import verify_internal_api_secret
from web.backend.api.v2.roles import AVAILABLE_RESOURCES

logger = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(verify_internal_api_secret)])


_QUOTA_RESOURCES = {"users", "nodes", "hosts"}
_KNOWN_RBAC_RESOURCES = set(AVAILABLE_RESOURCES.keys())


def _method_to_action(method: str, path: str) -> str:
    """Map HTTP method + path to RBAC action."""
    method = method.upper()
    if method == "GET":
        return "view"
    if method == "PATCH":
        return "edit"
    if method == "DELETE":
        return "delete"
    if method == "POST":
        if "bulk" in path.lower():
            return "bulk_operations"
        if not _is_resource_root(path):
            return "edit"
        return "create"
    return "view"


async def _check_permission(
    admin_account_id: int | None,
    resource: str,
    action: str,
) -> bool:
    """Check RBAC permission for a proxy'd request.

    Returns True if:
    - Resource is not in the RBAC system (Panel API-only resources are unconstrained)
    - Admin is legacy (no account_id — from ADMINS env)
    - Admin has superadmin role
    - Admin has the specific (resource, action) permission

    Returns False only if admin lacks the specific permission.
    """
    if not resource or resource not in _KNOWN_RBAC_RESOURCES:
        # Panel-only ресурс (вне RBAC-системы) проходит без проверки прав. Логируем для
        # аудита: чувствительные Panel-операции желательно переводить на типизированные эндпоинты.
        if resource:
            logger.debug("Proxy: non-RBAC resource '%s' (%s) passed without RBAC check", resource, action)
        return True
    if admin_account_id is None:
        return True

    from web.backend.core.rbac import get_admin_account_by_id
    from shared.rbac import has_permission

    admin = await get_admin_account_by_id(admin_account_id)
    if admin is None:
        return False

    role_name = admin.get("role_name", "")
    if role_name == "superadmin":
        return True

    role_id = admin.get("role_id")
    return await has_permission(role_id, resource, action)


def _extract_resource(path: str) -> str:
    """Extract the resource name from a proxy path (e.g. 'api/users' → 'users')."""
    parts = path.strip("/").split("/")
    for p in parts:
        if p and p not in ("api",):
            return p
    return ""


def _is_resource_root(path: str) -> bool:
    """True if the path points at a resource root like 'users', not 'users/{uuid}'."""
    parts = path.strip("/").split("/")
    relevant = [p for p in parts if p and p not in ("api",)]
    return len(relevant) == 1


async def _get_request_body(request: Request) -> dict | None:
    """Safely read JSON body from request (body() + manual json.loads).

    Using body() + json.loads() instead of request.json() because the
    request body stream is consumed here once and cached by Starlette's
    body() method, avoiding issues with repeated stream reads across
    different Starlette versions.
    """
    try:
        body = await request.body()
        if not body:
            return None
        return json.loads(body)
    except Exception:
        return None


async def _proxy(request: Request, path: str):
    """Proxy a request to the Panel API through the backend."""
    from shared.api_client import (
        api_client,
        NetworkError,
        NotFoundError,
        RateLimitError,
        ServerError,
        TimeoutError,
        UnauthorizedError,
        ValidationError,
    )

    target_path = f"/api/{path}" if not path.startswith("api/") else f"/{path}"
    params = dict(request.query_params) if request.query_params else None
    body = await _get_request_body(request)

    # Normalize casing for fields the Panel expects in uppercase
    if body and isinstance(body, dict):
        for _field in ("status", "traffic_limit_strategy"):
            if _field in body and isinstance(body[_field], str):
                body[_field] = body[_field].upper()

    kwargs = {}
    if params:
        kwargs["params"] = params
    if body is not None:
        kwargs["json"] = body

    if request.method not in ("GET", "POST", "PATCH", "DELETE"):
        raise HTTPException(status_code=405, detail="Method not allowed")

    # Read admin identity from bot-forwarded headers
    admin_username = request.headers.get("X-Admin-Username", "bot")
    admin_account_id_raw = request.headers.get("X-Admin-Account-Id")
    admin_account_id = int(admin_account_id_raw) if admin_account_id_raw and admin_account_id_raw.isdigit() else None

    resource = _extract_resource(path)

    # RBAC check: verify admin has permission for this resource+action
    action = _method_to_action(request.method, path)
    if not await _check_permission(admin_account_id, resource, action):
        logger.warning(
            "Permission denied via proxy: %s (%s) -> %s:%s",
            admin_username, admin_account_id, resource, action,
        )
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: {resource}:{action}",
        )

    # Quota check before create operations on quota-tracked resources
    if request.method == "POST" and _is_resource_root(path) and resource in _QUOTA_RESOURCES and admin_account_id is not None:
        from web.backend.core.rbac import check_quota
        allowed, msg = await check_quota(admin_account_id, resource)
        if not allowed:
            raise HTTPException(status_code=403, detail=msg)

    try:
        response = await api_client.request(request.method, target_path, **kwargs)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except UnauthorizedError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))
    except (TimeoutError, NetworkError) as e:
        raise HTTPException(status_code=504, detail=str(e))
    except ServerError as e:
        raise HTTPException(status_code=502, detail=str(e)[:500])

    # Apply creator scope filtering for user list responses (GET /users)
    if request.method == "GET" and resource == "users" and admin_account_id is not None:
        from shared.rbac import get_visible_user_uuids
        # Check if admin is superadmin or has unrestricted access
        from web.backend.core.rbac import get_admin_account_by_id
        admin_info = await get_admin_account_by_id(admin_account_id)
        is_superadmin = admin_info and admin_info.get("role_name") == "superadmin"
        unrestricted = admin_info and admin_info.get("unrestricted_user_access", False)
        
        if not is_superadmin and not unrestricted:
            visible_uuids = await get_visible_user_uuids(admin_account_id, admin_info.get("role_name") if admin_info else None)
            if visible_uuids is not None:
                # Filter the response users
                if isinstance(response, dict):
                    payload = response.get("response", response)
                    if isinstance(payload, dict) and "users" in payload:
                        users = payload.get("users") or []
                        filtered = [u for u in users if u.get("uuid") and str(u["uuid"]).lower() in visible_uuids]
                        payload["users"] = filtered
                        if "total" in payload:
                            payload["total"] = len(filtered)

    # Post-creation: increment counter + update created_by_admin_id
    if admin_account_id is not None:
        try:
            if request.method == "POST" and _is_resource_root(path) and resource in _QUOTA_RESOURCES:
                counter = f"{resource}_created"
                from web.backend.core.rbac import increment_usage_counter
                if not await increment_usage_counter(admin_account_id, counter):
                    # Atomic check failed — another request hit the limit first.
                    # Roll back by deleting the created resource.
                    entity = response.get("response", {}) if isinstance(response, dict) else {}
                    entity_uuid = entity.get("uuid") if isinstance(entity, dict) else None
                    if entity_uuid:
                        try:
                            await api_client.request("DELETE", f"/api/{resource}/{entity_uuid}")
                        except Exception:
                            pass
                    raise HTTPException(status_code=409, detail=f"Quota exceeded: {resource}")

                # For user creation, also update the local DB with created_by_admin_id and sync from panel
                if resource == "users":
                    user = response.get("response", {}) if isinstance(response, dict) else {}
                    user_uuid = user.get("uuid") if isinstance(user, dict) else None
                    if user_uuid:
                        from shared.database import db_service
                        if db_service.is_connected:
                            async with db_service.acquire() as conn:
                                # UPSERT to handle case where user not yet synced to local DB
                                await conn.execute(
                                    """
                                    INSERT INTO users (uuid, created_by_admin_id, created_at)
                                    VALUES ($1, $2, NOW())
                                    ON CONFLICT (uuid) DO UPDATE SET
                                        created_by_admin_id = EXCLUDED.created_by_admin_id
                                    """,
                                    user_uuid, admin_account_id,
                                )
                            # Sync single user from panel to get created_at and other fields
                            from shared.sync import sync_service
                            await sync_service.sync_single_user(user_uuid)
                            # Fetch the synced user from DB to return accurate createdAt
                            synced_user = await db_service.get_user_by_uuid(user_uuid)
                            if synced_user and synced_user.get("created_at"):
                                # Update response with synced data including createdAt
                                if isinstance(response, dict):
                                    payload = response.get("response", response)
                                    if isinstance(payload, dict):
                                        payload["createdAt"] = synced_user["created_at"].isoformat()
                                        # Also update other fields from DB
                                        for key, value in synced_user.items():
                                            if key not in payload and value is not None:
                                                payload[key] = value

            elif request.method == "DELETE" and resource in _QUOTA_RESOURCES:
                counter = f"{resource}_created"
                from web.backend.core.rbac import increment_usage_counter
                await increment_usage_counter(admin_account_id, counter, -1)
        except HTTPException:
            raise
        except Exception as counter_err:
            logger.warning("Counter update failed for %s/%s: %s", resource, request.method, counter_err)

    # Write audit log (fire-and-forget)
    try:
        from web.backend.core.rbac import write_audit_log
        parts = path.strip("/").split("/")
        audit_resource = parts[0] if parts else path
        resource_id = parts[-1] if len(parts) > 1 else ""
        await write_audit_log(
            admin_id=admin_account_id,
            admin_username=admin_username,
            action=f"internal.{request.method.lower()}",
            resource=audit_resource,
            resource_id=resource_id,
            details=json.dumps({"path": path, "method": request.method}),
            ip_address="127.0.0.1",
        )
    except Exception as audit_err:
        logger.debug("Audit log write skipped: %s", audit_err)

    return response


@router.api_route("/proxy/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_to_panel(request: Request, path: str):
    return await _proxy(request, path)


@router.api_route("/proxy", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_to_panel_root(request: Request):
    return await _proxy(request, "")
