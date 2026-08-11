"""Загрузчик плагинов (манифест v2, Plugin API v1).

Плагин регистрируется через entry point ``rwa.plugin`` (или
``RWA_DEV_PLUGINS=module:factory,...`` для разработки) и возвращает
декларативный :class:`PluginManifest`. Роутер и фоновые задачи плагин
отдаёт фабрикой ``build(ctx)`` — панель зовёт её с готовым
:class:`~web.backend.core.plugin_api.PluginContext`.

Лицензирование — забота ядра, не плагина: роутер платного плагина
монтируется всегда, но каждый запрос проходит через динамический гейт по
entitlements-кэшу (core/entitlements.py). Покупка и истечение подписки
применяются без рестарта; рестарт нужен только для установки/удаления
wheel. Фоновые задачи проверяют entitlement на каждом тике.

Загрузчик fail-soft: сломанный плагин не должен уронить панель.
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Literal, Optional

from fastapi import APIRouter, FastAPI, HTTPException

from web.backend.core.plugin_api import API_VERSION, PluginContext, build_context

logger = logging.getLogger(__name__)

# Значения, которые понимает фронт (lib/plugins.ts): valid | expired |
# missing | not_required. Семантика сохранена при переезде на онлайн-
# лицензии: active/grace → valid.
UiLicenseState = Literal["valid", "expired", "missing", "not_required"]

API_PREFIX = "/api/v2/plugins"


@dataclass(frozen=True)
class NavEntry:
    """Пункт навигации от плагина (см. Sidebar.tsx)."""

    path: str
    label_i18n: str
    icon: str
    permission: Optional[tuple[str, str]] = None
    section_i18n: Optional[str] = None


@dataclass
class ScheduledTask:
    name: str
    interval_seconds: int
    coro: Callable[[], Awaitable[None]]


@dataclass
class PluginParts:
    """Что плагин собирает в ``build(ctx)``: роутер и фоновые задачи,
    замкнутые на контекст."""

    router: Optional[APIRouter] = None
    scheduled_tasks: list[ScheduledTask] = field(default_factory=list)


@dataclass(frozen=True)
class PluginUI:
    """How to render the page of a plugin that ships outside this repo.

    Built-in plugin pages live in ``web/frontend/src/plugins/<id>/`` and are
    wired through ``PLUGIN_ROUTES``. A plugin distributed as a standalone
    wheel cannot add itself there, so it declares its UI here instead and the
    frontend mounts it on the generic ``/plugins/:pluginId`` route.

    ``kind="module"`` — the frontend loads ``api_prefix + path`` as a script;
    the script registers ``window.rwaPluginUI[<plugin id>] = {mount, unmount}``
    and renders into the element it is given. Same-origin, so it passes the
    panel CSP (``script-src 'self'``).

    ``kind="iframe"`` — the frontend embeds ``api_prefix + path`` in an
    iframe; the plugin must serve that page with ``frame-ancestors 'self'``.
    """

    kind: Literal["module", "iframe"] = "module"
    path: str = "/app"


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    api_version: int = API_VERSION
    billing: Literal["free", "subscription"] = "free"
    build: Optional[Callable[[PluginContext], PluginParts]] = None
    rbac_resources: dict[str, list[str]] = field(default_factory=dict)
    navigation: list[NavEntry] = field(default_factory=list)
    ui: Optional[PluginUI] = None


# ── private state ────────────────────────────────────────────────

_loaded: list[PluginManifest] = []
_rbac_extras: dict[str, set[str]] = {}
_parts: dict[str, PluginParts] = {}


def loaded_plugins() -> list[PluginManifest]:
    return list(_loaded)


def get_extra_rbac_resources() -> dict[str, list[str]]:
    return {res: sorted(actions) for res, actions in _rbac_extras.items()}


def ui_license_state(manifest: PluginManifest) -> UiLicenseState:
    """Состояние для фронта из entitlements-кэша."""
    if manifest.billing == "free":
        return "not_required"
    from web.backend.core import entitlements

    ent = entitlements.plugin_state(manifest.id)
    if ent is None:
        return "missing"
    if ent.get("state") in entitlements.USABLE_STATES:
        return "valid"
    return "expired"


# ── discovery ────────────────────────────────────────────────────

def _iter_entry_point_factories() -> Iterable[tuple[str, Callable[[], Any]]]:
    try:
        from importlib.metadata import entry_points
    except Exception:  # pragma: no cover
        logger.exception("plugins.entry_points_unavailable")
        return []

    eps: list = []
    try:
        eps = list(entry_points(group="rwa.plugin"))  # type: ignore[arg-type]
    except TypeError:  # pragma: no cover
        all_eps = entry_points()
        eps = list(all_eps.get("rwa.plugin", []))  # type: ignore[union-attr]
    except Exception:
        logger.exception("plugins.entry_points_lookup_failed")
        return []

    for ep in eps:
        name = getattr(ep, "name", "<unknown>")
        try:
            factory = ep.load()
        except Exception:
            logger.exception("plugins.entry_point_load_failed", extra={"entry_point": name})
            continue
        yield name, factory


def _iter_dev_factories() -> Iterable[tuple[str, Callable[[], Any]]]:
    """Дев-плагины через ``RWA_DEV_PLUGINS=mod.path:callable,...``."""
    raw = os.environ.get("RWA_DEV_PLUGINS", "").strip()
    if not raw:
        return []

    out: list[tuple[str, Callable[[], Any]]] = []
    for spec in (s.strip() for s in raw.split(",") if s.strip()):
        if ":" not in spec:
            logger.warning("plugins.dev_spec_invalid", extra={"spec": spec})
            continue
        module_path, attr = spec.split(":", 1)
        try:
            module = importlib.import_module(module_path)
            factory = getattr(module, attr)
        except Exception:
            logger.exception("plugins.dev_spec_load_failed", extra={"spec": spec})
            continue
        out.append((spec, factory))
    return out


def discover_plugins() -> list[PluginManifest]:
    """Найти и инстанцировать манифесты. Fail-soft."""
    manifests: list[PluginManifest] = []
    seen_ids: set[str] = set()

    factories = list(_iter_entry_point_factories()) + list(_iter_dev_factories())
    for source, factory in factories:
        try:
            result = factory() if callable(factory) else factory
        except Exception:
            logger.exception("plugins.factory_raised", extra={"source": source})
            continue

        if not isinstance(result, PluginManifest):
            logger.error(
                "plugins.invalid_manifest",
                extra={"source": source, "got_type": type(result).__name__},
            )
            continue

        if result.api_version != API_VERSION:
            logger.error(
                "plugins.api_version_mismatch",
                extra={"plugin": result.id, "plugin_api": result.api_version,
                       "panel_api": API_VERSION},
            )
            continue

        if result.id in seen_ids:
            logger.warning(
                "plugins.duplicate_id_ignored",
                extra={"source": source, "plugin": result.id},
            )
            continue

        seen_ids.add(result.id)
        manifests.append(result)
        logger.info(
            "plugins.discovered",
            extra={"plugin": result.id, "version": result.version,
                   "billing": result.billing, "source": source},
        )

    return manifests


# ── динамический лицензионный гейт ───────────────────────────────

def _entitlement_gate(plugin_id: str) -> Callable[[], None]:
    """FastAPI-dependency: 402 на каждый запрос без активной подписки.

    Проверка — O(1) по кэшу в памяти, поэтому её не стыдно вешать на
    каждый запрос. Payload повторяет старый 402-стаб — фронт уже умеет
    показывать по нему баннер «купить/продлить».
    """

    def gate() -> None:
        from web.backend.core import entitlements

        if entitlements.is_usable(plugin_id):
            return
        ent = entitlements.plugin_state(plugin_id)
        state = "expired" if ent else "missing"
        code = "license_expired" if ent else "license_required"
        raise HTTPException(
            status_code=402,
            detail={"plugin": plugin_id, "license_state": state, "code": code},
        )

    return gate


# ── registration ─────────────────────────────────────────────────

def register(app: FastAPI) -> list[PluginManifest]:
    """Открыть плагины и примонтировать их к приложению.

    Идемпотентен в рамках процесса для тестов; в проде зовётся один раз
    из lifespan.
    """
    from fastapi import Depends

    _loaded.clear()
    _rbac_extras.clear()
    _parts.clear()

    for manifest in discover_plugins():
        ctx = build_context(manifest.id)
        try:
            parts = manifest.build(ctx) if manifest.build else PluginParts()
        except Exception:
            logger.exception("plugins.build_failed", extra={"plugin": manifest.id})
            continue
        if not isinstance(parts, PluginParts):
            logger.error(
                "plugins.invalid_parts",
                extra={"plugin": manifest.id, "got_type": type(parts).__name__},
            )
            continue

        if parts.router is not None:
            dependencies = (
                [Depends(_entitlement_gate(manifest.id))]
                if manifest.billing == "subscription" else []
            )
            app.include_router(
                parts.router,
                prefix=f"{API_PREFIX}/{manifest.id}",
                tags=[f"plugin:{manifest.id}"],
                dependencies=dependencies,
            )

        for resource, actions in manifest.rbac_resources.items():
            _rbac_extras.setdefault(resource, set()).update(actions)

        _parts[manifest.id] = parts
        _loaded.append(manifest)

    if _loaded:
        logger.info("plugins.registered", extra={"count": len(_loaded)})
    return list(_loaded)


# ── scheduled tasks ──────────────────────────────────────────────

async def _safe_periodic_loop(manifest: PluginManifest, task: ScheduledTask) -> None:
    """Крутить одну задачу вечно, изолируя падения тиков.

    Платные плагины: тик пропускается, пока entitlement не активен —
    подписка кончилась → фоновая работа остановилась без рестарта,
    оплатили → возобновилась.
    """
    from web.backend.core import entitlements

    interval = max(1, int(task.interval_seconds))
    logger.info(
        "plugins.task_started",
        extra={"plugin": manifest.id, "task": task.name, "interval_seconds": interval},
    )
    while True:
        try:
            if manifest.billing == "free" or entitlements.is_usable(manifest.id):
                await task.coro()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "plugins.task_iteration_failed",
                extra={"plugin": manifest.id, "task": task.name},
            )
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.info(
                "plugins.task_cancelled",
                extra={"plugin": manifest.id, "task": task.name},
            )
            raise


def start_scheduled_tasks() -> list[asyncio.Task]:
    """Поднять фоновые задачи всех плагинов (лицензия решается на тике)."""
    tasks: list[asyncio.Task] = []
    for manifest in _loaded:
        for task in _parts.get(manifest.id, PluginParts()).scheduled_tasks:
            handle = asyncio.create_task(
                _safe_periodic_loop(manifest, task),
                name=f"plugin:{manifest.id}:{task.name}",
            )
            tasks.append(handle)
    return tasks
