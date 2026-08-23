"""Ограничение скорости на ноде: скрипт tc и разбор входящих правил.

Гоняется в наборе агента — пакет здесь зовётся ``src`` и в одном процессе
с тестами бэкенда конкурировал бы за это имя:

    cd node-agent && python -m pytest
"""
import os

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.command_runner import CommandRunner


def build(rules):
    return CommandRunner._build_throttle_script(rules)


def runner():
    r = CommandRunner.__new__(CommandRunner)
    r._settings = MagicMock(host_mode=False)
    r._run_shell = AsyncMock(return_value=("", 0))
    r._send = AsyncMock()
    return r


class TestThrottleScript:
    def test_empty_list_clears_everything(self):
        """Пустой список — снятие: иначе снятое ограничение висело бы вечно."""
        script = build([])
        assert "tc qdisc del" in script
        assert "tc class add" not in script
        assert "tc filter add" not in script

    def test_rule_per_address(self):
        script = build([("1.2.3.4", 1024), ("5.6.7.8", 512)])
        assert "match ip dst 1.2.3.4/32 flowid 40:10" in script
        assert "match ip dst 5.6.7.8/32 flowid 40:11" in script
        assert "rate 1024kbit ceil 1024kbit" in script
        assert "rate 512kbit ceil 512kbit" in script

    def test_ordinary_traffic_never_enters_the_shaper(self):
        """Ошибиться в ширине канала нельзя, если её вообще не нужно знать."""
        script = build([("1.2.3.4", 1024)])
        assert "priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0" in script
        assert "gbit" not in script
        assert "parent 1:4 handle 40: htb" in script

    def test_previous_layout_is_replaced_not_stacked(self):
        script = build([("1.2.3.4", 1024)])
        assert script.index("tc qdisc del") < script.index("tc qdisc add")

    def test_interface_is_taken_from_the_default_route(self):
        assert "ip route show default" in build([])


class TestRuleValidation:
    """Правила приходят по сети — до shell должны доходить только разобранные значения."""

    @pytest.mark.asyncio
    async def test_shell_injection_attempt_is_dropped(self):
        r = runner()
        await r._sync_throttled_ips({"rules": [
            {"ip": "1.2.3.4; rm -rf /", "rate_kbit": 1024},
            {"ip": "8.8.8.8", "rate_kbit": 1024},
        ]})

        script = r._run_shell.await_args.args[0]
        assert "rm -rf" not in script
        assert "8.8.8.8/32" in script

    @pytest.mark.asyncio
    async def test_nonpositive_rate_is_dropped(self):
        r = runner()
        await r._sync_throttled_ips({"rules": [{"ip": "8.8.8.8", "rate_kbit": 0}]})
        assert "tc filter add" not in r._run_shell.await_args.args[0]

    @pytest.mark.asyncio
    async def test_ipv6_is_skipped_rather_than_mismatched(self):
        """Фильтр под IPv6 нужен отдельный — молча резать не тот трафик хуже."""
        r = runner()
        await r._sync_throttled_ips({"rules": [{"ip": "2001:db8::1", "rate_kbit": 1024}]})
        assert "tc filter add" not in r._run_shell.await_args.args[0]

    @pytest.mark.asyncio
    async def test_malformed_entries_do_not_break_the_batch(self):
        r = runner()
        await r._sync_throttled_ips({"rules": [
            "not-a-dict",
            {"rate_kbit": 1024},
            {"ip": "9.9.9.9", "rate_kbit": 2048},
        ]})

        script = r._run_shell.await_args.args[0]
        assert "9.9.9.9/32" in script
        # На адрес приходится два фильтра: на полосу ограничителя и в его класс
        assert script.count("tc filter add") == 2

    @pytest.mark.asyncio
    async def test_result_is_reported_back(self):
        r = runner()
        await r._sync_throttled_ips({"command_id": "c1", "rules": [{"ip": "9.9.9.9", "rate_kbit": 512}]})

        reply = r._send.await_args.args[0]
        assert reply["command_id"] == "c1"
        assert reply["status"] == "completed"
