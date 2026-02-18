"""Violation reports management — local database."""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, require_permission

logger = logging.getLogger(__name__)
router = APIRouter()


class GenerateReportRequest(BaseModel):
    report_type: str  # daily, weekly, monthly
    start_date: Optional[str] = None
    end_date: Optional[str] = None


@router.get("")
async def list_reports(
    report_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    admin: AdminUser = Depends(require_permission("reports", "view")),
):
    """List violation reports history."""
    try:
        from shared.database import db_service as db
        reports = await db.get_reports_history(report_type=report_type, limit=limit)
        for r in reports:
            for key in ("top_violators", "by_country", "by_action", "by_asn_type"):
                if r.get(key) and isinstance(r[key], str):
                    try:
                        r[key] = json.loads(r[key])
                    except (json.JSONDecodeError, TypeError):
                        pass
            for key in ("period_start", "period_end", "generated_at", "sent_at"):
                if r.get(key):
                    r[key] = str(r[key])
        return {"items": reports, "total": len(reports)}
    except Exception as e:
        logger.error("Failed to list reports: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{report_id}")
async def get_report(
    report_id: int,
    admin: AdminUser = Depends(require_permission("reports", "view")),
):
    """Get a single report by ID."""
    try:
        from shared.database import db_service as db
        reports = await db.get_reports_history(limit=200)
        report = next((r for r in reports if r.get("id") == report_id), None)
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        for key in ("top_violators", "by_country", "by_action", "by_asn_type"):
            if report.get(key) and isinstance(report[key], str):
                try:
                    report[key] = json.loads(report[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        for key in ("period_start", "period_end", "generated_at", "sent_at"):
            if report.get(key):
                report[key] = str(report[key])
        return report
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get report: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
async def generate_report(
    data: GenerateReportRequest,
    admin: AdminUser = Depends(require_permission("reports", "create")),
):
    """Generate a new violation report."""
    try:
        from shared.database import db_service as db
        from src.services.violation_reports import ViolationReportService, ReportType

        report_type_map = {
            "daily": ReportType.DAILY,
            "weekly": ReportType.WEEKLY,
            "monthly": ReportType.MONTHLY,
        }
        rt = report_type_map.get(data.report_type)
        if not rt:
            raise HTTPException(status_code=400, detail=f"Invalid report type: {data.report_type}")

        service = ViolationReportService(db)

        if data.start_date and data.end_date:
            from datetime import datetime
            start = datetime.fromisoformat(data.start_date)
            end = datetime.fromisoformat(data.end_date)
            report_data = await service.get_custom_report(start, end)
        else:
            report_data = await service.generate_report(rt, save_to_db=True)

        return {
            "report_type": report_data.report_type.value,
            "period_start": str(report_data.period_start),
            "period_end": str(report_data.period_end),
            "total_violations": report_data.total_violations,
            "critical_count": report_data.critical_count,
            "warning_count": report_data.warning_count,
            "monitor_count": report_data.monitor_count,
            "unique_users": report_data.unique_users,
            "avg_score": report_data.avg_score,
            "max_score": report_data.max_score,
            "trend_percent": report_data.trend_percent,
            "trend_direction": report_data.trend_direction,
            "top_violators": report_data.top_violators,
            "by_country": report_data.by_country,
            "by_action": report_data.by_action,
            "by_asn_type": report_data.by_asn_type,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate report: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
