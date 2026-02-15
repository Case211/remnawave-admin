"""Violations API endpoints."""
import json
import logging
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from typing import Optional
from datetime import datetime, timedelta

from web.backend.api.deps import get_current_admin, get_db, AdminUser, require_permission, get_client_ip
from web.backend.core.rbac import write_audit_log
from web.backend.schemas.violation import (
    ViolationListItem,
    ViolationListResponse,
    ViolationDetail,
    ViolationStats,
    ViolationUserSummary,
    ResolveViolationRequest,
    ViolationSeverity,
    IPLookupRequest,
    IPLookupResponse,
    IPInfo,
)
from src.services.database import DatabaseService
from src.services.geoip import get_geoip_service

logger = logging.getLogger(__name__)
router = APIRouter()


def get_severity(score: float) -> ViolationSeverity:
    """Определить серьёзность по скору."""
    if score >= 80:
        return ViolationSeverity.CRITICAL
    elif score >= 60:
        return ViolationSeverity.HIGH
    elif score >= 40:
        return ViolationSeverity.MEDIUM
    return ViolationSeverity.LOW


def _row_to_list_item(v: dict) -> ViolationListItem:
    """Convert a DB row dict to ViolationListItem (handles UUID→str, None defaults)."""
    score = float(v.get('score', 0) or 0)
    return ViolationListItem(
        id=int(v.get('id', 0)),
        user_uuid=str(v.get('user_uuid', '')),
        username=v.get('username'),
        email=v.get('email'),
        telegram_id=v.get('telegram_id'),
        score=score,
        recommended_action=v.get('recommended_action') or 'no_action',
        confidence=float(v.get('confidence', 0) or 0),
        detected_at=v.get('detected_at') or datetime.utcnow(),
        severity=get_severity(score),
        action_taken=v.get('action_taken'),
        notified=v.get('notified_at') is not None,
    )


@router.get("", response_model=ViolationListResponse)
async def list_violations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    days: int = Query(7, ge=1, le=90),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    severity: Optional[str] = None,
    user_uuid: Optional[str] = None,
    resolved: Optional[bool] = None,
    ip: Optional[str] = Query(None, description="Filter by IP address"),
    country: Optional[str] = Query(None, description="Filter by country code"),
    date_from: Optional[str] = Query(None, description="Filter from date (ISO format)"),
    date_to: Optional[str] = Query(None, description="Filter to date (ISO format)"),
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """
    Список нарушений с пагинацией и фильтрами.

    - **days**: Период в днях (по умолчанию 7)
    - **min_score**: Минимальный скор
    - **severity**: Фильтр по серьёзности (low, medium, high, critical)
    - **user_uuid**: Фильтр по пользователю
    - **resolved**: Фильтр по статусу разрешения
    - **ip**: Фильтр по IP адресу
    - **country**: Фильтр по коду страны
    - **date_from**: Фильтр от даты (ISO формат)
    - **date_to**: Фильтр до даты (ISO формат)
    """
    try:
        if not db.is_connected:
            return ViolationListResponse(items=[], total=0, page=page, per_page=per_page, pages=1)

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Получаем нарушения из БД
        violations = await db.get_violations_for_period(
            start_date=start_date,
            end_date=end_date,
            min_score=min_score,
        )

        # Фильтрация
        if user_uuid:
            violations = [v for v in violations if str(v.get('user_uuid', '')) == user_uuid]

        if severity:
            severity_map = {
                'low': (0, 40),
                'medium': (40, 60),
                'high': (60, 80),
                'critical': (80, 101),
            }
            if severity in severity_map:
                min_s, max_s = severity_map[severity]
                violations = [v for v in violations if min_s <= v.get('score', 0) < max_s]

        if resolved is not None:
            if resolved:
                violations = [v for v in violations if v.get('action_taken')]
            else:
                violations = [v for v in violations if not v.get('action_taken')]

        if ip:
            violations = [
                v for v in violations
                if ip in (v.get('ip_addresses') or v.get('ips') or [])
            ]

        if country:
            country_upper = country.upper()
            violations = [
                v for v in violations
                if country_upper in [c.upper() for c in (v.get('countries') or [])]
            ]

        if date_from:
            try:
                dt_from = datetime.fromisoformat(date_from)
                violations = [
                    v for v in violations
                    if (v.get('detected_at') or datetime.min) >= dt_from
                ]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date_from format. Use ISO format (e.g. 2024-01-15T00:00:00)",
                )

        if date_to:
            try:
                dt_to = datetime.fromisoformat(date_to)
                violations = [
                    v for v in violations
                    if (v.get('detected_at') or datetime.max) <= dt_to
                ]
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date_to format. Use ISO format (e.g. 2024-01-15T23:59:59)",
                )

        # Сортировка по дате (новые первыми)
        violations.sort(key=lambda x: x.get('detected_at', datetime.min), reverse=True)

        # Пагинация
        total = len(violations)
        start = (page - 1) * per_page
        end = start + per_page
        items_raw = violations[start:end]

        # Преобразуем в модели
        items = []
        for v in items_raw:
            try:
                items.append(_row_to_list_item(v))
            except Exception as item_err:
                logger.warning("Skipping violation row id=%s: %s", v.get('id'), item_err)

        return ViolationListResponse(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page if total > 0 else 1,
        )
    except Exception as e:
        logger.error("Error listing violations: %s", e, exc_info=True)
        return ViolationListResponse(items=[], total=0, page=page, per_page=per_page, pages=1)


