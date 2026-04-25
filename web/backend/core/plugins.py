"""Plugin loader and registry for paid/optional addons.

Plugins register themselves through Python entry points (group ``rwa.plugin``)
or, for development, through the ``RWA_DEV_PLUGINS`` env variable
("module.path:factory_callable" entries separated by commas).

A plugin returns a :class:`PluginManifest` describing its router, RBAC
resources, navigation entries, scheduled tasks, and license state.

The loader is fail-soft: a broken plugin must not crash the panel. It is also
license-aware — when a plugin reports ``license_state`` outside ``valid`` or
``not_required``, its real router is replaced with a stub that returns
HTTP 402 for every path under the plugin's prefix.
"""
from __future__ import annotations

import importlib
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Iterable, Literal, Optional

from fastapi import APIRouter, FastAPI, HTTPException

logger = logging.getLogger(__name__)

LicenseState = Literal["valid", "expired", "missing", "not_required"]

API_PREFIX = "/api/v2/plugins"


@dataclass(frozen=True)
class NavEntry:
    """A single navigation link contributed by a plugin.

    ``path`` is the frontend route (relative to the panel root, e.g.
    ``/plugins/debugger``). ``label_i18n`` is an i18n key the frontend will
    translate. ``icon`` is a lucide icon name as used in Sidebar.tsx.
    ``permission`` is an optional ``(resource, action)`` gate.
    """

    path: str
    label_i18n: str
    icon: str
    permission: Optional[tuple[str, str]] = None
    section_i18n: Optional[str] = None  # optional sidebar section header


@dataclass
class ScheduledTask:
    name: str
    interval_seconds: int
    coro: Callable[[], Awaitable[None]]


@dataclass
class PluginManifest:
    id: str
    name: str
    version: str
    license_state: LicenseState = "not_required"
    router: Optional[APIRouter] = None
    rbac_resources: dict[str, list[str]] = field(default_factory=dict)
    navigation: list[NavEntry] = field(default_factory=list)
    scheduled_tasks: list[ScheduledTask] = field(default_factory=list)


# ── private state ────────────────────────────────────────────────

_loaded: list[PluginManifest] = []
_rbac_extras: dict[str, set[str]] = {}


def loaded_plugins() -> list[PluginManifest]:
    """Return manifests registered in the current process."""
    return list(_loaded)


def get_extra_rbac_resources() -> dict[str, list[str]]:
    """RBAC resources contributed by plugins (sorted, deterministic)."""
    return {res: sorted(actions) for res, actions in _rbac_extras.items()}


# ── discovery ────────────────────────────────────────────────────

def _iter_entry_point_factories() -> Iterable[tuple[str, Callable[[], Any]]]:
    try:
        from importlib.metadata import entry_points
    except Exception:  # pragma: no cover
        logger.exception("plugins.entry_points_unavailable")
        return []

    eps: list = []
    try:
        # Python 3.10+: selectable interface
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
    """Development-time plugins via ``RWA_DEV_PLUGINS=mod.path:callable,...``.

    Useful for tests and local smoke runs without ``pip install``.
    """
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
    """Discover and instantiate plugin manifests. Fail-soft."""
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
            extra={
                "plugin": result.id,
                "version": result.version,
                "license_state": result.license_state,
                "source": source,
            },
        )

    return manifests


# ── registration ─────────────────────────────────────────────────

def _license_stub_router(plugin_id: str, state: LicenseState) -> APIRouter:
    """Catch-all router that returns HTTP 402 for any path under the plugin.

    Used for plugins whose license is expired or missing — UI shows the
    pages but every API call fails with a structured 402 payload, letting
    the frontend display a "buy/renew license" banner.
    """
    r = APIRouter()
    code = "license_expired" if state == "expired" else "license_required"

    async def _stub() -> None:
        raise HTTPException(
            status_code=402,
            detail={"plugin": plugin_id, "license_state": state, "code": code},
        )

    r.add_api_route(
        "/{path:path}",
        _stub,
        methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        include_in_schema=False,
    )
    return r


def register(app: FastAPI) -> list[PluginManifest]:
    """Discover plugins and attach them to the FastAPI app.

    Idempotent within a process: subsequent calls reset the registry, so
    tests can re-register without leaking state. Routers from previous
    calls remain attached to the app — callers must not invoke ``register``
    on the same app twice in production.
    """
    _loaded.clear()
    _rbac_extras.clear()

    for manifest in discover_plugins():
        prefix = f"{API_PREFIX}/{manifest.id}"
        tags = [f"plugin:{manifest.id}"]

        if manifest.license_state in ("valid", "not_required") and manifest.router is not None:
            app.include_router(manifest.router, prefix=prefix, tags=tags)
        else:
            app.include_router(
                _license_stub_router(manifest.id, manifest.license_state),
                prefix=prefix,
                tags=tags,
            )

        for resource, actions in manifest.rbac_resources.items():
            _rbac_extras.setdefault(resource, set()).update(actions)

        _loaded.append(manifest)

    if _loaded:
        logger.info("plugins.registered", extra={"count": len(_loaded)})
    return list(_loaded)
