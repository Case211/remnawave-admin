"""Mobile device registration for FCM push notifications.

`POST /api/v2/me/devices` — мобильник регистрирует свой FCM-токен после логина.
`DELETE /api/v2/me/devices/{token}` — снимаем перед logout, чтобы освободить
    запись (FCM-токен один и тот же между сессиями, но при logout мы не хотим
    продолжать слать пуши на залогиненный из чужого аккаунта телефон).
`GET /api/v2/me/devices` — список устройств текущего админа (для UI).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, get_current_admin

router = APIRouter()
logger = logging.getLogger(__name__)

# Канонический список категорий пушей. Если в data['type'] от backend пришёл
# тип, который не в этом списке — он всё равно проходит (мы фильтруем только
# по непустому subscriptions), но в UI настройка показывается только для них.
PUSH_CATEGORIES = {"violations", "alerts", "info"}


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=4096)
    platform: str = Field(default="android", pattern=r"^(android|ios)$")
    app_version: Optional[str] = Field(default=None, max_length=32)
    device_label: Optional[str] = Field(default=None, max_length=128)


class DeviceUpdateRequest(BaseModel):
    notifications_enabled: Optional[bool] = None
    # null/отсутствие = «все категории», пустой список = «ничего не слать»,
    # непустой = «только эти» (фильтр на стороне push_service).
    subscriptions: Optional[List[str]] = None


class DeviceItem(BaseModel):
    id: int
    platform: str
    app_version: Optional[str] = None
    device_label: Optional[str] = None
    notifications_enabled: bool = True
    subscriptions: Optional[List[str]] = None
    created_at: datetime
    last_seen_at: datetime


def _decode_subscriptions(value) -> Optional[List[str]]:
    """asyncpg отдаёт jsonb уже как python-объект, но если это будет str —
    парсим. None → None (значит «все категории»)."""
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return None
    if isinstance(value, list):
        return [str(x) for x in value]
    return None


async def _resolve_admin_id(admin: AdminUser) -> int:
    """Возвращает admin_accounts.id; для legacy админов авто-создаём строку
    тем же путём, что и notifications._require_account_id."""
    from web.backend.api.v2.notifications import _require_account_id
    return await _require_account_id(admin)


def _row_to_device(row) -> DeviceItem:
    d = dict(row)
    d["subscriptions"] = _decode_subscriptions(d.get("subscriptions"))
    return DeviceItem(**d)


@router.post("/me/devices", response_model=DeviceItem)
async def register_device(
    payload: DeviceRegisterRequest,
    admin: AdminUser = Depends(get_current_admin),
) -> DeviceItem:
    """Регистрирует FCM-токен. При повторной регистрации того же токена
    обновляет привязку к текущему админу (например, переустановили приложение
    или выполнен relogin под другим юзером).

    Subscriptions/notifications_enabled НЕ сбрасываются при повторной регистрации —
    юзер мог настроить под себя, не теряем эти настройки."""
    from shared.database import db_service

    admin_id = await _resolve_admin_id(admin)
    if not db_service.is_connected:
        raise HTTPException(status_code=503, detail="DB not connected")

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO admin_devices (admin_id, fcm_token, platform, app_version, device_label)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (fcm_token) DO UPDATE SET
                admin_id = EXCLUDED.admin_id,
                platform = EXCLUDED.platform,
                app_version = EXCLUDED.app_version,
                device_label = COALESCE(EXCLUDED.device_label, admin_devices.device_label),
                last_seen_at = NOW()
            RETURNING id, platform, app_version, device_label,
                      notifications_enabled, subscriptions, created_at, last_seen_at
            """,
            admin_id,
            payload.fcm_token,
            payload.platform,
            payload.app_version,
            payload.device_label,
        )
    return _row_to_device(row)


