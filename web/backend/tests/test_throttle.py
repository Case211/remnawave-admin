"""Раскладка ограничений скорости по нодам и рассылка агентам.

Скрипт tc и разбор правил проверяются в наборе агента
(node-agent/tests/test_throttle_script.py) — пакет агента зовётся ``src``
и в одном процессе с бэкендом конкурировал бы за это имя.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import throttle_sync

NODE = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


class TestPushThrottles:
    def setup_method(self):
        throttle_sync._pushed.clear()

    def teardown_method(self):
        throttle_sync._pushed.clear()

    @staticmethod
    def _agent_manager(connected):
        mgr = MagicMock()
        mgr.connected_nodes.return_value = list(connected)
        mgr.send_command = AsyncMock(return_value=True)
        return mgr

    @staticmethod
    def _db(rules_by_node):
        db = MagicMock()
        db.get_throttle_rules_by_node = AsyncMock(return_value=rules_by_node)
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value={"agent_token": "tok"})
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=conn)
        cm.__aexit__ = AsyncMock(return_value=False)
        db.acquire = MagicMock(return_value=cm)
        return db

    @pytest.mark.asyncio
    async def test_sends_rules_to_the_node_that_holds_the_user(self):
        db = self._db({NODE: [{"ip": "1.2.3.4", "rate_kbit": 1024}]})
        mgr = self._agent_manager([NODE])

        with patch.object(throttle_sync, "db_service", db), \
             patch("web.backend.core.agent_manager.agent_manager", mgr):
            sent = await throttle_sync.push_throttles()

        assert sent == 1
        payload = mgr.send_command.await_args.args[1]
        assert payload["type"] == "sync_throttled_ips"
        assert payload["rules"] == [{"ip": "1.2.3.4", "rate_kbit": 1024}]
        assert "_sig" in payload

    @pytest.mark.asyncio
    async def test_node_without_throttles_gets_an_empty_list(self):
        """Иначе снятое ограничение осталось бы висеть на ноде навсегда."""
        db = self._db({})
        mgr = self._agent_manager([NODE])

        with patch.object(throttle_sync, "db_service", db), \
             patch("web.backend.core.agent_manager.agent_manager", mgr):
            await throttle_sync.push_throttles()

        assert mgr.send_command.await_args.args[1]["rules"] == []

    @pytest.mark.asyncio
    async def test_unchanged_list_is_not_resent(self):
        """Применение снимает и ставит корневую дисциплину — дёргать зря нельзя."""
        db = self._db({NODE: [{"ip": "1.2.3.4", "rate_kbit": 1024}]})
        mgr = self._agent_manager([NODE])

        with patch.object(throttle_sync, "db_service", db), \
             patch("web.backend.core.agent_manager.agent_manager", mgr):
            first = await throttle_sync.push_throttles()
            second = await throttle_sync.push_throttles()

        assert (first, second) == (1, 0)
        assert mgr.send_command.await_count == 1

    @pytest.mark.asyncio
    async def test_changed_list_is_resent(self):
        db = self._db({NODE: [{"ip": "1.2.3.4", "rate_kbit": 1024}]})
        mgr = self._agent_manager([NODE])

        with patch.object(throttle_sync, "db_service", db), \
             patch("web.backend.core.agent_manager.agent_manager", mgr):
            await throttle_sync.push_throttles()
            db.get_throttle_rules_by_node.return_value = {
                NODE: [{"ip": "1.2.3.4", "rate_kbit": 512}]
            }
            again = await throttle_sync.push_throttles()

        assert again == 1
        assert mgr.send_command.await_count == 2

    @pytest.mark.asyncio
    async def test_reconnect_forces_a_resend(self):
        """Правила tc живут в ядре и не переживают перезагрузку ноды."""
        db = self._db({NODE: [{"ip": "1.2.3.4", "rate_kbit": 1024}]})
        mgr = self._agent_manager([NODE])

        with patch.object(throttle_sync, "db_service", db), \
             patch("web.backend.core.agent_manager.agent_manager", mgr):
            await throttle_sync.push_throttles()
            throttle_sync.forget_node(NODE)
            after = await throttle_sync.push_throttles()

        assert after == 1

    @pytest.mark.asyncio
    async def test_disconnected_node_is_skipped(self):
        db = self._db({NODE: [{"ip": "1.2.3.4", "rate_kbit": 1024}]})
        mgr = self._agent_manager([])

        with patch.object(throttle_sync, "db_service", db), \
             patch("web.backend.core.agent_manager.agent_manager", mgr):
            sent = await throttle_sync.push_throttles()

        assert sent == 0
        mgr.send_command.assert_not_awaited()
