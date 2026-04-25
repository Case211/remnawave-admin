"""Plugin metadata API.

Lists plugins that were registered with the panel at startup. The frontend
uses this to render plugin-contributed sidebar entries and to know which
license states require a "buy/renew" banner.

The actual plugin endpoints live under ``/api/v2/plugins/{id}/...`` and are
mounted by ``web.backend.core.plugins.register``.
"""
from __future__ import annotations

import logging
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from web.backend.api.deps import AdminUser, get_current_admin
from web.backend.core.plugins import loaded_plugins

logger = logging.getLogger(__name__)
router = APIRouter()


class PluginNavEntry(BaseModel):
    path: str
    label_i18n: str
    icon: str
    permission: Optional[List[str]] = None  # ["resource", "action"] tuple flattened
    section_i18n: Optional[str] = None


class PluginInfo(BaseModel):
    id: str
    name: str
    version: str
    license_state: Literal["valid", "expired", "missing", "not_required"]
    api_prefix: str
    navigation: List[PluginNavEntry]


@router.get("", response_model=List[PluginInfo])
async def list_plugins(_: AdminUser = Depends(get_current_admin)) -> List[PluginInfo]:
    """List plugins registered in this panel instance.

    Auth-only: any logged-in admin can see the list. Per-plugin permissions
    are still enforced by the plugin routers themselves.
    """
    out: List[PluginInfo] = []
    for m in loaded_plugins():
        out.append(
            PluginInfo(
                id=m.id,
                name=m.name,
                version=m.version,
                license_state=m.license_state,
                api_prefix=f"/api/v2/plugins/{m.id}",
                navigation=[
                    PluginNavEntry(
                        path=n.path,
                        label_i18n=n.label_i18n,
                        icon=n.icon,
                        permission=list(n.permission) if n.permission else None,
                        section_i18n=n.section_i18n,
                    )
                    for n in m.navigation
                ],
            )
        )
    return out
