"""Plugin API v1 — фасад панели для плагинов.

Единственный модуль, который разрешено импортировать плагину. Каждый
метод здесь — обещание совместимости: панель может свободно менять
внутренности, пока фасад отдаёт то же самое. Расширяется по потребности
плагинов, а не впрок.

Плагин получает готовый :class:`PluginContext` в свою ``build(ctx)``
(см. манифест v2 в core/plugins.py) и замыкает на него роутер и фоновые
задачи. Лицензии, URL сервера и токены плагина не касаются — это
обязанность ядра (core/entitlements.py).
"""
from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException

API_VERSION = 1

# Продуктовая телеметрия: счётчики фич копятся в памяти, heartbeat
# забирает их через drain_telemetry() и шлёт на сервер лицензирования.
_telemetry: Counter = Counter()


def drain_telemetry() -> dict[str, int]:
    """Снять накопленные счётчики (вызывается heartbeat-циклом)."""
    global _telemetry
    out, _telemetry = dict(_telemetry), Counter()
    return out


class CloudError(Exception):
    """Базовая ошибка вызова серверного ядра."""

    def __init__(self, code: str, detail: Any = None):
        super().__init__(code)
        self.code = code
        self.detail = detail


class CloudQuotaExceeded(CloudError):
    """Квота rt-вызовов исчерпана — UI предлагает докупить пакет."""


class CloudSubscriptionRequired(CloudError):
    """Подписка не активна (сервер ответил 402)."""


class CloudUnavailable(CloudError):
    """Сервер лицензирования недоступен (сеть/5xx)."""


class PluginDB:
    """Точка входа к PostgreSQL панели. Живой SQL — плагины наши,
    ограничивать нечего; фасад фиксирует только место входа."""

    def acquire(self):
        from shared.database import db_service
        return db_service.acquire()

    async def fetch(self, query: str, *args):
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args):
        async with self.acquire() as conn:
            return await conn.execute(query, *args)


class PluginSettings:
    """JSON-настройки плагина в общей таблице plugin_settings."""

    def __init__(self, plugin_id: str, db: PluginDB):
        self._plugin_id = plugin_id
        self._db = db

    async def get(self, key: str, default: Any = None) -> Any:
        import json
        raw = await self._db.fetchval(
            "SELECT value FROM plugin_settings WHERE plugin_id = $1 AND key = $2",
            self._plugin_id, key,
        )
        if raw is None:
            return default
        return json.loads(raw) if isinstance(raw, str) else raw

    async def set(self, key: str, value: Any) -> None:
        import json
        await self._db.execute(
            """INSERT INTO plugin_settings (plugin_id, key, value, updated_at)
               VALUES ($1, $2, $3::jsonb, NOW())
               ON CONFLICT (plugin_id, key) DO UPDATE SET
                   value = EXCLUDED.value, updated_at = NOW()""",
            self._plugin_id, key, json.dumps(value, ensure_ascii=False),
        )

    async def delete(self, key: str) -> None:
        await self._db.execute(
            "DELETE FROM plugin_settings WHERE plugin_id = $1 AND key = $2",
            self._plugin_id, key,
        )


class PluginLicense:
    """Состояние entitlement плагина (снапшот кэша ядра)."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id

    @property
    def _ent(self) -> Optional[dict]:
        from web.backend.core import entitlements
        return entitlements.plugin_state(self._plugin_id)

    @property
    def state(self) -> str:
        ent = self._ent
        return ent["state"] if ent else "missing"

    @property
    def usable(self) -> bool:
        from web.backend.core import entitlements
        return entitlements.is_usable(self._plugin_id)

    @property
    def tier(self) -> Optional[str]:
        ent = self._ent
        return ent.get("tier") if ent else None

    @property
    def quota(self) -> Optional[dict]:
        ent = self._ent
        return ent.get("quota") if ent else None

    def require(self) -> None:
        """Бросить 402, если подписка не активна (для ручных проверок —
        роуты и фоновые задачи ядро гейтит само)."""
        if not self.usable:
            raise HTTPException(
                status_code=402,
                detail={"plugin": self._plugin_id, "license_state": self.state,
                        "code": "license_required"},
            )


class CloudClient:
    """Вызовы серверного ядра плагина: ``await ctx.cloud.call("resolve", {...})``."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id

    async def call(self, method: str, payload: dict | None = None, *,
                   timeout: float = 30.0) -> dict:
        from web.backend.core import entitlements
        try:
            return await entitlements.rt_call(
                self._plugin_id, method, payload or {}, timeout=timeout,
            )
        except entitlements.LicenseServerError as e:
            if e.code == "quota_exceeded":
                raise CloudQuotaExceeded(e.code, e.detail) from e
            if e.code == "subscription_required" or e.status == 402:
                raise CloudSubscriptionRequired(e.code, e.detail) from e
            if e.code == "server_unreachable" or e.status >= 500:
                raise CloudUnavailable(e.code, e.detail) from e
            raise CloudError(e.code, e.detail) from e


class PluginEvents:
    """События панели. ``emit`` кладёт событие в общий диспатч вебхуков
    под неймспейсом плагина."""

    def __init__(self, plugin_id: str):
        self._plugin_id = plugin_id

    def emit(self, name: str, payload: dict) -> None:
        from web.backend.core.webhook_security import fire_event
        fire_event(f"plugin.{self._plugin_id}.{name}", payload)


class PluginTelemetry:
    """Анонимные продуктовые счётчики (уходят в heartbeat)."""

    def __init__(self, plugin_id: str):
        self._prefix = f"{plugin_id}."

    def count(self, feature: str, n: int = 1) -> None:
        _telemetry[self._prefix + feature] += n


@dataclass(frozen=True)
class PluginContext:
    plugin_id: str
    logger: logging.Logger
    db: PluginDB
    settings: PluginSettings
    license: PluginLicense
    cloud: CloudClient
    events: PluginEvents
    telemetry: PluginTelemetry


def build_context(plugin_id: str) -> PluginContext:
    """Собрать контекст плагина (зовётся загрузчиком, не плагином)."""
    db = PluginDB()
    return PluginContext(
        plugin_id=plugin_id,
        logger=logging.getLogger(f"plugin.{plugin_id}"),
        db=db,
        settings=PluginSettings(plugin_id, db),
        license=PluginLicense(plugin_id),
        cloud=CloudClient(plugin_id),
        events=PluginEvents(plugin_id),
        telemetry=PluginTelemetry(plugin_id),
    )
