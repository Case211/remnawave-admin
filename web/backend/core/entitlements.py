"""Клиент сервера лицензирования и кэш entitlements (контракт v1.1).

Панель keyless-идентифицируется на license.nexuslink.ru: при первом
обращении к витрине тихо регистрируется (instance_id + bearer-токен),
дальше heartbeat раз в несколько часов приносит подписанный Ed25519
entitlements JWT — «что этому инстансу можно». Токен проверяется локально
вшитым публичным ключом и кэшируется в БД: недоступность сервера не
трогает купленные плагины до истечения TTL токена (сетевой грейс 72 ч).

Плагины сами сюда не ходят — их гейтит ядро панели (см. core/plugins.py),
плагинам состояние отдаёт фасад ``ctx.license``.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from shared.db_query import select_sql

logger = logging.getLogger(__name__)


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))

# ── конфигурация ─────────────────────────────────────────────────

# Прод-ключ сервера лицензирования (Ed25519 raw, base64). Подделать
# entitlements без приватника нельзя; сам ключ — не секрет.
PUBLIC_KEY_B64 = "xasDeV371wZoM9iRiiU31BARjrzLfJqO8FQjj0qpWdk="

# Основной + резервные адреса сервера; перебираются по порядку.
LICENSE_SERVERS = ["https://license.nexuslink.ru"]

HEARTBEAT_INTERVAL_S = 8 * 3600
RETRY_INTERVAL_S = 15 * 60
HTTP_TIMEOUT_S = 15.0

LINK_TABLE = "license_link"

STATE_ACTIVE = "active"
STATE_GRACE = "grace"
STATE_EXPIRED = "expired"
USABLE_STATES = (STATE_ACTIVE, STATE_GRACE)


def _servers() -> list[str]:
    override = os.environ.get("RWA_LICENSE_SERVER", "").strip()
    return [override.rstrip("/")] if override else LICENSE_SERVERS


def _public_key_raw() -> bytes:
    override = os.environ.get("RWA_LICENSE_PUBKEY", "").strip()
    return base64.b64decode(override or PUBLIC_KEY_B64)


# ── состояние в памяти ───────────────────────────────────────────

@dataclass
class EntitlementsCache:
    instance_id: Optional[str] = None
    instance_token: Optional[str] = None
    plugins: dict[str, dict[str, Any]] = field(default_factory=dict)
    jwt_exp: int = 0
    messages: list[dict] = field(default_factory=list)
    catalog: Optional[dict] = None
    last_sync_ok: Optional[float] = None
    last_error: Optional[str] = None


_cache = EntitlementsCache()
_lock = asyncio.Lock()


def plugin_state(plugin_id: str) -> Optional[dict[str, Any]]:
    """Снапшот entitlement плагина из кэша (None — подписки нет).

    После истечения JWT кэш считается протухшим: сетевой грейс кончился,
    доверять старым правам нельзя.
    """
    if _cache.jwt_exp and time.time() >= _cache.jwt_exp:
        return None
    return _cache.plugins.get(plugin_id)


def is_usable(plugin_id: str) -> bool:
    ent = plugin_state(plugin_id)
    return bool(ent and ent.get("state") in USABLE_STATES)


def status_summary() -> dict[str, Any]:
    """Сводка для админ-API (страница «Плагины»)."""
    return {
        "registered": _cache.instance_token is not None,
        "instance_id": _cache.instance_id,
        "plugins": _cache.plugins,
        "jwt_exp": _cache.jwt_exp or None,
        "last_sync_ok": _cache.last_sync_ok,
        "last_error": _cache.last_error,
        "messages": _cache.messages,
    }


# ── верификация entitlements JWT ─────────────────────────────────

def verify_entitlements_jwt(token: str, *, now: Optional[int] = None) -> Optional[dict]:
    """Проверить подпись/срок и вернуть payload. None — токен не годен.

    Формат v1.1: ``{"iss": "rwa-licensing", "sub": "<instance>",
    "iat", "exp", "plugins": {id: {...}}}``. Алгоритм захардкожен
    (EdDSA) — ровно как в offline-верификаторе рядом.
    """
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    if not token or token.count(".") != 2:
        return None
    header_b64, payload_b64, sig_b64 = token.split(".")
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(sig_b64)
    except (ValueError, json.JSONDecodeError):
        return None
    if header.get("alg") != "EdDSA" or payload.get("iss") != "rwa-licensing":
        return None
    try:
        key = Ed25519PublicKey.from_public_bytes(_public_key_raw())
        key.verify(signature, f"{header_b64}.{payload_b64}".encode("ascii"))
    except (InvalidSignature, ValueError):
        return None
    current = now if now is not None else int(time.time())
    if int(payload.get("exp") or 0) <= current:
        return None
    if not isinstance(payload.get("plugins"), dict):
        return None
    return payload


def _adopt_jwt(jwt_token: str) -> bool:
    payload = verify_entitlements_jwt(jwt_token)
    if payload is None:
        return False
    _cache.plugins = payload["plugins"]
    _cache.jwt_exp = int(payload["exp"])
    return True


# ── персистентность (таблица license_link, одна строка) ──────────

async def _load_link() -> None:
    from shared.database import db_service

    if not db_service.is_connected:
        return
    try:
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(LINK_TABLE,
                           "instance_id, instance_token, entitlements_jwt, catalog_cache",
                           "WHERE id = 1")
            )
    except Exception:
        logger.warning("entitlements.load_failed", exc_info=True)
        return
    if not row:
        return
    _cache.instance_id = str(row["instance_id"]) if row["instance_id"] else None
    _cache.instance_token = row["instance_token"]
    if row["catalog_cache"]:
        try:
            _cache.catalog = json.loads(row["catalog_cache"])
        except (TypeError, ValueError):
            pass
    if row["entitlements_jwt"] and not _adopt_jwt(row["entitlements_jwt"]):
        logger.info("entitlements.cached_jwt_stale")


async def _save_link(*, jwt_token: Optional[str] = None, catalog: Optional[dict] = None) -> None:
    from shared.database import db_service

    if not db_service.is_connected:
        return
    async with db_service.acquire() as conn:
        await conn.execute(
            f"""INSERT INTO {LINK_TABLE} (id, instance_id, instance_token,
                                          entitlements_jwt, catalog_cache, updated_at)
                VALUES (1, $1, $2, $3, $4::jsonb, NOW())
                ON CONFLICT (id) DO UPDATE SET
                    instance_id = EXCLUDED.instance_id,
                    instance_token = EXCLUDED.instance_token,
                    entitlements_jwt = COALESCE(EXCLUDED.entitlements_jwt,
                                                {LINK_TABLE}.entitlements_jwt),
                    catalog_cache = COALESCE(EXCLUDED.catalog_cache,
                                             {LINK_TABLE}.catalog_cache),
                    updated_at = NOW()""",
            uuid.UUID(_cache.instance_id) if _cache.instance_id else None,
            _cache.instance_token,
            jwt_token,
            json.dumps(catalog, ensure_ascii=False) if catalog is not None else None,
        )


# ── HTTP-клиент сервера ──────────────────────────────────────────

class LicenseServerError(Exception):
    def __init__(self, code: str, status: int = 0, detail: Any = None):
        super().__init__(code)
        self.code = code
        self.status = status
        self.detail = detail


async def _request(
    method: str,
    path: str,
    *,
    json_body: Optional[dict] = None,
    authed: bool = True,
    expect_bytes: bool = False,
) -> Any:
    """Запрос к серверу лицензирования с перебором зеркал."""
    headers = {}
    if authed:
        if not _cache.instance_token:
            raise LicenseServerError("not_registered")
        headers["Authorization"] = f"Bearer {_cache.instance_token}"

    last_exc: Optional[Exception] = None
    for base in _servers():
        try:
            async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_S) as client:
                resp = await client.request(method, base + path, json=json_body, headers=headers)
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("detail", {})
                except ValueError:
                    detail = {}
                raise LicenseServerError(
                    detail.get("code", f"http_{resp.status_code}"),
                    status=resp.status_code,
                    detail=detail,
                )
            return resp.content if expect_bytes else resp.json()
        except (httpx.HTTPError, OSError) as e:
            last_exc = e
            continue
    raise LicenseServerError("server_unreachable", detail=str(last_exc))


# ── основные операции ────────────────────────────────────────────

async def ensure_registered() -> None:
    """Тихая регистрация инстанса (первое открытие витрины)."""
    async with _lock:
        if _cache.instance_token:
            return
        if not _cache.instance_id:
            _cache.instance_id = str(uuid.uuid4())
        try:
            data = await _request(
                "POST", "/v1/register", authed=False,
                json_body={"instance_id": _cache.instance_id,
                           "meta": {"panel_version": _panel_version()}},
            )
        except LicenseServerError as e:
            _cache.last_error = e.code
            raise
        _cache.instance_token = data["instance_token"]
        _adopt_jwt(data.get("entitlements_jwt", ""))
        _cache.last_sync_ok = time.time()
        _cache.last_error = None
        await _save_link(jwt_token=data.get("entitlements_jwt"))
        logger.info("entitlements.registered", extra={"instance_id": _cache.instance_id})


def _panel_version() -> str:
    try:
        from web.backend.core.update_checker import _detect_local_version
        return _detect_local_version()
    except Exception:
        return "unknown"


async def heartbeat_now(usage_stats: Optional[dict] = None) -> None:
    """Синхронизировать entitlements с сервером немедленно."""
    plugin_versions = {}
    try:
        from web.backend.core.plugins import loaded_plugins
        plugin_versions = {m.id: m.version for m in loaded_plugins()}
    except Exception:
        pass
    data = await _request(
        "POST", "/v1/heartbeat",
        json_body={"panel_version": _panel_version(),
                   "plugin_versions": plugin_versions,
                   "usage_stats": usage_stats or {}},
    )
    if not _adopt_jwt(data.get("entitlements_jwt", "")):
        raise LicenseServerError("bad_entitlements_jwt")
    _cache.messages = data.get("messages", [])
    _cache.last_sync_ok = time.time()
    _cache.last_error = None
    await _save_link(jwt_token=data["entitlements_jwt"])


async def fetch_catalog(force: bool = False) -> dict:
    """Каталог витрины: живой с сервера, фолбэк — последний удачный."""
    if _cache.catalog is not None and not force:
        return _cache.catalog
    try:
        catalog = await _request("GET", "/v1/catalog", authed=False)
    except LicenseServerError:
        if _cache.catalog is not None:
            return _cache.catalog
        raise
    _cache.catalog = catalog
    await _save_link(catalog=catalog)
    return catalog


async def purchase(items: list[dict]) -> dict:
    await ensure_registered()
    return await _request("POST", "/v1/purchase-intent", json_body={"items": items})


async def order_status(order_id: str) -> dict:
    return await _request("GET", f"/v1/order/{order_id}")


async def transfer_out() -> dict:
    return await _request("POST", "/v1/transfer-out")


async def redeem(code: str) -> None:
    data = await _request("POST", "/v1/redeem", json_body={"code": code})
    if not _adopt_jwt(data.get("entitlements_jwt", "")):
        raise LicenseServerError("bad_entitlements_jwt")
    await _save_link(jwt_token=data["entitlements_jwt"])


async def download_wheel(plugin_id: str) -> bytes:
    return await _request("GET", f"/v1/download/{plugin_id}", expect_bytes=True)


async def rt_call(plugin_id: str, rt_method: str, payload: dict, *, timeout: float = 30.0) -> dict:
    """Вызов серверного ядра плагина (используется фасадом ctx.cloud)."""
    if not _cache.instance_token:
        raise LicenseServerError("not_registered")
    headers = {"Authorization": f"Bearer {_cache.instance_token}"}
    last_exc: Optional[Exception] = None
    for base in _servers():
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{base}/v1/rt/{plugin_id}/{rt_method}",
                    json=payload, headers=headers,
                )
            if resp.status_code >= 400:
                try:
                    detail = resp.json().get("detail", {})
                except ValueError:
                    detail = {}
                raise LicenseServerError(
                    detail.get("code", f"http_{resp.status_code}"),
                    status=resp.status_code, detail=detail,
                )
            return resp.json()
        except (httpx.HTTPError, OSError) as e:
            last_exc = e
            continue
    raise LicenseServerError("server_unreachable", detail=str(last_exc))


# ── фоновый цикл ─────────────────────────────────────────────────

async def startup() -> None:
    """Загрузить кэш из БД (зовётся из lifespan до регистрации плагинов)."""
    await _load_link()
    if _cache.instance_token:
        logger.info(
            "entitlements.loaded",
            extra={"plugins": list(_cache.plugins), "jwt_exp": _cache.jwt_exp},
        )


async def heartbeat_loop() -> None:
    """Фоновая синхронизация. Первый проход — сразу (панель рестартует
    редко; свежий entitlements при старте важнее равномерности)."""
    while True:
        try:
            if _cache.instance_token:
                from web.backend.core.plugin_api import drain_telemetry
                await heartbeat_now(usage_stats=drain_telemetry())
                delay: float = HEARTBEAT_INTERVAL_S * random.uniform(0.75, 1.25)
            else:
                delay = RETRY_INTERVAL_S  # не зарегистрированы — ждём открытия витрины
        except LicenseServerError as e:
            _cache.last_error = e.code
            logger.warning("entitlements.heartbeat_failed", extra={"code": e.code})
            delay = RETRY_INTERVAL_S
        except Exception:
            logger.exception("entitlements.heartbeat_crashed")
            delay = RETRY_INTERVAL_S
        await asyncio.sleep(delay)
