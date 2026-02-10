"""Audit Log API endpoints — dedicated page-level API."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from web.backend.api.deps import require_permission, AdminUser

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None, description="Filter by action (partial match)"),
    resource: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    date_from: Optional[str] = Query(None, description="ISO date from"),
    date_to: Optional[str] = Query(None, description="ISO date to"),
    search: Optional[str] = Query(None, description="Free text search"),
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Get audit log entries with rich filtering."""
    from web.backend.core.rbac import get_audit_logs as _get_logs

    items, total = await _get_logs(
        limit=limit,
        offset=offset,
        admin_id=admin_id,
        action=action,
        resource=resource,
        resource_id=resource_id,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )

    # Serialize datetime objects
    for item in items:
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])

    return {"items": items, "total": total}


@router.get("/actions")
async def get_distinct_actions(
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Get distinct action names for filter dropdown."""
    from web.backend.core.rbac import get_audit_distinct_actions
    actions = await get_audit_distinct_actions()
    return actions


@router.get("/resource/{resource}/{resource_id}")
async def get_resource_history(
    resource: str,
    resource_id: str,
    limit: int = Query(50, ge=1, le=200),
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Get audit history for a specific resource (e.g., user change history)."""
    from web.backend.core.rbac import get_audit_logs_for_resource

    items = await get_audit_logs_for_resource(resource, resource_id, limit)

    for item in items:
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])

    return {"items": items}


@router.get("/stats")
async def get_audit_stats(
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Get audit log statistics for dashboard widgets."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return {"total": 0, "today": 0, "by_resource": {}, "by_admin": []}

        async with db_service.acquire() as conn:
            # Total count
            total = await conn.fetchval("SELECT COUNT(*) FROM admin_audit_log")

            # Today's count
            today = await conn.fetchval(
                "SELECT COUNT(*) FROM admin_audit_log "
                "WHERE created_at >= CURRENT_DATE"
            )

            # By resource
            resource_rows = await conn.fetch(
                "SELECT resource, COUNT(*) as count FROM admin_audit_log "
                "WHERE resource IS NOT NULL "
                "GROUP BY resource ORDER BY count DESC"
            )
            by_resource = {r["resource"]: r["count"] for r in resource_rows}

            # Top admins today
            admin_rows = await conn.fetch(
                "SELECT admin_username, COUNT(*) as count FROM admin_audit_log "
                "WHERE created_at >= CURRENT_DATE "
                "GROUP BY admin_username ORDER BY count DESC LIMIT 10"
            )
            by_admin = [
                {"username": r["admin_username"], "count": r["count"]}
                for r in admin_rows
            ]

            return {
                "total": total,
                "today": today,
                "by_resource": by_resource,
                "by_admin": by_admin,
            }
    except Exception as e:
        logger.error("get_audit_stats failed: %s", e)
        return {"total": 0, "today": 0, "by_resource": {}, "by_admin": []}
