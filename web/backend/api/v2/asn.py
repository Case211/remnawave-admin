"""ASN database management — local RIPE sync."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


class ASNSyncRequest(BaseModel):
    limit: Optional[int] = None


@router.get("/search")
async def search_asn(
    org_name: str = Query(..., min_length=2),
    admin: AdminUser = Depends(require_permission("reports", "view")),
):
    """Search ASN records by organization name."""
    try:
        from shared.database import db_service as db
        records = await db.get_asn_by_org_name(org_name)
        for r in records:
            for key in ("created_at", "updated_at", "last_synced_at"):
                if r.get(key):
                    r[key] = str(r[key])
        return {"items": records, "total": len(records)}
    except Exception as e:
        logger.error("Failed to search ASN: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/by-type/{provider_type}")
async def get_asn_by_type(
    provider_type: str,
    admin: AdminUser = Depends(require_permission("reports", "view")),
):
    """Get ASN records by provider type."""
    try:
        from shared.database import db_service as db
        if provider_type == "unknown":
            # Records with NULL provider_type
            async with db.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM asn_russia WHERE provider_type IS NULL AND is_active = true ORDER BY org_name"
                )
                records = [dict(row) for row in rows]
        else:
            records = await db.get_asn_by_provider_type(provider_type)
        for r in records:
            for key in ("created_at", "updated_at", "last_synced_at"):
                if r.get(key):
                    r[key] = str(r[key])
        return {"items": records, "total": len(records)}
    except Exception as e:
        logger.error("Failed to get ASN by type: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_asn_stats(
    admin: AdminUser = Depends(require_permission("reports", "view")),
):
    """Get ASN database statistics."""
    try:
        from shared.database import db_service as db
        async with db.acquire() as conn:
            # Total active records
            total = await conn.fetchval(
                "SELECT COUNT(*) FROM asn_russia WHERE is_active = true"
            ) or 0

            # Count by provider_type (single query)
            type_rows = await conn.fetch(
                """
                SELECT COALESCE(provider_type, 'unknown') as provider_type, COUNT(*) as cnt
                FROM asn_russia
                WHERE is_active = true
                GROUP BY provider_type
                ORDER BY cnt DESC
                """
            )
            by_type = {r["provider_type"]: r["cnt"] for r in type_rows}

        return {
            "total": total,
            "by_type": by_type,
        }
    except Exception as e:
        logger.error("Failed to get ASN stats: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{asn}")
async def get_asn(
    asn: int,
    admin: AdminUser = Depends(require_permission("reports", "view")),
):
    """Get a single ASN record."""
    try:
        from shared.database import db_service as db
        record = await db.get_asn_record(asn)
        if not record:
            raise HTTPException(status_code=404, detail="ASN not found")
        for key in ("created_at", "updated_at", "last_synced_at"):
            if record.get(key):
                record[key] = str(record[key])
        return record
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get ASN: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_asn_database(
    data: ASNSyncRequest,
    admin: AdminUser = Depends(require_permission("reports", "create")),
):
    """Trigger ASN database synchronization from RIPE."""
    try:
        from shared.asn_parser import asn_parser
        result = await asn_parser.sync_russian_asn_database(limit=data.limit)
        return {
            "status": "ok",
            "total": result.get("total", 0),
            "success": result.get("success", 0),
            "failed": result.get("failed", 0),
            "skipped": result.get("skipped", 0),
        }
    except Exception as e:
        logger.error("Failed to sync ASN: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