@router.get("/me/devices", response_model=List[DeviceItem])
async def list_devices(
    admin: AdminUser = Depends(get_current_admin),
) -> List[DeviceItem]:
    from shared.database import db_service
    admin_id = await _resolve_admin_id(admin)
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, platform, app_version, device_label, "
            "notifications_enabled, subscriptions, created_at, last_seen_at "
            "FROM admin_devices WHERE admin_id = $1 ORDER BY last_seen_at DESC",
            admin_id,
        )
    return [_row_to_device(r) for r in rows]


@router.patch("/me/devices/{device_id}", response_model=DeviceItem)
async def update_device(
    device_id: int,
    payload: DeviceUpdateRequest,
    admin: AdminUser = Depends(get_current_admin),
) -> DeviceItem:
    """Обновить настройки конкретного устройства (свич push, выбор категорий).

    Меняем только то, что прислали (None → не трогать). Невалидные категории
    в subscriptions молча отбрасываем, чтобы клиент с устаревшим списком не
    ломал нам payload.
    """
    from shared.database import db_service
    admin_id = await _resolve_admin_id(admin)
    if not db_service.is_connected:
        raise HTTPException(status_code=503, detail="DB not connected")

    subs_json = None
    set_subs = payload.subscriptions is not None
    if set_subs:
        cleaned = [s for s in (payload.subscriptions or []) if s in PUSH_CATEGORIES]
        subs_json = json.dumps(cleaned)

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            """
            UPDATE admin_devices
            SET
                notifications_enabled = COALESCE($3, notifications_enabled),
                subscriptions = CASE WHEN $4 THEN $5::jsonb ELSE subscriptions END,
                last_seen_at = NOW()
            WHERE id = $1 AND admin_id = $2
            RETURNING id, platform, app_version, device_label,
                      notifications_enabled, subscriptions, created_at, last_seen_at
            """,
            device_id,
            admin_id,
            payload.notifications_enabled,
            set_subs,
            subs_json,
        )
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")
    return _row_to_device(row)


@router.post("/me/devices/test")
async def send_test_push(
    admin: AdminUser = Depends(get_current_admin),
):
    """Кнопка «отправить тестовый пуш мне»: проверка, что Firebase настроен и
    у устройства есть валидный токен. Шлёт на все девайсы текущего админа.
    В ответе возвращаем admin_id и сколько устройств зарегистрировано — чтобы
    видеть, если веб и мобильник попали в разные admin_accounts.id."""
    from shared.database import db_service
    from web.backend.core.push_service import is_enabled, send_to_admin
    if not is_enabled():
        raise HTTPException(
            status_code=503,
            detail="FCM disabled (set FCM_ENABLED=true and FCM_CREDENTIALS_PATH on server)",
        )
    admin_id = await _resolve_admin_id(admin)
    devices_count = 0
    if db_service.is_connected:
        async with db_service.acquire() as conn:
            devices_count = await conn.fetchval(
                "SELECT COUNT(*) FROM admin_devices WHERE admin_id = $1", admin_id,
            ) or 0
    result = await send_to_admin(
        admin_id=admin_id,
        title="Remnawave Admin",
        body="Тестовый пуш — всё работает",
        data={"type": "info", "severity": "info"},
    )
    return {
        "success": result.get("sent", 0) > 0,
        "admin_id": admin_id,
        "devices_for_admin": devices_count,
        **result,
    }


@router.delete("/me/devices/{token}")
async def unregister_device(
    token: str,
    admin: AdminUser = Depends(get_current_admin),
):
    """Удаление по полному значению FCM-токена. Снимает только устройства
    текущего админа — кросс-удаление чужих чужими токенами не пускаем."""
    from shared.database import db_service
    admin_id = await _resolve_admin_id(admin)
    if not db_service.is_connected:
        raise HTTPException(status_code=503, detail="DB not connected")
    async with db_service.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM admin_devices WHERE admin_id = $1 AND fcm_token = $2",
            admin_id,
            token,
        )
    # asyncpg возвращает 'DELETE N'
    deleted = int(result.split()[-1]) if result and result.startswith("DELETE") else 0
    return {"success": True, "deleted": deleted}
