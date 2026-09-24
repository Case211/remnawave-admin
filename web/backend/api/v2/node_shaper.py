"""Шейпер клиентов ноды: окно настроек в карточке ноды.

Потолок скорости на каждый адрес клиента и режим штрафа для тех, кто за
окно прокачал больше порога. Настройки у каждой ноды свои; применяет их
агент, а панель показывает его ответ — встал ли шейпер на самом деле.
"""
import json
import logging
from typing import List

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field, field_validator, model_validator

from web.backend.api.deps import AdminUser, get_client_ip, require_permission
from web.backend.core import shaper_rollout
from web.backend.core.audit import write_audit_log
from web.backend.core.errors import E, api_error
from web.backend.core.rbac import check_access

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_KBIT = 100_000_000  # 100 Гбит/с — выше только опечатка


class PenaltyIn(BaseModel):
    enabled: bool = False
    mb: int = Field(0, ge=0, le=10_000_000)
    window_sec: int = Field(0, ge=0, le=86_400)
    kbit: int = Field(0, ge=0, le=MAX_KBIT)
    minutes: int = Field(0, ge=0, le=10_080)

    @model_validator(mode="after")
    def _complete_when_enabled(self):
        if self.enabled:
            if self.mb < 1:
                raise ValueError("penalty.mb must be at least 1")
            if self.window_sec < 10:
                raise ValueError("penalty.window_sec must be at least 10")
            if self.kbit < 64:
                raise ValueError("penalty.kbit must be at least 64")
            if self.minutes < 1:
                raise ValueError("penalty.minutes must be at least 1")
        return self


class ShaperIn(BaseModel):
    enabled: bool
    ports: List[int] = Field(default_factory=list, max_length=64)
    down_kbit: int = Field(0, ge=0, le=MAX_KBIT)
    up_kbit: int = Field(0, ge=0, le=MAX_KBIT)
    penalty: PenaltyIn = Field(default_factory=PenaltyIn)

    @field_validator("ports")
    @classmethod
    def _ports(cls, ports: List[int]) -> List[int]:
        for port in ports:
            if not 0 < port < 65536:
                raise ValueError("ports must be between 1 and 65535")
        return sorted(set(ports))

    @model_validator(mode="after")
    def _meaningful_when_enabled(self):
        if self.enabled:
            # Без портов под потолок попали бы соединения самой ноды в интернет
            if not self.ports:
                raise ValueError("at least one inbound port is required")
            if not (self.down_kbit or self.up_kbit or self.penalty.enabled):
                raise ValueError("set a speed cap or enable the penalty mode")
        return self


async def _agent_state(node_uuid: str) -> dict:
    from web.backend.core.agent_manager import agent_manager

    _, version = await shaper_rollout.agent_info(node_uuid)
    return {
        "connected": agent_manager.is_connected(node_uuid),
        "version": version,
        "supported": shaper_rollout.supports(version),
        "min_version": ".".join(str(part) for part in shaper_rollout.MIN_AGENT_VERSION),
    }


@router.get("/{node_uuid}/shaper")
async def get_shaper(
    node_uuid: str,
    admin: AdminUser = Depends(require_permission("nodes", "view")),
):
    """Настройки шейпера ноды, ответ агента и подсказка портов."""
    if not await check_access(admin, "node", node_uuid, "view"):
        raise api_error(403, E.FORBIDDEN)
    try:
        stored = await shaper_rollout.load(node_uuid)
        agent = await _agent_state(node_uuid)
    except Exception as e:
        logger.error("shaper: не удалось прочитать настройки %s: %s", node_uuid, e)
        raise api_error(503, E.DB_UNAVAILABLE)

    suggested = await shaper_rollout.suggest_ports(node_uuid)
    if stored is None:
        settings = {**shaper_rollout.DEFAULTS, "ports": suggested}
        stored = {"settings": settings, "status": None, "status_at": None,
                  "updated_at": None, "updated_by": None}

    try:
        penalties = await shaper_rollout.recent_penalties(node_uuid)
    except Exception as e:
        logger.debug("shaper: история штрафов %s недоступна: %s", node_uuid, e)
        penalties = []

    return {
        **stored,
        "penalties": penalties,
        "configured": stored["updated_at"] is not None,
        "agent": agent,
        "suggested_ports": suggested,
    }


@router.put("/{node_uuid}/shaper")
async def put_shaper(
    node_uuid: str,
    data: ShaperIn,
    request: Request,
    admin: AdminUser = Depends(require_permission("nodes", "edit")),
):
    """Сохранить настройки и отправить агенту."""
    if not await check_access(admin, "node", node_uuid, "edit"):
        raise api_error(403, E.FORBIDDEN)

    settings = data.model_dump()
    try:
        await shaper_rollout.save(node_uuid, settings, admin.username)
    except Exception as e:
        logger.error("shaper: не удалось сохранить настройки %s: %s", node_uuid, e)
        raise api_error(503, E.DB_UNAVAILABLE)

    try:
        pushed = await shaper_rollout.push(node_uuid, settings)
    except Exception as e:
        logger.warning("shaper: настройки %s сохранены, но агенту не ушли: %s", node_uuid, e)
        pushed = False

    await write_audit_log(
        admin_id=admin.account_id,
        admin_username=admin.username,
        action="node.shaper.update",
        resource="nodes",
        resource_id=node_uuid,
        details=json.dumps({
            "enabled": settings["enabled"],
            "ports": settings["ports"],
            "down_kbit": settings["down_kbit"],
            "up_kbit": settings["up_kbit"],
            "penalty": settings["penalty"],
            "pushed": pushed,
        }),
        ip_address=get_client_ip(request),
    )
    return {"success": True, "pushed": pushed}
