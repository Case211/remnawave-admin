"""Шейпер клиентов: разбор команды, раскладка карты и скрипты tc/bpftool.

Живая проверка программы eBPF идёт стендом на ядре; здесь — то, что
агент собирает из команды панели, и правила «снимаем только своё».

    cd node-agent && python -m pytest
"""
import json
import os
import shutil
import struct
import subprocess

os.environ.setdefault("AGENT_NODE_UUID", "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
os.environ.setdefault("AGENT_COLLECTOR_URL", "http://collector.test")
os.environ.setdefault("AGENT_AUTH_TOKEN", "token")

from unittest.mock import AsyncMock, MagicMock

import pytest

from src import shaper
from src.command_runner import ALLOWED_COMMAND_TYPES, CommandRunner

BASE = {"enabled": True, "ports": [443], "down_kbit": 10000, "up_kbit": 5000}


def cfg(**overrides):
    return shaper.parse_config({**BASE, **overrides})


class TestParseConfig:
    def test_disabled_needs_nothing_else(self):
        assert shaper.parse_config({"enabled": False, "ports": "garbage"}).enabled is False

    def test_ports_are_deduplicated_and_sorted(self):
        assert cfg(ports=[8443, 443, 443]).ports == (443, 8443)

    @pytest.mark.parametrize("ports", [[], [0], [70000], ["443; rm -rf /"], [True], "443"])
    def test_bad_ports_are_rejected(self, ports):
        with pytest.raises(ValueError):
            cfg(ports=ports)

    def test_empty_ports_would_shape_the_node_itself(self):
        """Без портов под потолок попали бы соединения ноды в интернет."""
        with pytest.raises(ValueError, match="inbound port"):
            cfg(ports=[])

    def test_too_many_ports_do_not_fit_the_map(self):
        with pytest.raises(ValueError):
            cfg(ports=list(range(1000, 1000 + shaper.MAX_PORTS + 1)))

    def test_something_must_be_limited(self):
        with pytest.raises(ValueError, match="nothing to shape"):
            cfg(down_kbit=0, up_kbit=0)

    def test_penalty_alone_is_enough(self):
        c = cfg(down_kbit=0, up_kbit=0,
                penalty={"enabled": True, "mb": 500, "window_sec": 60, "kbit": 5000, "minutes": 10})
        assert (c.penalty_mb, c.penalty_window_sec, c.penalty_kbit, c.penalty_minutes) == (500, 60, 5000, 10)

    def test_disabled_penalty_ignores_its_fields(self):
        c = cfg(penalty={"enabled": False, "mb": "junk"})
        assert c.penalty_mb == 0

    @pytest.mark.parametrize("penalty", [
        {"enabled": True, "mb": 0, "window_sec": 60, "kbit": 5000, "minutes": 10},
        {"enabled": True, "mb": 100, "window_sec": 1, "kbit": 5000, "minutes": 10},
        {"enabled": True, "mb": 100, "window_sec": 60, "kbit": 1, "minutes": 10},
        {"enabled": True, "mb": 100, "window_sec": 60, "kbit": 5000},
    ])
    def test_bad_penalty_is_rejected(self, penalty):
        with pytest.raises(ValueError):
            cfg(penalty=penalty)

    def test_rates_are_bounded(self):
        with pytest.raises(ValueError):
            cfg(down_kbit=-1)
        with pytest.raises(ValueError):
            cfg(up_kbit=shaper.MAX_KBIT + 1)


class TestEncoding:
    def test_cfg_layout_matches_the_bpf_struct(self):
        """struct shaper_cfg — девять __u64 в этом порядке."""
        c = cfg(penalty={"enabled": True, "mb": 100, "window_sec": 60, "kbit": 2000, "minutes": 5})
        fields = struct.unpack("<9Q", shaper.encode_cfg(c, 14))
        assert fields == (
            14,
            10000 * 125,              # кбит/с → байт/с
            5000 * 125,
            shaper.HORIZON_NS,
            shaper.BURST_NS,
            100 * 1024 * 1024,
            60 * 10**9,
            2000 * 125,
            5 * 60 * 10**9,
        )

    def test_port_key_is_little_endian_u16(self):
        script = shaper.build_apply_script(cfg(ports=[443]))
        assert "rws_ports key hex bb 01 value hex 01" in script


class TestApplyScript:
    def test_previous_install_is_removed_only_if_it_is_ours(self):
        script = shaper.build_apply_script(cfg())
        assert f"*rws_*) tc filter del dev \"$IFACE\" $HOOK pref {shaper.SHAPER_PREF}" in script
        assert "is taken by another tool\"; exit 1" in script
        # Удаление без номера приоритета снесло бы все фильтры интерфейса
        deletions = [line for line in script.splitlines() if "tc filter del" in line]
        assert all(f"pref {shaper.SHAPER_PREF}" in line or f"pref {shaper.LEGACY_IFB_PREF}" in line
                   for line in deletions)

    def test_fq_is_installed_only_over_the_kernel_default(self):
        script = shaper.build_apply_script(cfg())
        lines = script.splitlines()
        installs = [i for i, line in enumerate(lines) if "tc qdisc replace" in line and "root" in line]
        assert installs
        guard = next(i for i, line in enumerate(lines) if 'elif [ "$HANDLE" = "0:" ]' in line)
        foreign = next(i for i, line in enumerate(lines) if "ROOT=foreign" in line)
        assert all(guard < i < foreign for i in installs)
        assert all(f"handle {shaper.ROOT_HANDLE}" in lines[i] for i in installs)

    def test_both_hooks_get_the_program(self):
        script = shaper.build_apply_script(cfg())
        assert f"egress pref {shaper.SHAPER_PREF} bpf da pinned {shaper.PIN_DIR}/progs/rws_egress" in script
        assert f"ingress pref {shaper.SHAPER_PREF} bpf da pinned {shaper.PIN_DIR}/progs/rws_ingress" in script

    def test_maps_are_configured_before_the_program_is_attached(self):
        script = shaper.build_apply_script(cfg())
        assert script.index("rws_cfg key") < script.index("bpf da pinned")
        assert script.index("rws_ports key") < script.index("bpf da pinned")

    def test_existing_clsact_is_reused(self):
        lines = shaper.build_apply_script(cfg()).splitlines()
        add = next(i for i, line in enumerate(lines) if 'tc qdisc add dev "$IFACE" clsact' in line)
        assert any("^qdisc clsact " in line and line.startswith("if !") for line in lines[:add])

    def test_l2_header_follows_the_link_type(self):
        script = shaper.build_apply_script(cfg())
        eth = " ".join(f"{b:02x}" for b in shaper.encode_cfg(cfg(), 14))
        l3 = " ".join(f"{b:02x}" for b in shaper.encode_cfg(cfg(), 0))
        assert f'CFG="{eth}"' in script and f'CFG="{l3}"' in script
        assert "link/ether" in script


class TestDisableScript:
    def test_foreign_filters_do_not_fail_the_removal(self):
        script = shaper.build_disable_script()
        assert 'echo "FOREIGN=$HOOK"' in script
        assert "exit 1 ;;" not in script

    def test_root_is_removed_only_when_it_carries_our_mark(self):
        lines = shaper.build_disable_script().splitlines()
        removals = [i for i, line in enumerate(lines) if 'tc qdisc del dev "$IFACE" root' in line]
        # Каждое снятие корня — под своей меткой: наш fq или старая раскладка агента
        assert removals
        for i in removals:
            guard = lines[i - 1]
            assert f'= "{shaper.ROOT_HANDLE}" ]' in guard or "htb 40: parent 1:4" in guard

    def test_clsact_is_removed_only_when_nothing_else_is_on_it(self):
        lines = shaper.build_disable_script().splitlines()
        removal = next(i for i, line in enumerate(lines) if 'tc qdisc del dev "$IFACE" clsact' in line)
        guard = lines[removal - 1]
        assert '"$HAD"' in guard and "egress" in guard and "ingress" in guard


@pytest.mark.parametrize("script", [
    shaper.build_apply_script(cfg(ports=[443, 8443],
                                  penalty={"enabled": True, "mb": 1, "window_sec": 10, "kbit": 64, "minutes": 1})),
    shaper.build_disable_script(),
])
def test_scripts_are_valid_posix_shell(script):
    """В контейнере агента скрипт исполняет /bin/sh — у Debian это dash."""
    sh = shutil.which("dash") or shutil.which("sh")
    if not sh:
        pytest.skip("no POSIX shell to check the syntax with")
    # Байтами, а не текстом: на Windows текстовый режим дописал бы к строкам CR
    result = subprocess.run([sh, "-n"], input=script.encode(), capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors="replace")


class TestSummary:
    def test_installed_fq_means_exact_download_shaping(self):
        out = "IFACE=ens3\nROOT=installed:fq_codel\nsome tc noise\nACTIVE=1\n"
        state = shaper.summarize(cfg(), out, 0)
        assert state == {"enabled": True, "active": True, "loaded": True, "personal": 0,
                         "interface": "ens3", "root": "installed:fq_codel",
                         "download_exact": True, "error": None}

    def test_program_kept_for_personal_limits_is_not_an_active_general_shaper(self):
        """Общий шейпер выключен, программа стоит ради урезанных юзеров."""
        state = shaper.summarize(shaper.DISABLED, "ROOT=kept:fq\nACTIVE=1\n", 0, personal=3)
        assert state["active"] is False
        assert state["loaded"] is True and state["personal"] == 3

    def test_foreign_root_is_reported_as_rough_download(self):
        state = shaper.summarize(cfg(), "IFACE=ens3\nROOT=foreign:htb\nACTIVE=1\n", 0)
        assert state["active"] is True
        assert state["download_exact"] is False

    def test_failure_carries_the_reason(self):
        out = "IFACE=ens3\nERROR=egress pref 29304 on ens3 is taken by another tool\n"
        state = shaper.summarize(cfg(), out, 1)
        assert state["active"] is False
        assert "taken by another tool" in state["error"]

    def test_unexpected_failure_falls_back_to_the_last_line(self):
        state = shaper.summarize(cfg(), "IFACE=ens3\nlibbpf: prog 'rws_egress': failed to load\n", 255)
        assert state["error"] == "libbpf: prog 'rws_egress': failed to load"


def runner():
    r = CommandRunner.__new__(CommandRunner)
    r._settings = MagicMock(host_mode=False)
    r._shaper_general = shaper.DISABLED
    r._shaper_personal = {}
    r._shaper_loaded = False
    r._run_hostnet = AsyncMock(return_value=("IFACE=ens3\nROOT=kept:fq\nACTIVE=1\n", 0))
    r._send = AsyncMock()
    return r


class TestCommand:
    def test_command_is_allowed(self):
        assert "set_shaper" in ALLOWED_COMMAND_TYPES

    @pytest.mark.asyncio
    async def test_apply_answers_with_state(self):
        r = runner()
        await r._set_shaper({**BASE, "type": "set_shaper", "command_id": "shaper"})

        script = r._run_hostnet.await_args.args[0]
        assert "bpftool prog loadall" in script
        reply = r._send.await_args.args[0]
        assert reply["command_id"] == "shaper"
        assert reply["status"] == "completed"
        assert json.loads(reply["output"])["active"] is True

    @pytest.mark.asyncio
    async def test_personal_limits_survive_disabling_the_general_shaper(self):
        r = runner()
        r._shaper_personal = {"1.2.3.4": 1024}
        await r._set_shaper({"type": "set_shaper", "command_id": "shaper", "enabled": False})

        script = r._run_hostnet.await_args.args[0]
        assert "bpftool prog loadall" in script and "rws_personal key hex" in script
        assert "rws_ports key" not in script

    @pytest.mark.asyncio
    async def test_disable_runs_the_removal(self):
        r = runner()
        r._run_hostnet = AsyncMock(return_value=("IFACE=ens3\nROOT=restored\nACTIVE=0\n", 0))
        await r._set_shaper({"type": "set_shaper", "command_id": "shaper", "enabled": False})

        assert "bpftool prog loadall" not in r._run_hostnet.await_args.args[0]
        state = json.loads(r._send.await_args.args[0]["output"])
        assert state["enabled"] is False and state["root"] == "restored"

    @pytest.mark.asyncio
    async def test_invalid_command_never_reaches_the_shell(self):
        r = runner()
        await r._set_shaper({"type": "set_shaper", "command_id": "shaper", "enabled": True,
                             "ports": ["443; rm -rf /"], "down_kbit": 1000})

        r._run_hostnet.assert_not_awaited()
        reply = r._send.await_args.args[0]
        assert reply["status"] == "error"
        assert json.loads(reply["output"])["active"] is False
