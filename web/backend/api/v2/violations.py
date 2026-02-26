"""Violations API endpoints."""
import csv
import io
import json
import logging
from fastapi import APIRouter, Depends, Path, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from typing import Optional
from datetime import datetime, timedelta

from web.backend.api.deps import get_current_admin, get_db, AdminUser, require_permission, get_client_ip
from web.backend.core.errors import api_error, E
from web.backend.core.rbac import write_audit_log
from web.backend.core.rate_limit import limiter, RATE_READ, RATE_EXPORT, RATE_MUTATIONS
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
    WhitelistAddRequest,
    WhitelistUpdateRequest,
    WhitelistItem,
    WhitelistListResponse,
)
from shared.database import DatabaseService
from shared.geoip import get_geoip_service

logger = logging.getLogger(__name__)
router = APIRouter()


get_severity = ViolationListItem.get_severity


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

        # Override start/end from date_from/date_to if provided
        if date_from:
            try:
                start_date = datetime.fromisoformat(date_from)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date_from format. Use ISO format (e.g. 2024-01-15T00:00:00)",
                )
        if date_to:
            try:
                end_date = datetime.fromisoformat(date_to)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid date_to format. Use ISO format (e.g. 2024-01-15T23:59:59)",
                )

        filter_kwargs = dict(
            start_date=start_date,
            end_date=end_date,
            min_score=min_score,
            user_uuid=user_uuid,
            severity=severity,
            resolved=resolved,
            ip=ip,
            country=country,
        )

        # Подсчёт для пагинации
        # KNOWN LIMITATION: count и data — два отдельных запроса без общей транзакции.
        # При concurrent INSERT/DELETE возможен race condition: total=0 но items не пустой
        # (или наоборот). Для admin-панели это приемлемо.
        total = await db.count_violations_for_period(**filter_kwargs)

        # Получаем страницу данных
        violations = await db.get_violations_for_period(
            **filter_kwargs,
            limit=per_page,
            offset=(page - 1) * per_page,
        )

        # Преобразуем в модели
        items = []
        for v in violations:
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
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error listing violations: %s", e, exc_info=True)
        raise api_error(500, E.INTERNAL_ERROR)


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

        total = stats.get('total', 0)
        critical = stats.get('critical', 0)
        high = stats.get('high', 0)
        medium = stats.get('medium', 0)
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
        raise api_error(500, E.INTERNAL_ERROR)


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
@limiter.limit(RATE_READ)
async def lookup_ips(
    request: Request,
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


# ── Whitelist ─────────────────────────────────────────────────

@router.get("/whitelist", response_model=WhitelistListResponse)
async def get_whitelist(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Список пользователей в whitelist нарушений."""
    items_raw = await db.get_violation_whitelist(limit=limit, offset=offset)
    total = await db.get_violation_whitelist_count()

    items = []
    for row in items_raw:
        excluded = row.get('excluded_analyzers')
        items.append(WhitelistItem(
            id=row['id'],
            user_uuid=str(row['user_uuid']),
            username=row.get('username'),
            email=row.get('email'),
            reason=row.get('reason'),
            added_by_username=row.get('added_by_username'),
            added_at=row.get('added_at') or datetime.utcnow(),
            expires_at=row.get('expires_at'),
            excluded_analyzers=list(excluded) if excluded else None,
        ))

    return WhitelistListResponse(items=items, total=total)


@router.post("/whitelist")
async def add_to_whitelist(
    data: WhitelistAddRequest,
    request: Request,
    admin: AdminUser = Depends(require_permission("violations", "resolve")),
    db: DatabaseService = Depends(get_db),
):
    """Добавить пользователя в whitelist нарушений."""
    expires_at = None
    if data.expires_in_days is not None:
        expires_at = datetime.utcnow() + timedelta(days=data.expires_in_days)

    success, error = await db.add_to_violation_whitelist(
        user_uuid=data.user_uuid,
        reason=data.reason,
        admin_id=admin.account_id,
        admin_username=admin.username,
        expires_at=expires_at,
        excluded_analyzers=data.excluded_analyzers,
    )

    if not success:
        raise api_error(500, E.WHITELIST_ADD_FAILED, error)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="violation.whitelist.add",
        resource="violations",
        resource_id=data.user_uuid,
        details=json.dumps({
            "reason": data.reason,
            "expires_in_days": data.expires_in_days,
            "excluded_analyzers": data.excluded_analyzers,
        }),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "user_uuid": data.user_uuid}


@router.patch("/whitelist/{user_uuid}")
async def update_whitelist_entry(
    data: WhitelistUpdateRequest,
    request: Request,
    user_uuid: str = Path(..., pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    admin: AdminUser = Depends(require_permission("violations", "resolve")),
    db: DatabaseService = Depends(get_db),
):
    """Обновить настройки whitelist для пользователя (исключения анализаторов)."""
    success = await db.update_violation_whitelist_exclusions(
        user_uuid=user_uuid,
        excluded_analyzers=data.excluded_analyzers,
    )

    if not success:
        raise api_error(404, E.WHITELIST_USER_NOT_FOUND)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="violation.whitelist.update",
        resource="violations",
        resource_id=user_uuid,
        details=json.dumps({
            "excluded_analyzers": data.excluded_analyzers,
        }),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "user_uuid": user_uuid, "excluded_analyzers": data.excluded_analyzers}


@router.delete("/whitelist/{user_uuid}")
async def remove_from_whitelist(
    request: Request,
    user_uuid: str = Path(..., pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    admin: AdminUser = Depends(require_permission("violations", "resolve")),
    db: DatabaseService = Depends(get_db),
):
    """Убрать пользователя из whitelist нарушений."""
    success = await db.remove_from_violation_whitelist(user_uuid)

    if not success:
        raise api_error(404, E.WHITELIST_USER_NOT_FOUND)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="violation.whitelist.remove",
        resource="violations",
        resource_id=user_uuid,
        details=json.dumps({"action": "removed_from_whitelist"}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "user_uuid": user_uuid}


@router.post("/user/{user_uuid}/annul-all")
async def annul_user_violations(
    request: Request,
    user_uuid: str = Path(..., pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
    admin: AdminUser = Depends(require_permission("violations", "resolve")),
    db: DatabaseService = Depends(get_db),
):
    """Аннулировать все нерассмотренные нарушения пользователя."""
    count = await db.annul_pending_violations(
        user_uuid=user_uuid,
        admin_telegram_id=admin.telegram_id,
    )

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="violation.annul_bulk",
        resource="violations",
        resource_id=user_uuid,
        details=json.dumps({"action": "annulled", "count": count}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "action": "annulled", "count": count}


@router.get("/user/{user_uuid}")
async def get_user_violations(
    user_uuid: str = Path(..., pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'),
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


@router.get("/export/csv")
@limiter.limit(RATE_EXPORT)
async def export_violations_csv(
    request: Request,
    days: int = Query(7, ge=1, le=365),
    min_score: float = Query(0, ge=0, le=100),
    severity: Optional[str] = None,
    user_uuid: Optional[str] = None,
    resolved: Optional[bool] = None,
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Экспорт нарушений в CSV с proper escaping."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    violations = await db.get_violations_for_period(
        start_date=start_date,
        end_date=end_date,
        min_score=min_score,
        severity=severity,
        user_uuid=user_uuid,
        resolved=resolved,
        limit=10000,
    )

    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    writer.writerow(["Date", "User", "Email", "Score", "Action", "IPs", "Countries", "Reasons", "Status"])
    for v in violations:
        writer.writerow([
            str(v.get('detected_at', '')),
            v.get('username', ''),
            v.get('email', ''),
            v.get('score', 0),
            v.get('recommended_action', ''),
            '; '.join(v.get('ip_addresses') or []),
            '; '.join(v.get('countries') or []),
            '; '.join(v.get('reasons') or []),
            v.get('action_taken', 'pending'),
        ])

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=violations_{days}d.csv"},
    )


@router.get("/{violation_id}", response_model=ViolationDetail)
async def get_violation(
    violation_id: int,
    admin: AdminUser = Depends(require_permission("violations", "view")),
    db: DatabaseService = Depends(get_db),
):
    """Детальная информация о нарушении."""
    violation = await db.get_violation_by_id(violation_id)

    if not violation:
        raise api_error(404, E.VIOLATION_NOT_FOUND)

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
        temporal_score=violation.get('temporal_score') or 0,
        geo_score=violation.get('geo_score') or 0,
        asn_score=violation.get('asn_score') or 0,
        profile_score=violation.get('profile_score') or 0,
        device_score=violation.get('device_score') or 0,
        hwid_score=violation.get('hwid_score') or 0,
        reasons=violation.get('reasons') or [],
        countries=violation.get('countries') or [],
        asn_types=violation.get('asn_types') or [],
        ips=violation.get('ip_addresses') or violation.get('ips') or [],
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
    action_value = data.action.value if hasattr(data.action, 'value') else str(data.action)

    success = await db.update_violation_action(
        violation_id=violation_id,
        action_taken=action_value,
        admin_telegram_id=admin.telegram_id,
    )

    if not success:
        raise api_error(409, E.VIOLATION_UPDATE_FAILED)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="violation.resolve",
        resource="violations",
        resource_id=str(violation_id),
        details=json.dumps({"action": action_value, "comment": data.comment}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "action": action_value}


@router.post("/{violation_id}/annul")
async def annul_violation(
    violation_id: int,
    request: Request,
    admin: AdminUser = Depends(require_permission("violations", "resolve")),
    db: DatabaseService = Depends(get_db),
):
    """Аннулировать нарушение (ложное срабатывание)."""
    success = await db.update_violation_action(
        violation_id=violation_id,
        action_taken="annulled",
        admin_telegram_id=admin.telegram_id,
    )

    if not success:
        raise api_error(404, E.VIOLATION_UPDATE_FAILED)

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="violation.annul",
        resource="violations",
        resource_id=str(violation_id),
        details=json.dumps({"action": "annulled"}),
        ip_address=get_client_ip(request),
    )

    return {"status": "ok", "action": "annulled"}
