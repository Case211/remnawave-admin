"""Smoke noop plugin used to validate the plugin loader end-to-end.

Activate with::

    RWA_DEV_PLUGINS=scripts.plugin_noop:manifest

Then ``GET /api/v2/plugins`` should list ``id=noop``, and
``GET /api/v2/plugins/noop/ping`` should return ``{"pong": true}``.

This file lives in the open-source repo only as a developer aid — real
plugins ship as separate pip packages with an ``rwa.plugin`` entry point.
"""
from __future__ import annotations

from fastapi import APIRouter

from web.backend.core.plugins import NavEntry, PluginManifest


def _build_router() -> APIRouter:
    r = APIRouter()

    @r.get("/ping")
    async def ping() -> dict:
        return {"pong": True, "plugin": "noop"}

    return r


def manifest() -> PluginManifest:
    return PluginManifest(
        id="noop",
        name="Noop Plugin (dev smoke)",
        version="0.0.1",
        license_state="not_required",
        router=_build_router(),
        navigation=[
            NavEntry(
                path="/plugins/noop",
                label_i18n="plugins.noop.nav",
                icon="Sparkles",
                section_i18n="nav.sections.plugins",
            ),
        ],
        rbac_resources={"noop": ["view"]},
    )
