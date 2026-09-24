"""Audit Log API endpoints — dedicated page-level API."""
import csv
import io
import json
import logging
from datetime import timedelta
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Query, Response

from web.backend.api.deps import require_permission, AdminUser
from shared import timefmt
from shared.db_schema import AUDIT_TABLE
from shared.db_query import select_sql

logger = logging.getLogger(__name__)
router = APIRouter()

# Разбивка по разделам в статистике — за этот период, а не за всю историю
STATS_PERIOD_DAYS = 30


@router.get("")
async def get_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    cursor: Optional[int] = Query(None, description="Cursor (last seen ID) for efficient pagination"),
    admin_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None, description="Filter by action (partial match)"),
    resource: Optional[str] = Query(None, description="Filter by resource type"),
    resource_id: Optional[str] = Query(None, description="Filter by resource ID"),
    date_from: Optional[str] = Query(None, description="ISO date from"),
    date_to: Optional[str] = Query(None, description="ISO date to"),
    search: Optional[str] = Query(None, description="Free text search"),
    admin_username: Optional[str] = Query(None, description="Exact admin username"),
    ip_address: Optional[str] = Query(None, description="Exact client IP"),
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Get audit log entries with rich filtering.

    Supports two pagination modes:
    - offset-based (legacy): ?limit=50&offset=100
    - cursor-based (efficient): ?limit=50&cursor=12345
      Returns next_cursor for fetching the next page.
    """
    from web.backend.core.audit import get_audit_logs as _get_logs

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
        cursor=cursor,
        admin_username=admin_username,
        ip_address=ip_address,
    )

    # Serialize datetime objects
    for item in items:
        if item.get("created_at"):
            item["created_at"] = str(item["created_at"])

    # Compute next_cursor from the last item's id
    next_cursor = None
    if items and len(items) == limit:
        last_id = items[-1].get("id")
        if last_id is not None:
            next_cursor = last_id

    return {"items": items, "total": total, "next_cursor": next_cursor}


EXPORT_MAX_ROWS = 50_000
_EXPORT_COLUMNS = ["id", "created_at", "admin_username", "action", "resource", "resource_id", "details", "ip_address"]


@router.get("/export")
async def export_audit_logs(
    fmt: Literal["csv", "json"] = Query("csv", alias="format"),
    admin_id: Optional[int] = Query(None),
    action: Optional[str] = Query(None),
    resource: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    admin_username: Optional[str] = Query(None),
    ip_address: Optional[str] = Query(None),
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Выгрузка всего, что попадает под фильтры страницы (до EXPORT_MAX_ROWS строк),
    а не только видимой страницы. Время — в UTC ISO."""
    from web.backend.core.audit import get_audit_logs as _get_logs

    filters = dict(admin_id=admin_id, action=action, resource=resource, resource_id=resource_id,
                   date_from=date_from, date_to=date_to, search=search,
                   admin_username=admin_username, ip_address=ip_address)
    rows: list = []
    cursor = None
    while len(rows) < EXPORT_MAX_ROWS:
        page, _ = await _get_logs(limit=1000, cursor=cursor, **filters)
        if not page:
            break
        rows.extend(page)
        cursor = page[-1]["id"]
        if len(page) < 1000:
            break
    rows = rows[:EXPORT_MAX_ROWS]
    for row in rows:
        created = row.get("created_at")
        row["created_at"] = created.isoformat() if hasattr(created, "isoformat") else created

    stamp = timefmt.now().strftime("%Y%m%d-%H%M")
    if fmt == "json":
        body = json.dumps([{c: r.get(c) for c in _EXPORT_COLUMNS} for r in rows], ensure_ascii=False, default=str)
        return Response(body, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="audit-{stamp}.json"'})

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(_EXPORT_COLUMNS)
    for r in rows:
        writer.writerow([r.get(c) if r.get(c) is not None else "" for c in _EXPORT_COLUMNS])
    # BOM — чтобы Excel открыл кириллицу без перекодировки
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="audit-{stamp}.csv"'})


@router.get("/admins")
async def get_audit_admins(
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Кто есть в журнале — для фильтра по админу (включая ключи API и легаси-админов)."""
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return []
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(AUDIT_TABLE, "admin_username, COUNT(*) AS count",
                           "GROUP BY admin_username ORDER BY count DESC LIMIT 200"),
            )
        return [{"username": r["admin_username"], "count": r["count"]} for r in rows]
    except Exception as e:
        logger.error("get_audit_admins failed: %s", e)
        return []


@router.get("/actions")
async def get_distinct_actions(
    admin: AdminUser = Depends(require_permission("audit", "view")),
):
    """Get distinct action names for filter dropdown."""
    from web.backend.core.audit import get_audit_distinct_actions
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
    from web.backend.core.audit import get_audit_logs_for_resource

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
        from shared.database import db_service
        if not db_service.is_connected:
            return {"total": 0, "today": 0, "by_resource": {}, "by_admin": []}

        # «Сегодня» — с полуночи по часам панели: CURRENT_DATE базы — это UTC
        day_start = timefmt.parse_filter(timefmt.now().date().isoformat())
        async with db_service.acquire() as conn:
            # Total count
            total = await conn.fetchval(
                select_sql(
                    AUDIT_TABLE,
                    "COUNT(*)",
                ),
            )
            period_start = day_start - timedelta(days=STATS_PERIOD_DAYS - 1)

            today = await conn.fetchval(
                select_sql(
                    AUDIT_TABLE,
                    "COUNT(*)",
                    "WHERE created_at >= $1",
                ),
                day_start,
            )

            # By resource
            resource_rows = await conn.fetch(
                select_sql(
                    AUDIT_TABLE,
                    "resource, COUNT(*) as count",
                    "WHERE resource IS NOT NULL AND created_at >= $1 GROUP BY resource ORDER BY count DESC",
                ),
                period_start,
            )
            by_resource = {r["resource"]: r["count"] for r in resource_rows}

            # Top admins today
            admin_rows = await conn.fetch(
                select_sql(
                    AUDIT_TABLE,
                    "admin_username, COUNT(*) as count",
                    "WHERE created_at >= $1 GROUP BY admin_username ORDER BY count DESC LIMIT 10",
                ),
                day_start,
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
                "period_days": STATS_PERIOD_DAYS,
            }
    except Exception as e:
        logger.error("get_audit_stats failed: %s", e)
        return {"total": 0, "today": 0, "by_resource": {}, "by_admin": []}
