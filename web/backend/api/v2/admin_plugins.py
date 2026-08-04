"""Админ-API витрины плагинов (keyless-модель, контракт v1.1).

Все операции — под ``require_superadmin``: установка кода в процесс
панели и покупки — привилегия владельца. Сетевые вызовы уходят на сервер
лицензирования через ``core/entitlements.py``; его ошибки пробрасываются
клиенту структурированно (code + http-статус), фронт показывает их
локализованно.

Рестарт нужен только установке/удалению wheel (pip + entry points не
перечитываются на лету). Покупка, продление, докупка квоты и redeem
применяются живьём ближайшим heartbeat-ом.
"""
from __future__ import annotations

import hashlib
import logging
import os
import signal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, require_superadmin
from web.backend.core import entitlements, plugin_installer
from web.backend.core.entitlements import LicenseServerError
from web.backend.core.plugins import loaded_plugins

logger = logging.getLogger(__name__)
router = APIRouter()


def _raise(e: LicenseServerError) -> None:
    status = e.status if 400 <= e.status < 500 else 502
    raise HTTPException(status_code=status, detail={"code": e.code, "upstream": e.detail})


# ── схемы ────────────────────────────────────────────────────────


class StoreStatus(BaseModel):
    registered: bool
    instance_id: Optional[str] = None
    plugins: Dict[str, Any]
    jwt_exp: Optional[int] = None
    last_sync_ok: Optional[float] = None
    last_error: Optional[str] = None
    messages: List[Dict[str, Any]] = Field(default_factory=list)
    installed: Dict[str, str]  # plugin_id -> версия загруженного кода


class PurchaseItemIn(BaseModel):
    type: str = Field(pattern="^(subscription|topup)$")
    plugin_id: str = Field(max_length=64)
    tariff: Optional[str] = Field(default=None, max_length=32)
    months: int = Field(default=1, ge=1, le=12)
    pack: Optional[str] = Field(default=None, max_length=32)


class PurchaseIn(BaseModel):
    items: List[PurchaseItemIn] = Field(min_length=1, max_length=10)


class RedeemIn(BaseModel):
    code: str = Field(min_length=6, max_length=64)


class SimpleResponse(BaseModel):
    ok: bool
    requires_restart: bool = False
    message: Optional[str] = None


# ── витрина ──────────────────────────────────────────────────────


@router.get("/catalog", summary="Каталог плагинов (прокси сервера с кэшем)")
async def catalog(_admin: AdminUser = Depends(require_superadmin())) -> dict:
    # Каталог публичный — открытие витрины НЕ регистрирует инстанс.
    # Привязка к серверу лицензий — только явно, кнопкой «Подключиться»
    # (приватность: пока не подключился, инстанс серверу не известен).
    try:
        return await entitlements.fetch_catalog()
    except LicenseServerError as e:
        _raise(e)


@router.post("/connect", response_model=SimpleResponse, summary="Подключить инстанс к магазину")
async def connect(_admin: AdminUser = Depends(require_superadmin())) -> SimpleResponse:
    """Явная регистрация инстанса на сервере лицензий + первый heartbeat.
    До этого шага панель не сообщает о себе серверу."""
    try:
        await entitlements.ensure_registered()
        await entitlements.heartbeat_now()
    except LicenseServerError as e:
        _raise(e)
    return SimpleResponse(ok=True, message="Подключено к магазину")


@router.post("/disconnect", response_model=SimpleResponse, summary="Отвязать инстанс от магазина")
async def disconnect(_admin: AdminUser = Depends(require_superadmin())) -> SimpleResponse:
    """Забыть привязку к серверу лицензий (приватность). Купленные
    подписки на сервере сохраняются — повторное «Подключиться» их вернёт."""
    await entitlements.disconnect()
    return SimpleResponse(ok=True, message="Отключено от магазина")


class TrialIn(BaseModel):
    # Дефолт — совместимость со старым фронтом, звавшим триал без тела.
    plugin_id: str = Field(default="smart_support", max_length=64)


@router.post("/trial", response_model=SimpleResponse, summary="Активировать пробный период")
async def start_trial(
    payload: TrialIn = Body(default=TrialIn()),
    _admin: AdminUser = Depends(require_superadmin()),
) -> SimpleResponse:
    """Пробный период плагина (один раз на пару инстанс+плагин). Подключает
    к магазину, если ещё не подключён."""
    try:
        await entitlements.start_trial(payload.plugin_id)
    except LicenseServerError as e:
        _raise(e)
    return SimpleResponse(ok=True, message="Пробный период активирован")


@router.get("/status", response_model=StoreStatus, summary="Состояние связки и подписок")
async def store_status(_admin: AdminUser = Depends(require_superadmin())) -> StoreStatus:
    summary = entitlements.status_summary()
    summary["installed"] = {m.id: m.version for m in loaded_plugins()}
    return StoreStatus(**summary)


@router.post("/sync", response_model=SimpleResponse, summary="Heartbeat немедленно")
async def sync_now(_admin: AdminUser = Depends(require_superadmin())) -> SimpleResponse:
    try:
        await entitlements.ensure_registered()
        await entitlements.heartbeat_now()
        await entitlements.fetch_catalog(force=True)  # подтянуть свежие версии/цены
    except LicenseServerError as e:
        _raise(e)
    return SimpleResponse(ok=True)


# ── покупка ──────────────────────────────────────────────────────


@router.post("/purchase", summary="Создать заказ (подписка или пакет квоты)")
async def purchase(
    payload: PurchaseIn = Body(...),
    _admin: AdminUser = Depends(require_superadmin()),
) -> dict:
    items = [i.model_dump(exclude_none=True) for i in payload.items]
    try:
        order = await entitlements.purchase(items)
    except LicenseServerError as e:
        _raise(e)
    logger.info("admin_plugins.order_created", extra={"order": order.get("order_id")})
    return order


