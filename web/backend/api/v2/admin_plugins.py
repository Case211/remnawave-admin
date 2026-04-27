"""Admin endpoints for the in-panel plugin manager.

Lets a superadmin upload a wheel + license JWT, list installed plugins,
update a license, or remove a plugin entirely. All operations are
gated by ``require_superadmin``: the blast radius of installing a
malicious wheel is the whole panel process, so we don't open this up
to lesser roles.

Restart contract: install/uninstall/license-update all require a
backend restart to take effect (FastAPI doesn't hot-reload routes
contributed by entry points). The endpoints are honest about that —
they return ``requires_restart: true`` and the UI surfaces a
`Перезапустить` button that calls ``POST /restart``.
"""
from __future__ import annotations

import logging
import os
import signal
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, require_superadmin
from web.backend.core import plugin_licenses, plugin_installer
from web.backend.core.license import peek_jwt_payload
from web.backend.core.plugins import loaded_plugins

logger = logging.getLogger(__name__)
router = APIRouter()


# ── schemas ──────────────────────────────────────────────────────


class InstalledPluginInfo(BaseModel):
    plugin_id: str
    name: Optional[str] = None
    version: Optional[str] = None
    license_state: Optional[str] = None
    license_set: bool
    wheel_name: Optional[str] = None
    installed_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class WheelFileInfo(BaseModel):
    """A wheel that's present on disk but not yet matched to a license."""

    filename: str
    package_name: str
    version: str


class PluginInventoryResponse(BaseModel):
    installed: List[InstalledPluginInfo]
    pending_wheels: List[WheelFileInfo] = Field(default_factory=list)
    plugins_dir: str
    requires_restart: bool = False


class InstallResponse(BaseModel):
    plugin_id: Optional[str] = None
    wheel_name: str
    version: str
    requires_restart: bool = True
    message: str


class LicenseUpdateIn(BaseModel):
    plugin_id: str
    jwt_token: str


class MasterLicenseIn(BaseModel):
    """One JWT that covers multiple plugins via its ``plugins`` claim."""

    jwt_token: str


class MasterLicenseOut(BaseModel):
    plugin_ids: List[str]
    expires_at: Optional[datetime] = None
    tier: Optional[str] = None
    sub: Optional[str] = None
    requires_restart: bool = True


class SimpleResponse(BaseModel):
    ok: bool
    requires_restart: bool = False
    message: Optional[str] = None


# ── endpoints ────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PluginInventoryResponse,
    summary="List installed plugins, their licenses and pending wheels",
)
async def list_inventory(
    _admin: AdminUser = Depends(require_superadmin()),
) -> PluginInventoryResponse:
    licenses_rows = {row["plugin_id"]: row for row in await plugin_licenses.list_all()}
    loaded = {m.id: m for m in loaded_plugins()}

    items: List[InstalledPluginInfo] = []
    seen_ids = set(licenses_rows.keys()) | set(loaded.keys())
    for plugin_id in sorted(seen_ids):
        manifest = loaded.get(plugin_id)
        lic = licenses_rows.get(plugin_id, {})
        items.append(
            InstalledPluginInfo(
                plugin_id=plugin_id,
                name=getattr(manifest, "name", None),
                version=getattr(manifest, "version", None) or lic.get("version"),
                license_state=getattr(manifest, "license_state", None),
                license_set=plugin_id in licenses_rows,
                wheel_name=lic.get("wheel_name"),
                installed_at=lic.get("installed_at"),
                updated_at=lic.get("updated_at"),
            )
        )

    pending = _list_pending_wheels(installed_plugin_ids=set(licenses_rows.keys()))
    return PluginInventoryResponse(
        installed=items,
        pending_wheels=pending,
        plugins_dir=str(plugin_installer.plugins_dir()),
    )


@router.post(
    "/upload",
    response_model=InstallResponse,
    summary="Upload a wheel + license JWT for a plugin",
)
async def upload_plugin(
    file: UploadFile = File(...),
    plugin_id: str = Form(..., min_length=1, max_length=64),
    jwt_token: str = Form(..., min_length=10),
    _admin: AdminUser = Depends(require_superadmin()),
) -> InstallResponse:
    if not file.filename:
        raise HTTPException(status_code=422, detail={"code": "missing_filename"})

    contents = await file.read()
    try:
        installed = plugin_installer.accept_uploaded_wheel(
            filename=file.filename,
            contents=contents,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_wheel", "message": str(e)},
        ) from e
    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "pip_install_failed", "message": str(e)},
        ) from e

    await plugin_licenses.upsert(
        plugin_id=plugin_id,
        jwt_token=jwt_token.strip(),
        wheel_name=installed.path.name,
        version=installed.version,
    )

    logger.info(
        "admin_plugins.uploaded",
        extra={
            "plugin_id": plugin_id,
            "wheel": installed.path.name,
            "version": installed.version,
        },
    )
    return InstallResponse(
        plugin_id=plugin_id,
        wheel_name=installed.path.name,
        version=installed.version,
        requires_restart=True,
        message="Плагин загружен. Перезапустите backend для активации.",
    )


@router.put(
    "/license",
    response_model=SimpleResponse,
    summary="Update the license JWT for an already-installed plugin",
)
async def update_license(
    payload: LicenseUpdateIn = Body(...),
    _admin: AdminUser = Depends(require_superadmin()),
) -> SimpleResponse:
    await plugin_licenses.upsert(
        plugin_id=payload.plugin_id,
        jwt_token=payload.jwt_token.strip(),
    )
    logger.info("admin_plugins.license_updated", extra={"plugin_id": payload.plugin_id})
    return SimpleResponse(
        ok=True,
        requires_restart=True,
        message="Лицензия обновлена. Перезапустите backend.",
    )


