"""Mobile device registration for FCM push notifications.

`POST /api/v2/me/devices` — мобильник регистрирует свой FCM-токен после логина.
`DELETE /api/v2/me/devices/{token}` — снимаем перед logout, чтобы освободить
    запись (FCM-токен один и тот же между сессиями, но при logout мы не хотим
    продолжать слать пуши на залогиненный из чужого аккаунта телефон).
`GET /api/v2/me/devices` — список устройств текущего админа (для UI).
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException

from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, get_current_admin

router = APIRouter()
logger = logging.getLogger(__name__)


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(..., min_length=10, max_length=4096)
    platform: str = Field(default="android", pattern=r"^(android|ios)$")
    app_version: Optional[str] = Field(default=None, max_length=32)
    device_label: Optional[str] = Field(default=None, max_length=128)


class DeviceItem(BaseModel):
    id: int
    platform: str
    app_version: Optional[str] = None
    device_label: Optional[str] = None
    created_at: datetime
    last_seen_at: datetime


async def _resolve_admin_id(admin: AdminUser) -> int:
    """Возвращает admin_accounts.id; для legacy админов авто-создаём строку
    тем же путём, что и notifications._require_account_id."""
    from web.backend.api.v2.notifications import _require_account_id
    return await _require_account_id(admin)


@router.post("/me/devices", response_model=DeviceItem)
async def register_device(
    payload: DeviceRegisterRequest,
    admin: AdminUser = Depends(get_current_admin),
) -> DeviceItem:
    """Регистрирует FCM-токен. При повторной регистрации того же токена
    обновляет привязку к текущему админу (например, переустановили приложение
    или выполнен relogin под другим юзером)."""
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
            RETURNING id, platform, app_version, device_label, created_at, last_seen_at
            """,
            admin_id,
            payload.fcm_token,
            payload.platform,
            payload.app_version,
            payload.device_label,
        )
    return DeviceItem(**dict(row))


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
            "SELECT id, platform, app_version, device_label, created_at, last_seen_at "
            "FROM admin_devices WHERE admin_id = $1 ORDER BY last_seen_at DESC",
            admin_id,
        )
    return [DeviceItem(**dict(r)) for r in rows]


@router.post("/me/devices/test")
async def send_test_push(
    admin: AdminUser = Depends(get_current_admin),
):
    """Кнопка «отправить тестовый пуш мне»: проверка, что Firebase настроен и
    у устройства есть валидный токен. Шлёт на все девайсы текущего админа."""
    from web.backend.core.push_service import is_enabled, send_to_admin
    if not is_enabled():
        raise HTTPException(
            status_code=503,
            detail="FCM disabled (set FCM_ENABLED=true and FCM_CREDENTIALS_PATH on server)",
        )
    admin_id = await _resolve_admin_id(admin)
    result = await send_to_admin(
        admin_id=admin_id,
        title="Remnawave Admin",
        body="Тестовый пуш — всё работает",
        data={"type": "info", "severity": "info"},
    )
    return {"success": result.get("sent", 0) > 0, **result}


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
