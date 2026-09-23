"""Шейпер клиентов ноды: настройки живут в панели, работает агент.

У каждой ноды свои настройки — таблица node_shapers. Агенту они уходят
командой set_shaper при сохранении и при каждом его подключении: программа
eBPF и правила tc не переживают перезагрузку ноды, а новый процесс агента
о прежних настройках не помнит.

Ответ агента — не «принято», а состояние: встал ли шейпер на самом деле и
что стало с корнем интерфейса. Панель хранит его и показывает как есть.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from shared.db_schema import NODE_SHAPERS_TABLE, NODES_TABLE

logger = logging.getLogger(__name__)

#: По этой метке в ответе агента панель узнаёт результат set_shaper
COMMAND_ID = "shaper"
#: Команду понимает агент начиная с этой версии
MIN_AGENT_VERSION = (1, 9, 0)

#: Что окно предлагает на ноде, где шейпер ещё не настраивали
DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "ports": [],
    "down_kbit": 50_000,
    "up_kbit": 50_000,
    "penalty": {"enabled": False, "mb": 2048, "window_sec": 300, "kbit": 10_000, "minutes": 15},
}

_LOOPBACK = {"127.0.0.1", "::1", "localhost"}

_COLUMNS = (
    "enabled, ports, down_kbit, up_kbit, penalty_enabled, penalty_mb, "
    "penalty_window_sec, penalty_kbit, penalty_minutes, status, status_at, "
    "updated_at, updated_by"
)


def _json(value):
    return json.loads(value) if isinstance(value, str) else value


def _iso(value) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _row_to_settings(row) -> Dict[str, Any]:
    return {
        "enabled": row["enabled"],
        "ports": list(_json(row["ports"]) or []),
        "down_kbit": row["down_kbit"],
        "up_kbit": row["up_kbit"],
        "penalty": {
            "enabled": row["penalty_enabled"],
            "mb": row["penalty_mb"],
            "window_sec": row["penalty_window_sec"],
            "kbit": row["penalty_kbit"],
            "minutes": row["penalty_minutes"],
        },
    }


async def load(node_uuid: str) -> Optional[Dict[str, Any]]:
    """Настройки и последнее состояние; None — на этой ноде шейпер не настраивали."""
    from shared.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {_COLUMNS} FROM {NODE_SHAPERS_TABLE} WHERE node_uuid = $1::uuid", node_uuid,
        )
    if not row:
        return None
    return {
        "settings": _row_to_settings(row),
        "status": _json(row["status"]),
        "status_at": _iso(row["status_at"]),
        "updated_at": _iso(row["updated_at"]),
        "updated_by": row["updated_by"],
    }


async def save(node_uuid: str, settings: Dict[str, Any], updated_by: str) -> None:
    """Сохранить настройки. Прежнее состояние сбрасывается: оно было про старые."""
    from shared.database import db_service

    penalty = settings["penalty"]
    async with db_service.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO {NODE_SHAPERS_TABLE} (
                node_uuid, enabled, ports, down_kbit, up_kbit, penalty_enabled,
                penalty_mb, penalty_window_sec, penalty_kbit, penalty_minutes,
                status, status_at, updated_at, updated_by
            ) VALUES ($1::uuid, $2, $3::jsonb, $4, $5, $6, $7, $8, $9, $10, NULL, NULL, NOW(), $11)
            ON CONFLICT (node_uuid) DO UPDATE SET
                enabled = EXCLUDED.enabled, ports = EXCLUDED.ports,
                down_kbit = EXCLUDED.down_kbit, up_kbit = EXCLUDED.up_kbit,
                penalty_enabled = EXCLUDED.penalty_enabled, penalty_mb = EXCLUDED.penalty_mb,
                penalty_window_sec = EXCLUDED.penalty_window_sec,
                penalty_kbit = EXCLUDED.penalty_kbit, penalty_minutes = EXCLUDED.penalty_minutes,
                status = NULL, status_at = NULL,
                updated_at = NOW(), updated_by = EXCLUDED.updated_by
            """,
            node_uuid,
            settings["enabled"],
            json.dumps(list(settings["ports"])),
            settings["down_kbit"],
            settings["up_kbit"],
            penalty["enabled"],
            penalty["mb"],
            penalty["window_sec"],
            penalty["kbit"],
            penalty["minutes"],
            updated_by,
        )


