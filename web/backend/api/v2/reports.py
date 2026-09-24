"""Violation reports management — local database."""
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from shared import timefmt
from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import api_error, E

logger = logging.getLogger(__name__)
router = APIRouter()

_JSON_FIELDS = ("top_violators", "by_country", "by_action", "by_asn_type")
_DATE_FIELDS = ("period_start", "period_end", "generated_at", "sent_at")


class GenerateReportRequest(BaseModel):
    report_type: str  # daily, weekly, monthly
    # Свой период: даты «с» и «по» (включительно), сутки — по часам панели.
    # Такой отчёт не сохраняется: у него нет места в расписании.
    start_date: Optional[str] = None
    end_date: Optional[str] = None


async def _visible(admin) -> Optional[set]:
    from web.backend.core.rbac import get_visible_user_uuids
    return await get_visible_user_uuids(admin)


def _serialize(report: Dict[str, Any], visible: Optional[set]) -> Dict[str, Any]:
    """JSON-поля — объектами, даты — ISO с поясом. Ограниченному админу —
    только его юзеры в топе; общие цифры отчёта считаются по всем."""
    out = dict(report)
    for key in _JSON_FIELDS:
        if isinstance(out.get(key), str):
            try:
                out[key] = json.loads(out[key])
            except (json.JSONDecodeError, TypeError):
                out[key] = None
    for key in _DATE_FIELDS:
        value = out.get(key)
        if value is not None and hasattr(value, "isoformat"):
            out[key] = value.isoformat()
    top: List[Dict[str, Any]] = out.get("top_violators") or []
    for v in top:
        # Старые отчёты и фронт знали поле uuid, база отдаёт user_uuid
        if v.get("user_uuid") is not None:
            v["user_uuid"] = str(v["user_uuid"])
    if visible is not None:
        out["top_violators"] = [v for v in top if str(v.get("user_uuid", "")).lower() in visible]
        out["scoped"] = True
    return out


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
        visible = await _visible(admin)
        items = [_serialize(r, visible) for r in reports]
        return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error("Failed to list reports: %s", e)
        raise api_error(500, E.INTERNAL_ERROR, "Failed to list reports")


async def _get_or_404(report_id: int) -> Dict[str, Any]:
    from shared.database import db_service as db
    report = await db.get_report_by_id(report_id)
    if not report:
        raise api_error(404, E.REPORT_NOT_FOUND)
    return report


@router.get("/{report_id}")
async def get_report(
    report_id: int,
    admin: AdminUser = Depends(require_permission("reports", "view")),
):
    """Get a single report by ID."""
    return _serialize(await _get_or_404(report_id), await _visible(admin))


@router.post("/generate")
async def generate_report(
    data: GenerateReportRequest,
    admin: AdminUser = Depends(require_permission("reports", "create")),
):
    """Сгенерировать отчёт. Отчёт за уже существующий период перезаписывается."""
    from shared.violation_reports import ViolationReportService, ReportType

    report_type_map = {
        "daily": ReportType.DAILY,
        "weekly": ReportType.WEEKLY,
        "monthly": ReportType.MONTHLY,
    }
    rt = report_type_map.get(data.report_type)
    if not rt:
        raise api_error(400, E.INVALID_INPUT, f"Invalid report type: {data.report_type}")

    service = ViolationReportService()
    # Мин. скор и размер топа — те же, что у отчётов по расписанию
    service.configure_from_settings()
    try:
        if data.start_date and data.end_date:
            start = timefmt.parse_filter(data.start_date)
            end = timefmt.parse_filter(data.end_date, end=True)
            if start is None or end is None or start >= end:
                raise ValueError("empty period")
            report_data = await service.get_custom_report(start, end)
        else:
            report_data = await service.generate_report(rt, save_to_db=True)
    except ValueError:
        raise api_error(400, E.INVALID_INPUT, "Invalid period")
    except Exception as e:
        logger.error("Failed to generate report: %s", e, exc_info=True)
        raise api_error(500, E.INTERNAL_ERROR, "Failed to generate report")

    return {
        "id": report_data.id,
        "report_type": report_data.report_type.value,
        "period_start": report_data.period_start.isoformat(),
        "period_end": report_data.period_end.isoformat(),
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


@router.post("/{report_id}/send")
async def send_report(
    report_id: int,
    admin: AdminUser = Depends(require_permission("reports", "create")),
):
    """Отправить готовый отчёт в Telegram — туда же, куда шлёт расписание."""
    report = await _get_or_404(report_id)
    if not report.get("message_text"):
        raise api_error(400, E.INVALID_INPUT, "Report has no text")

    from shared import tg_rich
    from shared.config_service import config_service
    from shared.database import db_service as db
    from web.backend.core.notification_service import _get_global_telegram_config

    bot_token, chat_id, violations_topic = _get_global_telegram_config("violations")
    if not bot_token or not chat_id:
        raise api_error(400, E.TELEGRAM_NOT_CONFIGURED)
    topic_id = config_service.get("reports_topic_id", None) or violations_topic
    try:
        await tg_rich.send_rich_or_html(
            bot_token, chat_id, report["message_text"],
            message_thread_id=int(topic_id) if topic_id else None,
        )
    except Exception as e:
        logger.error("Failed to send report %s to Telegram: %s", report_id, e)
        raise api_error(502, E.INTERNAL_ERROR, "Telegram did not accept the report")
    await db.mark_report_sent(report_id)
    return {"ok": True}


@router.delete("/{report_id}")
async def delete_report(
    report_id: int,
    admin: AdminUser = Depends(require_permission("reports", "delete")),
):
    """Удалить отчёт."""
    from shared.database import db_service as db
    if not await db.delete_report(report_id):
        raise api_error(404, E.REPORT_NOT_FOUND)
    return {"ok": True}
