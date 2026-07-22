"""Smoke noop plugin used to validate the plugin loader end-to-end.

Activate with::

    RWA_DEV_PLUGINS=scripts.plugin_noop:manifest

Then ``GET /api/v2/plugins`` should list ``id=noop``, and
``GET /api/v2/plugins/noop/ping`` should return ``{"pong": true}``.

This file lives in the open-source repo only as a developer aid — real
plugins ship as separate pip packages with an ``rwa.plugin`` entry point.
It doubles as the reference for manifest v2: declarative manifest +
``build(ctx)`` factory returning the router bound to the PluginContext.
"""
from __future__ import annotations

from fastapi import APIRouter

from web.backend.core.plugin_api import PluginContext
from web.backend.core.plugins import NavEntry, PluginManifest, PluginParts


def _build(ctx: PluginContext) -> PluginParts:
    r = APIRouter()

    @r.get("/ping")
    async def ping() -> dict:
        ctx.telemetry.count("ping")
        return {"pong": True, "plugin": ctx.plugin_id}

    return PluginParts(router=r)


def manifest() -> PluginManifest:
    return PluginManifest(
        id="noop",
        name="Noop Plugin (dev smoke)",
        version="0.0.2",
        billing="free",
        build=_build,
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
