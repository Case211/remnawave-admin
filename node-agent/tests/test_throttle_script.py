"""Мягкая блокировка на ноде: персональные лимиты через шейпер.

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

from src import shaper
from src.command_runner import CommandRunner

APPLIED = ("IFACE=ens3\nROOT=kept:fq\nPERSONAL=1\nACTIVE=1\n", 0)


def runner(result=APPLIED):
    r = CommandRunner.__new__(CommandRunner)
    r._settings = MagicMock(host_mode=False)
    r._shaper_general = shaper.DISABLED
    r._shaper_personal = {}
    r._shaper_loaded = False
    r._run_hostnet = AsyncMock(return_value=result)
    r._send = AsyncMock()
    return r


def rule(ip, kbit=1024):
    return {"ip": ip, "rate_kbit": kbit}


class TestPersonalRules:
    def test_ipv4_and_ipv6_are_both_accepted(self):
        personal, skipped = shaper.parse_personal([rule("1.2.3.4"), rule("2001:db8::1", 512)])
        assert personal == {"1.2.3.4": 1024, "2001:db8::1": 512}
        assert skipped == 0

    def test_zero_means_no_limit_and_is_left_out(self):
        personal, skipped = shaper.parse_personal([rule("1.2.3.4", 0)])
        assert personal == {} and skipped == 1

    def test_duplicate_address_takes_the_stricter_rate(self):
        """За одним адресом двое урезанных — действует меньшая скорость."""
        personal, _ = shaper.parse_personal([rule("1.2.3.4", 2048), rule("1.2.3.4", 512)])
        assert personal == {"1.2.3.4": 512}

    def test_shell_injection_attempt_is_dropped(self):
        personal, skipped = shaper.parse_personal([rule("1.2.3.4; rm -rf /"), rule("8.8.8.8")])
        assert personal == {"8.8.8.8": 1024} and skipped == 1

    def test_malformed_entries_do_not_break_the_batch(self):
        personal, skipped = shaper.parse_personal(["not-a-dict", {"rate_kbit": 1024}, rule("9.9.9.9", 2048)])
        assert personal == {"9.9.9.9": 2048} and skipped == 2

    def test_ipv4_key_is_the_mapped_ipv6_form(self):
        """Программа кладёт IPv4 в ключ как ::ffff:a.b.c.d — агент обязан так же."""
        assert shaper.client_key("1.2.3.4") == bytes(10) + b"\xff\xff" + bytes([1, 2, 3, 4])
        assert len(shaper.client_key("2001:db8::1")) == 16


class TestScripts:
    def test_personal_limits_go_into_the_map_on_full_apply(self):
        script = shaper.build_apply_script(shaper.DISABLED, {"1.2.3.4": 1024})
        key = " ".join(f"{b:02x}" for b in shaper.client_key("1.2.3.4"))
        assert f"rws_personal key hex {key}" in script
        # Общий шейпер выключен — портов в карте нет, режутся только персональные
        assert "rws_ports key" not in script

    def test_legacy_layouts_are_cleaned_before_the_root_decision(self):
        script = shaper.build_apply_script(shaper.DISABLED, {"1.2.3.4": 1024})
        assert script.index("htb 40: parent 1:4") < script.index("ROOT=$(tc qdisc show")
        assert f"ip link del {shaper.LEGACY_IFB}" in script
        deletions = [line for line in script.splitlines() if "tc filter del" in line]
        assert all("pref" in line for line in deletions)

    def test_incremental_update_never_reloads_the_program(self):
        """Перезагрузка обнулила бы штраф качальщиков при каждой смене адреса урезанного."""
        script = shaper.build_personal_update_script({"5.6.7.8": 512}, ["1.2.3.4"])
        assert "loadall" not in script and "tc filter" not in script
        assert "rws_personal key hex" in script
        assert "map delete pinned" in script
        assert f"exit {shaper.RELOAD_EXIT}" in script


class TestSyncHandler:
    @pytest.mark.asyncio
    async def test_first_rules_install_the_program(self):
        r = runner()
        await r._sync_throttled_ips({"rules": [rule("1.2.3.4")]})

        script = r._run_hostnet.await_args.args[0]
        assert "bpftool prog loadall" in script
        assert r._shaper_loaded is True
        assert r._shaper_personal == {"1.2.3.4": 1024}

    @pytest.mark.asyncio
    async def test_changed_rules_update_the_map_in_place(self):
        r = runner()
        r._shaper_loaded = True
        r._shaper_personal = {"1.2.3.4": 1024}
        r._run_hostnet = AsyncMock(return_value=("UPDATED=1\n", 0))

        await r._sync_throttled_ips({"rules": [rule("5.6.7.8")]})

        script = r._run_hostnet.await_args.args[0]
        assert "loadall" not in script
        assert "map delete pinned" in script
        assert r._shaper_personal == {"5.6.7.8": 1024}

    @pytest.mark.asyncio
    async def test_same_rules_touch_nothing(self):
        r = runner()
        r._shaper_loaded = True
        r._shaper_personal = {"1.2.3.4": 1024}

        await r._sync_throttled_ips({"rules": [rule("1.2.3.4")]})

        r._run_hostnet.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_missing_pins_fall_back_to_full_install(self):
        """Агент перезапустился — пинов нет, ставим программу заново."""
        r = runner()
        r._shaper_loaded = True
        r._shaper_personal = {"1.2.3.4": 1024}
        r._run_hostnet = AsyncMock(side_effect=[("RELOAD=1\n", shaper.RELOAD_EXIT), APPLIED])

        await r._sync_throttled_ips({"rules": [rule("5.6.7.8")]})

        assert r._run_hostnet.await_count == 2
        assert "bpftool prog loadall" in r._run_hostnet.await_args_list[1].args[0]

    @pytest.mark.asyncio
    async def test_last_limit_lifted_removes_the_program(self):
        """Ни общего шейпера, ни персональных — ноде возвращается прежний вид."""
        r = runner(("IFACE=ens3\nROOT=restored\nACTIVE=0\n", 0))
        r._shaper_loaded = True
        r._shaper_personal = {"1.2.3.4": 1024}

        await r._sync_throttled_ips({"rules": []})

        script = r._run_hostnet.await_args.args[0]
        assert "ROOT=restored" in script and "loadall" not in script
        assert r._shaper_loaded is False

    @pytest.mark.asyncio
    async def test_general_shaper_keeps_the_program_when_personal_are_gone(self):
        r = runner(("UPDATED=1\n", 0))
        r._shaper_general = shaper.parse_config({"enabled": True, "ports": [443], "down_kbit": 10000})
        r._shaper_loaded = True
        r._shaper_personal = {"1.2.3.4": 1024}

        await r._sync_throttled_ips({"rules": []})

        script = r._run_hostnet.await_args.args[0]
        assert "map delete pinned" in script and "ROOT=restored" not in script

    @pytest.mark.asyncio
    async def test_result_is_reported_back(self):
        r = runner()
        await r._sync_throttled_ips({"command_id": "c1", "rules": [rule("9.9.9.9", 512)]})

        reply = r._send.await_args.args[0]
        assert reply["command_id"] == "c1"
        assert reply["status"] == "completed"