@router.get("/stats", response_model=ViolationStats)
async def get_violation_stats(
    days: int = Query(7, ge=1, le=90),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Статистика нарушений за период."""
    try:
        if not db.is_connected:
            return ViolationStats(
                total=0, critical=0, high=0, medium=0, low=0,
                unique_users=0, avg_score=0.0, max_score=0.0,
            )

        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days)

        # Базовая статистика
        stats = await db.get_violations_stats_for_period(
            start_date=start_date,
            end_date=end_date,
            min_score=min_score,
        )

        # По странам
        by_country = await db.get_violations_by_country(
            start_date=start_date,
            end_date=end_date,
            min_score=min_score,
        )

        # По действиям
        by_action = await db.get_violations_by_action(
            start_date=start_date,
            end_date=end_date,
            min_score=min_score,
        )

        # DB returns 'warning'/'monitor' but schema expects 'high'/'medium'/'low'
        total = stats.get('total', 0)
        critical = stats.get('critical', 0)
        high = stats.get('warning', stats.get('high', 0))
        medium = stats.get('monitor', stats.get('medium', 0))
        low = max(0, total - critical - high - medium)

        return ViolationStats(
            total=total,
            critical=critical,
            high=high,
            medium=medium,
            low=low,
            unique_users=stats.get('unique_users', 0),
            avg_score=float(stats.get('avg_score', 0)),
            max_score=float(stats.get('max_score', 0)),
            by_action=by_action,
            by_country=by_country,
        )
    except Exception as e:
        logger.error("Error getting violation stats: %s", e, exc_info=True)
        return ViolationStats(
            total=0, critical=0, high=0, medium=0, low=0,
            unique_users=0, avg_score=0.0, max_score=0.0,
        )


@router.get("/pending", response_model=ViolationListResponse)
async def get_pending_violations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    min_score: float = Query(40.0, ge=0.0, le=100.0),
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Нерассмотренные нарушения (требующие действий)."""
    return await list_violations(
        page=page,
        per_page=per_page,
        days=30,
        min_score=min_score,
        resolved=False,
        admin=admin,
        db=db,
    )


@router.get("/top-violators")
async def get_top_violators(
    days: int = Query(7, ge=1, le=90),
    limit: int = Query(10, ge=1, le=50),
    min_score: float = Query(40.0, ge=0.0, le=100.0),
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Топ нарушителей за период."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    violators = await db.get_top_violators_for_period(
        start_date=start_date,
        end_date=end_date,
        min_score=min_score,
        limit=limit,
    )

    items = []
    for v in violators:
        try:
            items.append(ViolationUserSummary(
                user_uuid=str(v.get('user_uuid', '')),
                username=v.get('username'),
                violations_count=v.get('violations_count', 0),
                max_score=float(v.get('max_score', 0) or 0),
                avg_score=float(v.get('avg_score', 0) or 0),
                last_violation_at=v.get('last_violation_at') or datetime.utcnow(),
                actions=v.get('actions') or [],
            ))
        except Exception as e:
            logger.warning("Skipping top violator row: %s", e)
    return items


@router.post("/ip-lookup", response_model=IPLookupResponse)
async def lookup_ips(
    data: IPLookupRequest,
    admin: AdminUser = Depends(require_permission("violations", "view")),
):
    """Получить информацию о провайдерах по списку IP адресов."""
    if not data.ips:
        return IPLookupResponse(results={})

    # Ограничиваем количество IP за один запрос
    ips = data.ips[:50]

    try:
        geoip = get_geoip_service()
        metadata_map = await geoip.lookup_batch(ips)

        results = {}
        for ip, meta in metadata_map.items():
            results[ip] = IPInfo(
                ip=ip,
                asn_org=meta.asn_org or None,
                country=meta.country_name or meta.country_code or None,
                city=meta.city or None,
                connection_type=meta.connection_type or None,
                is_vpn=meta.is_vpn,
                is_proxy=meta.is_proxy,
                is_hosting=meta.is_hosting,
                is_mobile=meta.is_mobile,
            )

        return IPLookupResponse(results=results)
    except Exception as e:
        logger.error("Error during IP lookup: %s", e, exc_info=True)
        return IPLookupResponse(results={})


@router.get("/{violation_id}", response_model=ViolationDetail)
async def get_violation(
    violation_id: int,
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Детальная информация о нарушении."""
    # Получаем нарушение по ID
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=90)

    violations = await db.get_violations_for_period(
        start_date=start_date,
        end_date=end_date,
        min_score=0,
    )

    violation = None
    for v in violations:
        if int(v.get('id', 0)) == violation_id:
            violation = v
            break

    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")

    return ViolationDetail(
        id=int(violation.get('id', 0)),
        user_uuid=str(violation.get('user_uuid', '')),
        username=violation.get('username'),
        email=violation.get('email'),
        telegram_id=violation.get('telegram_id'),
        score=float(violation.get('score', 0) or 0),
        recommended_action=violation.get('recommended_action') or 'no_action',
        confidence=float(violation.get('confidence', 0) or 0),
        detected_at=violation.get('detected_at') or datetime.utcnow(),
        temporal_score=violation.get('temporal_score', 0),
        geo_score=violation.get('geo_score', 0),
        asn_score=violation.get('asn_score', 0),
        profile_score=violation.get('profile_score', 0),
        device_score=violation.get('device_score', 0),
        reasons=violation.get('reasons', []),
        countries=violation.get('countries', []),
        asn_types=violation.get('asn_types', []),
        ips=violation.get('ip_addresses', violation.get('ips', [])),
        action_taken=violation.get('action_taken'),
        action_taken_at=violation.get('action_taken_at'),
        action_taken_by=violation.get('action_taken_by'),
        notified_at=violation.get('notified_at'),
        raw_data=violation.get('raw_breakdown') or violation.get('raw_data'),
    )


@router.post("/{violation_id}/resolve")
async def resolve_violation(
    violation_id: int,
    data: ResolveViolationRequest,
    request: Request,
    admin: AdminUser = Depends(require_permission("violations", "resolve")),
    db: DatabaseService = Depends(get_db),
):
    """
    Разрешить нарушение (принять действие).

    Возможные действия:
    - ignore: Игнорировать
    - warn: Предупредить пользователя
    - block: Заблокировать пользователя
    """
    success = await db.update_violation_action(
        violation_id=violation_id,
        action_taken=data.action,
        admin_telegram_id=admin.telegram_id,
    )

    if not success:
        raise HTTPException(status_code=404, detail="Violation not found or update failed")

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="violation.resolve",
        resource="violations",
        resource_id=str(violation_id),
        details=json.dumps({"action": data.action}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "action": data.action}


@router.get("/user/{user_uuid}")
async def get_user_violations(
    user_uuid: str,
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Нарушения конкретного пользователя."""
    violations = await db.get_user_violations(
        user_uuid=user_uuid,
        days=days,
    )

    items = []
    for v in violations:
        try:
            items.append(_row_to_list_item(v))
        except Exception as e:
            logger.warning("Skipping user violation row id=%s: %s", v.get('id'), e)

    return items
