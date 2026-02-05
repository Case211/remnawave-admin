"""Violations API endpoints."""
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from datetime import datetime, timedelta

from web.backend.api.deps import get_current_admin, get_db, AdminUser
from web.backend.schemas.violation import (
    ViolationListItem,
    ViolationListResponse,
    ViolationDetail,
    ViolationStats,
    ViolationUserSummary,
    ResolveViolationRequest,
    ViolationSeverity,
)
from src.services.database import DatabaseService

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


@router.get("/", response_model=ViolationListResponse)
async def list_violations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    days: int = Query(7, ge=1, le=90),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    severity: Optional[str] = None,
    user_uuid: Optional[str] = None,
    resolved: Optional[bool] = None,
    admin: AdminUser = Depends(get_current_admin),
    db: DatabaseService = Depends(get_db),
):
    """
    Список нарушений с пагинацией и фильтрами.

    - **days**: Период в днях (по умолчанию 7)
    - **min_score**: Минимальный скор
    - **severity**: Фильтр по серьёзности (low, medium, high, critical)
    - **user_uuid**: Фильтр по пользователю
    - **resolved**: Фильтр по статусу разрешения
    """
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
        violations = [v for v in violations if v.get('user_uuid') == user_uuid]

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
        items.append(ViolationListItem(
            id=v.get('id'),
            user_uuid=v.get('user_uuid'),
            username=v.get('username'),
            email=v.get('email'),
            telegram_id=v.get('telegram_id'),
            score=v.get('score', 0),
            recommended_action=v.get('recommended_action', 'no_action'),
            confidence=v.get('confidence', 0),
            detected_at=v.get('detected_at'),
            severity=get_severity(v.get('score', 0)),
            action_taken=v.get('action_taken'),
            notified=v.get('notified_at') is not None,
        ))

    return ViolationListResponse(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=(total + per_page - 1) // per_page if total > 0 else 1,
    )


@router.get("/stats", response_model=ViolationStats)
async def get_violation_stats(
    days: int = Query(7, ge=1, le=90),
    min_score: float = Query(0.0, ge=0.0, le=100.0),
    admin: AdminUser = Depends(get_current_admin),
    db: DatabaseService = Depends(get_db),
):
    """Статистика нарушений за период."""
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

    return ViolationStats(
        total=stats.get('total', 0),
        critical=stats.get('critical', 0),
        high=stats.get('high', 0),
        medium=stats.get('medium', 0),
        low=stats.get('low', 0),
        unique_users=stats.get('unique_users', 0),
        avg_score=stats.get('avg_score', 0),
        max_score=stats.get('max_score', 0),
        by_action=by_action,
        by_country=by_country,
    )


@router.get("/pending", response_model=ViolationListResponse)
async def get_pending_violations(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    min_score: float = Query(40.0, ge=0.0, le=100.0),
    admin: AdminUser = Depends(get_current_admin),
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
    admin: AdminUser = Depends(get_current_admin),
    db: DatabaseService = Depends(get_db),
):
    """Топ нарушителей за период."""
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    violators = await db.get_top_violators(
        start_date=start_date,
        end_date=end_date,
        min_score=min_score,
        limit=limit,
    )

    return [
        ViolationUserSummary(
            user_uuid=v.get('user_uuid'),
            username=v.get('username'),
            violations_count=v.get('violations_count', 0),
            max_score=v.get('max_score', 0),
            avg_score=v.get('avg_score', 0),
            last_violation_at=v.get('last_violation_at'),
            actions=v.get('actions', []),
        )
        for v in violators
    ]


@router.get("/{violation_id}", response_model=ViolationDetail)
async def get_violation(
    violation_id: int,
    admin: AdminUser = Depends(get_current_admin),
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
        if v.get('id') == violation_id:
            violation = v
            break

    if not violation:
        raise HTTPException(status_code=404, detail="Violation not found")

    return ViolationDetail(
        id=violation.get('id'),
        user_uuid=violation.get('user_uuid'),
        username=violation.get('username'),
        email=violation.get('email'),
        telegram_id=violation.get('telegram_id'),
        score=violation.get('score', 0),
        recommended_action=violation.get('recommended_action', 'no_action'),
        confidence=violation.get('confidence', 0),
        detected_at=violation.get('detected_at'),
        temporal_score=violation.get('temporal_score', 0),
        geo_score=violation.get('geo_score', 0),
        asn_score=violation.get('asn_score', 0),
        profile_score=violation.get('profile_score', 0),
        device_score=violation.get('device_score', 0),
        reasons=violation.get('reasons', []),
        countries=violation.get('countries', []),
        asn_types=violation.get('asn_types', []),
        ips=violation.get('ips', []),
        action_taken=violation.get('action_taken'),
        action_taken_at=violation.get('action_taken_at'),
        action_taken_by=violation.get('action_taken_by'),
        notified_at=violation.get('notified_at'),
        raw_data=violation.get('raw_data'),
    )


@router.post("/{violation_id}/resolve")
async def resolve_violation(
    violation_id: int,
    data: ResolveViolationRequest,
    admin: AdminUser = Depends(get_current_admin),
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

    return {"status": "ok", "action": data.action}


@router.get("/user/{user_uuid}")
async def get_user_violations(
    user_uuid: str,
    days: int = Query(30, ge=1, le=365),
    admin: AdminUser = Depends(get_current_admin),
    db: DatabaseService = Depends(get_db),
):
    """Нарушения конкретного пользователя."""
    violations = await db.get_user_violations(
        user_uuid=user_uuid,
        days=days,
    )

    items = []
    for v in violations:
        items.append(ViolationListItem(
            id=v.get('id'),
            user_uuid=v.get('user_uuid'),
            username=v.get('username'),
            email=v.get('email'),
            telegram_id=v.get('telegram_id'),
            score=v.get('score', 0),
            recommended_action=v.get('recommended_action', 'no_action'),
            confidence=v.get('confidence', 0),
            detected_at=v.get('detected_at'),
            severity=get_severity(v.get('score', 0)),
            action_taken=v.get('action_taken'),
            notified=v.get('notified_at') is not None,
        ))

    return items
