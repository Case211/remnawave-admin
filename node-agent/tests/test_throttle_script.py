"""Ограничение скорости на ноде: скрипт tc и разбор входящих правил.

Гоняется в наборе агента — пакет здесь зовётся ``src`` и в одном процессе
с тестами бэкенда конкурировал бы за это имя:

    cd node-agent && python -m pytest
"""
import os
import shutil
import subprocess

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.command_runner import THROTTLE_IFB, THROTTLE_PREF, CommandRunner


def build(rules):
    return CommandRunner._build_throttle_script(rules)


def runner():
    r = CommandRunner.__new__(CommandRunner)
    r._settings = MagicMock(host_mode=False)
    r._run_shell = AsyncMock(return_value=("", 0))
    r._send = AsyncMock()
    return r


class TestThrottleScript:
    def test_root_is_touched_only_in_the_legacy_branch(self):
        """Issue #281: корень интерфейса чужой, трогать его можно лишь там,
        где стоит наша старая раскладка."""
        for rules in ([], [("1.2.3.4", 1024)]):
            lines = build(rules).splitlines()
            root_lines = [i for i, line in enumerate(lines) if 'dev "$IFACE" root' in line]
            assert len(root_lines) == 1
            assert "tc qdisc del" in lines[root_lines[0]]
            assert "htb 40: parent 1:4" in lines[root_lines[0] - 1]

    def test_empty_list_removes_only_our_own_filters(self):
        script = build([])
        deletions = [line for line in script.splitlines() if "tc filter del" in line]
        assert deletions
        # Удаление без номера приоритета снесло бы все фильтры интерфейса
        assert all(f"pref {THROTTLE_PREF}" in line for line in deletions)
        # И только если фильтры на этом приоритете ведут в наше устройство
        assert f'*"{THROTTLE_IFB}"*) tc filter del' in script
        assert "tc filter add" not in script
        assert "tc class add" not in script

    def test_device_goes_after_the_filters_that_point_to_it(self):
        """Перенаправление в пропавшее устройство ядро превращает в дроп."""
        script = build([])
        assert script.index("tc filter del") < script.index(f"ip link del {THROTTLE_IFB}")

    def test_clsact_is_removed_only_when_nothing_else_is_on_it(self):
        lines = build([]).splitlines()
        removal = next(i for i, line in enumerate(lines) if 'tc qdisc del dev "$IFACE" clsact' in line)
        guard = lines[removal - 1]
        assert '"$HAD"' in guard
        assert "egress" in guard and "ingress" in guard

    def test_rule_per_address(self):
        script = build([("1.2.3.4", 1024), ("5.6.7.8", 512)])
        assert "match ip dst 1.2.3.4/32 flowid 1:10" in script
        assert "match ip dst 5.6.7.8/32 flowid 1:11" in script
        assert "rate 1024kbit ceil 1024kbit" in script
        assert "rate 512kbit ceil 512kbit" in script
        for ip in ("1.2.3.4", "5.6.7.8"):
            assert (
                f'tc filter add dev "$IFACE" egress protocol ip pref {THROTTLE_PREF} u32 '
                f"match ip dst {ip}/32 action mirred egress redirect dev {THROTTLE_IFB}"
            ) in script

    def test_shaper_lives_in_our_device_not_on_the_interface(self):
        """Ошибиться в ширине канала нельзя, если её вообще не нужно знать."""
        script = build([("1.2.3.4", 1024)])
        assert f"tc qdisc add dev {THROTTLE_IFB} root handle 1: htb" in script
        assert 'tc qdisc add dev "$IFACE" root' not in script
        assert 'tc qdisc replace dev "$IFACE"' not in script
        assert "gbit" not in script

    def test_existing_clsact_is_reused_not_recreated(self):
        """На чужом clsact могут висеть чужие фильтры — пересоздание их снесло бы."""
        lines = build([("1.2.3.4", 1024)]).splitlines()
        add = next(i for i, line in enumerate(lines) if 'tc qdisc add dev "$IFACE" clsact' in line)
        assert any("^qdisc clsact " in line and line.startswith("if !") for line in lines[:add])

    def test_foreign_filter_on_our_priority_blocks_the_apply(self):
        script = build([("1.2.3.4", 1024)])
        assert script.index('if [ -n "$FOREIGN" ]') < script.index("tc filter add")

    def test_our_filters_run_before_auto_assigned_priorities(self):
        """Фильтры без явного приоритета получают 49152 и ниже; eBPF-программа
        там отпускает пакет вердиктом «пропустить», и дальше проверка не идёт."""
        assert 0 < THROTTLE_PREF < 49152

    def test_interface_is_taken_from_the_default_route(self):
        assert "ip route show default" in build([])

    @pytest.mark.parametrize("rules", [[], [("1.2.3.4", 1024), ("5.6.7.8", 512)]])
    def test_script_is_valid_posix_shell(self, rules):
        """На ноде скрипт исполняет /bin/sh хоста — у Ubuntu это dash."""
        shell = shutil.which("dash") or shutil.which("sh")
        if not shell:
            pytest.skip("no POSIX shell to check the syntax with")
        # Байтами, а не текстом: на Windows текстовый режим дописал бы к строкам CR
        result = subprocess.run([shell, "-n"], input=build(rules).encode(), capture_output=True)
        assert result.returncode == 0, result.stderr.decode(errors="replace")


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
        # На адрес два фильтра: перенаправление в наше устройство и в личный класс
        assert script.count("tc filter add") == 2

    @pytest.mark.asyncio
    async def test_result_is_reported_back(self):
        r = runner()
        await r._sync_throttled_ips({"command_id": "c1", "rules": [{"ip": "9.9.9.9", "rate_kbit": 512}]})

        reply = r._send.await_args.args[0]
        assert reply["command_id"] == "c1"
        assert reply["status"] == "completed"
