"""Шейпер клиентов ноды: настройки в панели, команда агенту, его ответ.

Главное здесь — контракт: команду, которую собирает панель, агент обязан
разобрать без ошибок. Поэтому тест берёт разбор прямо из кода агента.
"""
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# Агент живёт отдельным пакетом и в панель не импортируется — добавляем
# его каталог в путь, как это делает сам агент при запуске.
AGENT_ROOT = Path(__file__).resolve().parents[3] / "node-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from src import shaper as agent_shaper  # noqa: E402

from web.backend.api.v2.node_shaper import ShaperIn  # noqa: E402
from web.backend.core import shaper_rollout  # noqa: E402

NODE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"

ENABLED = {
    "enabled": True,
    "ports": [8443, 443, 443],
    "down_kbit": 50000,
    "up_kbit": 20000,
    "penalty": {"enabled": True, "mb": 2048, "window_sec": 300, "kbit": 10000, "minutes": 15},
}


class TestValidation:
    def test_ports_are_deduplicated_and_sorted(self):
        assert ShaperIn(**ENABLED).ports == [443, 8443]

    def test_enabled_without_ports_is_rejected(self):
        """Без портов под потолок попали бы соединения самой ноды в интернет."""
        with pytest.raises(ValidationError, match="inbound port"):
            ShaperIn(**{**ENABLED, "ports": []})

    def test_enabled_without_any_limit_is_rejected(self):
        with pytest.raises(ValidationError, match="speed cap"):
            ShaperIn(**{**ENABLED, "down_kbit": 0, "up_kbit": 0, "penalty": {"enabled": False}})

    def test_disabled_needs_nothing(self):
        assert ShaperIn(enabled=False).ports == []

    @pytest.mark.parametrize("ports", [[0], [65536], [-1]])
    def test_out_of_range_port_is_rejected(self, ports):
        with pytest.raises(ValidationError):
            ShaperIn(**{**ENABLED, "ports": ports})

    def test_incomplete_penalty_is_rejected(self):
        with pytest.raises(ValidationError, match="penalty.kbit"):
            ShaperIn(**{**ENABLED, "penalty": {**ENABLED["penalty"], "kbit": 0}})


class TestContractWithAgent:
    def test_enabled_command_is_accepted_by_the_agent(self):
        command = shaper_rollout.build_command(ShaperIn(**ENABLED).model_dump())
        cfg = agent_shaper.parse_config(command)
        assert cfg.enabled
        assert cfg.ports == (443, 8443)
        assert (cfg.down_kbit, cfg.up_kbit) == (50000, 20000)
        assert (cfg.penalty_mb, cfg.penalty_window_sec, cfg.penalty_kbit, cfg.penalty_minutes) == (
            2048, 300, 10000, 15)

    def test_disabled_command_is_accepted_by_the_agent(self):
        command = shaper_rollout.build_command(ShaperIn(enabled=False).model_dump())
        assert agent_shaper.parse_config(command).enabled is False

    def test_disabled_penalty_is_not_sent_half_filled(self):
        data = {**ENABLED, "penalty": {"enabled": False, "mb": 5}}
        command = shaper_rollout.build_command(ShaperIn(**data).model_dump())
        assert command["penalty"] == {"enabled": False}
        assert agent_shaper.parse_config(command).penalty_mb == 0

    def test_command_type_and_id(self):
        from src.command_runner import ALLOWED_COMMAND_TYPES

        command = shaper_rollout.build_command(ShaperIn(**ENABLED).model_dump())
        assert command["type"] in ALLOWED_COMMAND_TYPES
        assert command["command_id"] == shaper_rollout.COMMAND_ID


class TestAgentVersion:
    @pytest.mark.parametrize("version,ok", [
        ("1.9.0", True), ("1.10.2", True), ("2.0.0-rc1", True),
        ("1.8.3", False), ("1.8", False), (None, False), ("", False), ("garbage", False),
    ])
    def test_supports(self, version, ok):
        assert shaper_rollout.supports(version) is ok


class TestInboundPorts:
    def test_only_externally_listening_inbounds(self):
        node = {"configProfile": {"activeInbounds": [
            {"port": 443, "rawInbound": {"port": 443, "listen": "0.0.0.0"}},
            {"port": 8443, "rawInbound": {"port": 8443}},
            {"port": 4443, "rawInbound": {"port": 4443, "listen": "127.0.0.1"}},
            {"port": 443, "rawInbound": {"port": 443, "listen": "::"}},
        ]}}
        assert shaper_rollout.inbound_ports(node) == [443, 8443]

    def test_node_without_profile(self):
        assert shaper_rollout.inbound_ports({}) == []


def _db(conn):
    db = MagicMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db.acquire = MagicMock(return_value=cm)
    return db


class TestAgentAnswer:
    @pytest.mark.asyncio
    async def test_state_is_stored_as_reported(self):
        conn = AsyncMock()
        state = {"enabled": True, "active": True, "root": "installed:fq_codel", "error": None}
        with patch("shared.database.db_service", _db(conn)):
            await shaper_rollout.store_result(NODE, {"command_id": "shaper", "output": json.dumps(state)})

        args = conn.execute.await_args.args
        assert args[1] == NODE
        assert json.loads(args[2]) == state

    @pytest.mark.asyncio
    async def test_garbage_answer_is_kept_visible(self):
        """Старый или сломанный агент — показываем, что пришло, а не молчим."""
        conn = AsyncMock()
        with patch("shared.database.db_service", _db(conn)):
            await shaper_rollout.store_result(NODE, {"command_id": "shaper", "status": "error",
                                                     "output": "Unknown command"})

        stored = json.loads(conn.execute.await_args.args[2])
        assert stored == {"active": False, "error": "Unknown command"}


class TestPush:
    @pytest.mark.asyncio
    async def test_offline_agent_is_not_bothered(self):
        mgr = MagicMock()
        mgr.is_connected.return_value = False
        mgr.send_command = AsyncMock()
        with patch("web.backend.core.agent_manager.agent_manager", mgr):
            sent = await shaper_rollout.push(NODE, ShaperIn(**ENABLED).model_dump(), token="tok")

        assert sent is False
        mgr.send_command.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_payload_is_signed_and_flat(self):
        mgr = MagicMock()
        mgr.is_connected.return_value = True
        mgr.send_command = AsyncMock(return_value=True)
        with patch("web.backend.core.agent_manager.agent_manager", mgr):
            sent = await shaper_rollout.push(NODE, ShaperIn(**ENABLED).model_dump(), token="tok")

        assert sent is True
        payload = mgr.send_command.await_args.args[1]
        assert payload["type"] == "set_shaper"
        assert "_sig" in payload and "_ts" in payload

    @pytest.mark.asyncio
    async def test_node_without_shaper_is_skipped_on_connect(self):
        with patch.object(shaper_rollout, "load", AsyncMock(return_value=None)), \
             patch.object(shaper_rollout, "push", AsyncMock()) as push:
            await shaper_rollout.push_on_connect(NODE, "tok")
        push.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_configured_node_gets_its_settings_on_connect(self):
        stored = {"settings": ShaperIn(**ENABLED).model_dump()}
        with patch.object(shaper_rollout, "load", AsyncMock(return_value=stored)), \
             patch.object(shaper_rollout, "push", AsyncMock()) as push:
            await shaper_rollout.push_on_connect(NODE, "tok")
        push.assert_awaited_once_with(NODE, stored["settings"], "tok")