def build_command(settings: Dict[str, Any]) -> Dict[str, Any]:
    """Тело команды агенту — ровно то, что разбирает node-agent/src/shaper.py."""
    command: Dict[str, Any] = {"type": "set_shaper", "command_id": COMMAND_ID, "enabled": False}
    if not settings["enabled"]:
        return command
    penalty = settings["penalty"]
    command.update({
        "enabled": True,
        "ports": list(settings["ports"]),
        "down_kbit": settings["down_kbit"],
        "up_kbit": settings["up_kbit"],
        "penalty": dict(penalty) if penalty["enabled"] else {"enabled": False},
    })
    return command


def version_tuple(version: Optional[str]) -> Tuple[int, ...]:
    parts = []
    for chunk in str(version or "").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def supports(version: Optional[str]) -> bool:
    """Понимает ли агент команду. Версия неизвестна — считаем, что нет."""
    parsed = version_tuple(version)
    return bool(parsed) and parsed >= MIN_AGENT_VERSION


async def agent_info(node_uuid: str) -> Tuple[Optional[str], Optional[str]]:
    """Токен агента (для подписи) и его версия из последнего отчёта."""
    from shared.database import db_service

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT agent_token, agent_version FROM {NODES_TABLE} WHERE uuid = $1::uuid", node_uuid,
        )
    if not row:
        return None, None
    return row["agent_token"], row["agent_version"]


async def push(node_uuid: str, settings: Dict[str, Any], token: Optional[str] = None) -> bool:
    """Отправить настройки агенту. False — агент не подключён или без токена.

    Версию не проверяем: сразу после обновления агента панель ещё помнит
    старую, а старый агент незнакомую команду просто отбросит.
    """
    from web.backend.core.agent_hmac import sign_command_with_ts
    from web.backend.core.agent_manager import agent_manager

    if not agent_manager.is_connected(node_uuid):
        return False
    if token is None:
        token, _ = await agent_info(node_uuid)
    if not token:
        return False
    payload, signature = sign_command_with_ts(build_command(settings), token)
    payload["_sig"] = signature
    return await agent_manager.send_command(node_uuid, payload)


async def push_on_connect(node_uuid: str, token: str) -> None:
    """Агент подключился — вернуть ему настройки. Ноды без шейпера не трогаем."""
    stored = await load(node_uuid)
    if stored is None:
        return
    await push(node_uuid, stored["settings"], token)


async def store_result(node_uuid: str, msg: Dict[str, Any]) -> None:
    """Сохранить ответ агента на set_shaper."""
    from shared.database import db_service

    output = msg.get("output") or ""
    try:
        state = json.loads(output)
        if not isinstance(state, dict):
            raise ValueError("not an object")
    except ValueError:
        # Старый или сломанный агент — сохраняем как есть, чтобы было видно
        state = {"active": False, "error": output[-500:] or str(msg.get("status") or "unknown")}

    async with db_service.acquire() as conn:
        await conn.execute(
            f"UPDATE {NODE_SHAPERS_TABLE} SET status = $2::jsonb, status_at = NOW() "
            "WHERE node_uuid = $1::uuid",
            node_uuid,
            json.dumps(state, ensure_ascii=False),
        )
    if not state.get("active") and state.get("enabled", True):
        logger.warning("Shaper on %s is not active: %s", node_uuid, state.get("error"))


def inbound_ports(node: Dict[str, Any]) -> List[int]:
    """Порты inbound'ов ноды, которые слушают снаружи.

    Локальные (127.0.0.1 за nginx моста через CDN и подобные) не годятся:
    клиенты приходят не на них.
    """
    profile = node.get("configProfile") or {}
    ports = set()
    for inbound in profile.get("activeInbounds") or []:
        raw = inbound.get("rawInbound") or {}
        listen = str(raw.get("listen") or "0.0.0.0").strip().lower()
        port = raw.get("port", inbound.get("port"))
        if listen in _LOOPBACK or not isinstance(port, int):
            continue
        if 0 < port < 65536:
            ports.add(port)
    return sorted(ports)


async def suggest_ports(node_uuid: str) -> List[int]:
    """Порты для подстановки в окно; панель недоступна — пусто, введут руками."""
    try:
        from shared.api_client import api_client

        result = await api_client.get_node(node_uuid)
        node = result.get("response", result) if isinstance(result, dict) else {}
        return inbound_ports(node or {})
    except Exception:
        logger.debug("shaper: не удалось получить inbound'ы ноды %s", node_uuid, exc_info=True)
        return []