@router.delete(
    "/{plugin_id}",
    response_model=SimpleResponse,
    summary="Remove a plugin (deletes wheel + license; pip-uninstalls package)",
)
async def uninstall_plugin(
    plugin_id: str,
    _admin: AdminUser = Depends(require_superadmin()),
) -> SimpleResponse:
    licenses_rows = {row["plugin_id"]: row for row in await plugin_licenses.list_all()}
    lic = licenses_rows.get(plugin_id)

    # Best-effort cleanup. We try every step regardless of intermediate
    # failure because partial state is worse than over-cleaning.
    if lic and lic.get("wheel_name"):
        plugin_installer.remove_wheel(str(lic["wheel_name"]))

    # ``manifest.id`` is the human plugin id ("smart_support"); the pip
    # package name follows ``rwa_plugin_<id>`` convention. Try the wheel-
    # derived name first, fall back to the convention.
    pip_pkg_candidates: List[str] = []
    if lic and lic.get("wheel_name"):
        meta = plugin_installer.parse_wheel_name(str(lic["wheel_name"]))
        if meta:
            pip_pkg_candidates.append(meta.package_name)
    pip_pkg_candidates.append(f"rwa-plugin-{plugin_id.replace('_', '-')}")

    for pkg in pip_pkg_candidates:
        if plugin_installer.pip_uninstall(pkg):
            break

    await plugin_licenses.delete(plugin_id)

    logger.info("admin_plugins.uninstalled", extra={"plugin_id": plugin_id})
    return SimpleResponse(
        ok=True,
        requires_restart=True,
        message="Плагин удалён. Перезапустите backend для применения.",
    )


@router.post(
    "/master-license",
    response_model=MasterLicenseOut,
    summary="Apply one license JWT across all plugins it covers",
)
async def apply_master_license(
    payload: MasterLicenseIn = Body(...),
    _admin: AdminUser = Depends(require_superadmin()),
) -> MasterLicenseOut:
    """Decode a bundle JWT and fan it out to every plugin id it lists.

    The signature is **not** verified here — that happens when each
    plugin loads itself against its own embedded public key. We just
    need to know which plugin_ids to write the token under so the
    operator doesn't paste it once per plugin.
    """
    payload_obj = peek_jwt_payload(payload.jwt_token)
    if payload_obj is None:
        raise HTTPException(
            status_code=422,
            detail={"code": "malformed_jwt", "message": "Не удалось разобрать токен"},
        )
    plugin_ids = [str(p) for p in (payload_obj.get("plugins") or []) if isinstance(p, str)]
    if not plugin_ids:
        raise HTTPException(
            status_code=422,
            detail={"code": "no_plugins_claim", "message": "В токене не указаны плагины"},
        )

    token = payload.jwt_token.strip()
    for plugin_id in plugin_ids:
        await plugin_licenses.upsert(plugin_id=plugin_id, jwt_token=token)

    exp_raw = payload_obj.get("exp")
    expires_at: Optional[datetime] = None
    if isinstance(exp_raw, (int, float)):
        expires_at = datetime.utcfromtimestamp(int(exp_raw))

    logger.info(
        "admin_plugins.master_license_applied",
        extra={"plugin_ids": plugin_ids, "exp": exp_raw},
    )
    return MasterLicenseOut(
        plugin_ids=plugin_ids,
        expires_at=expires_at,
        tier=payload_obj.get("tier"),
        sub=payload_obj.get("sub"),
        requires_restart=True,
    )


@router.post(
    "/restart",
    response_model=SimpleResponse,
    summary="Restart the backend process to apply plugin changes",
)
async def restart_backend(
    _admin: AdminUser = Depends(require_superadmin()),
) -> SimpleResponse:
    """Send SIGTERM to the current process.

    We rely on the docker compose ``restart: unless-stopped`` policy
    (or equivalent) to bring it back up. Without that policy this
    endpoint just kills the panel — operators need that line in their
    compose to use the in-panel installer.
    """
    logger.warning("admin_plugins.restart_requested")
    # Run the kill in a delayed callback so the HTTP response can flush.
    import asyncio

    async def _delayed_exit() -> None:
        await asyncio.sleep(0.5)
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            os._exit(0)

    asyncio.create_task(_delayed_exit())
    return SimpleResponse(ok=True, requires_restart=False, message="Backend restarting…")


# ── helpers ──────────────────────────────────────────────────────


def _list_pending_wheels(installed_plugin_ids: set[str]) -> List[WheelFileInfo]:
    """Wheels on disk that don't have a matching license row.

    Useful UI hint: the operator dropped a wheel via volume mount but
    forgot the JWT. We show it as pending so they can attach a license
    without re-uploading the file.
    """
    out: List[WheelFileInfo] = []
    # We can't infer the plugin_id from a wheel filename without
    # importing it. Skip wheels whose package name maps to a known
    # plugin via convention; keep the rest as "pending".
    for wheel in plugin_installer.list_wheel_files():
        meta = plugin_installer.parse_wheel_name(wheel.name)
        if meta is None:
            continue
        # Convention: pip package ``rwa-plugin-<id>`` ↔ plugin id ``<id>``.
        guessed_id = meta.package_name.removeprefix("rwa-plugin-").replace("-", "_")
        if guessed_id in installed_plugin_ids:
            continue
        out.append(
            WheelFileInfo(
                filename=wheel.name,
                package_name=meta.package_name,
                version=meta.version,
            )
        )
    return out