@router.get("/order/{order_id}", summary="Статус заказа (поллинг после «Я оплатил»)")
async def order_status(
    order_id: str, _admin: AdminUser = Depends(require_superadmin())
) -> dict:
    try:
        status = await entitlements.order_status(order_id)
        if status.get("status") == "paid":
            # Оплату подтвердили — подтягиваем entitlements сразу же.
            await entitlements.heartbeat_now()
        return status
    except LicenseServerError as e:
        _raise(e)


@router.post("/redeem", response_model=SimpleResponse, summary="Промо или transfer-код")
async def redeem(
    payload: RedeemIn = Body(...),
    _admin: AdminUser = Depends(require_superadmin()),
) -> SimpleResponse:
    try:
        await entitlements.ensure_registered()
        await entitlements.redeem(payload.code.strip())
    except LicenseServerError as e:
        _raise(e)
    return SimpleResponse(ok=True, message="Код применён")


@router.post("/transfer-out", summary="Код переноса подписок на новый сервер")
async def transfer_out(_admin: AdminUser = Depends(require_superadmin())) -> dict:
    try:
        return await entitlements.transfer_out()
    except LicenseServerError as e:
        _raise(e)


# ── установка кода ───────────────────────────────────────────────


@router.post(
    "/install/{plugin_id}",
    response_model=SimpleResponse,
    summary="Скачать wheel с сервера и установить",
)
async def install_plugin(
    plugin_id: str, _admin: AdminUser = Depends(require_superadmin())
) -> SimpleResponse:
    try:
        catalog_data = await entitlements.fetch_catalog()
        contents = await entitlements.download_wheel(plugin_id)
    except LicenseServerError as e:
        _raise(e)

    entry = next(
        (p for p in catalog_data.get("plugins", []) if p.get("id") == plugin_id), {}
    )
    expected_sha = entry.get("wheel_sha256") or ""
    actual_sha = hashlib.sha256(contents).hexdigest()
    if expected_sha and actual_sha != expected_sha:
        raise HTTPException(
            status_code=502,
            detail={"code": "wheel_sha_mismatch", "expected": expected_sha,
                    "actual": actual_sha},
        )

    version = entry.get("latest_version", "0.0.0")
    # Имя файла берём из самого wheel (иначе pip отвергает несовпадение
    # имени с метаданными: пакет smart_support = rwa_plugin_smart_support_tool).
    filename = (plugin_installer.wheel_filename_from_contents(contents)
                or f"rwa_plugin_{plugin_id}-{version}-py3-none-any.whl")
    try:
        installed = plugin_installer.accept_uploaded_wheel(
            filename=filename, contents=contents
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"code": "invalid_wheel", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"code": "pip_install_failed", "message": str(e)})

    logger.info(
        "admin_plugins.installed",
        extra={"plugin": plugin_id, "wheel": installed.path.name, "sha256": actual_sha[:16]},
    )
    return SimpleResponse(
        ok=True, requires_restart=True,
        message="Плагин установлен. Перезапустите backend для активации.",
    )


@router.post(
    "/upload",
    response_model=SimpleResponse,
    summary="Ручная загрузка wheel (fallback для air-gapped)",
)
async def upload_plugin(
    file: UploadFile = File(...),
    _admin: AdminUser = Depends(require_superadmin()),
) -> SimpleResponse:
    if not file.filename:
        raise HTTPException(status_code=422, detail={"code": "missing_filename"})
    contents = await file.read()
    try:
        installed = plugin_installer.accept_uploaded_wheel(
            filename=file.filename, contents=contents
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail={"code": "invalid_wheel", "message": str(e)})
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail={"code": "pip_install_failed", "message": str(e)})
    logger.info("admin_plugins.uploaded", extra={"wheel": installed.path.name})
    return SimpleResponse(
        ok=True, requires_restart=True,
        message="Wheel загружен. Перезапустите backend для активации.",
    )


@router.delete(
    "/{plugin_id}",
    response_model=SimpleResponse,
    summary="Удалить код плагина (wheel + pip-пакет)",
)
async def uninstall_plugin(
    plugin_id: str, _admin: AdminUser = Depends(require_superadmin())
) -> SimpleResponse:
    removed_any = False
    for wheel in plugin_installer.list_wheel_files():
        meta = plugin_installer.parse_wheel_name(wheel.name)
        if meta and meta.package_name == f"rwa-plugin-{plugin_id.replace('_', '-')}":
            plugin_installer.remove_wheel(wheel.name)
            removed_any = True
    if plugin_installer.pip_uninstall(f"rwa-plugin-{plugin_id.replace('_', '-')}"):
        removed_any = True

    logger.info("admin_plugins.uninstalled", extra={"plugin": plugin_id})
    return SimpleResponse(
        ok=True, requires_restart=True,
        message="Код удалён. Перезапустите backend." if removed_any
        else "Удалять было нечего.",
    )


# ── restart ──────────────────────────────────────────────────────


@router.post("/restart", response_model=SimpleResponse, summary="Перезапуск backend")
async def restart_backend(
    _admin: AdminUser = Depends(require_superadmin()),
) -> SimpleResponse:
    """SIGTERM самому себе; поднимает обратно docker-политика
    ``restart: unless-stopped`` — без неё эндпоинт просто гасит панель."""
    logger.warning("admin_plugins.restart_requested")
    import asyncio

    async def _delayed_exit() -> None:
        await asyncio.sleep(0.5)
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            os._exit(0)

    asyncio.create_task(_delayed_exit())
    return SimpleResponse(ok=True, message="Backend restarting…")
