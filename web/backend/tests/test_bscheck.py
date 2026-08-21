"""Тесты bschekbot-клиента (core/bscheck.py) — проба нод через операторов РФ."""
import json

import httpx
import pytest
from unittest.mock import patch

from web.backend.core import bscheck as bs


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


def _token():
    return patch.object(bs, "_stored_token", return_value="bsk_live_TEST")


# ── summarize ────────────────────────────────────────────────────


class TestSummarize:
    def test_counts_passed_and_sorts_ops(self):
        result = {"cost_credits": 12, "by_target": {"1.2.3.4": {"by_operator": {
            "mts|цфо|on": {"ok": True, "operator": "mts", "region": "ЦФО", "dpi": "on",
                           "channel_state": "DPI_ON", "icmp": {"ok": True, "rtt_avg_ms": 140}},
            "tele2|дфо|on": {"ok": True, "operator": "tele2", "region": "ДФО", "dpi": "on",
                             "channel_state": "DPI_ON", "icmp": {"ok": False},
                             "tcp": {"ok": False}, "error": "timeout"}}}},
            "skipped_dpi_off": [{"operator": "beeline", "region": "ЮФО"}]}
        s = bs.summarize(result, "1.2.3.4")
        assert s["passed"] == 1 and s["total"] == 2
        assert s["cost_credits"] == 12 and s["skipped_dpi_off"] == ["beeline (ЮФО)"]
        assert s["operators"][0]["op"] == "mts|цфо|on"  # отсортировано по op
        assert s["operators"][0]["region"] == "ЦФО" and s["operators"][0]["dpi"] == "on"
        assert s["operators"][0]["latency_ms"] == 140

    def test_ok_without_probes_means_reachable(self):
        """ok у ноги = «проба выполнена». Без вложенных проб доверяем ему."""
        result = {"by_target": {"t": {"by_operator": {"mts|цфо|on": {"ok": True}}}}}
        assert bs.summarize(result, "t")["passed"] == 1

    def test_probe_done_but_target_unreachable(self):
        """Проба отработала штатно, а цель не ответила — это НЕ «прошло»."""
        result = {"by_target": {"t": {"by_operator": {"mts|цфо|on": {
            "ok": True, "icmp": {"ok": False, "loss_pct": 100}, "tcp": {"ok": False}}}}}}
        s = bs.summarize(result, "t")
        assert s["passed"] == 0 and s["total"] == 1

    def test_empty(self):
        s = bs.summarize({}, "x")
        assert s["passed"] == 0 and s["total"] == 0 and s["operators"] == []


# ── Клиент ───────────────────────────────────────────────────────


class TestClient:
    @pytest.mark.asyncio
    async def test_verify_and_account(self):
        def h(r):
            assert r.headers.get("Authorization") == "Bearer bsk_live_TEST"
            if r.url.path == "/v1/account":
                return httpx.Response(200, json={"balance_credits": 4500, "tier": "silver"})
            return httpx.Response(404)

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await bs.verify_token("bsk_live_TEST") is True
        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            acc = await bs.get_account()
        assert acc["balance_credits"] == 4500

    @pytest.mark.asyncio
    async def test_operators(self):
        def h(r):
            return httpx.Response(200, json={"n_units": 1, "n_probeable": 1, "units": [
                {"op_key": "mts|цфо|on", "operator": "mts", "name": "МТС", "region": "ЦФО",
                 "region_code": "cfo", "dpi": "on", "channel_state": "DPI_ON", "probeable": True}]})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            ops = await bs.get_operators()
        assert ops[0]["op_key"] == "mts|цфо|on" and ops[0]["dpi"] == "on"
        assert ops[0]["region"] == "ЦФО" and ops[0]["probeable"] is True

    @pytest.mark.asyncio
    async def test_operators_legacy_field(self):
        """Ответ старого сервиса клал единицы в operators — читаем и его."""
        def h(r):
            return httpx.Response(200, json={"operators": [
                {"id": "mts", "name": "МТС", "op_key": "ufo1:mts",
                 "channel_state": "DPI_ON", "alive": True}]})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            ops = await bs.get_operators()
        assert ops[0]["op_key"] == "ufo1:mts"

    @pytest.mark.asyncio
    async def test_probe_sends_idempotency_and_body(self):
        seen = {}

        def h(r):
            if r.url.path == "/v1/probe":
                seen["idem"] = r.headers.get("Idempotency-Key")
                seen["body"] = json.loads(r.content.decode())
                return httpx.Response(200, json={"outcome": "done", "cost_credits": 12, "by_target": {
                    "1.2.3.4": {"by_operator": {"ufo1:mts": {"ok": True, "channel_state": "DPI_ON"}}}}})
            return httpx.Response(404)

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            res = await bs.probe({"target": "1.2.3.4", "operators": ["ufo1:mts"],
                                  "probes": {"tcp": True}, "dpi": "on"})
        assert seen["idem"]  # Idempotency-Key проставлен на платном POST
        assert seen["body"]["target"] == "1.2.3.4"
        assert res["cost_credits"] == 12

    @pytest.mark.asyncio
    async def test_error_envelope(self):
        def h(r):
            return httpx.Response(402, json={"error": {
                "code": "insufficient_credits", "message": "не хватает баланса"}})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            with pytest.raises(bs.BscheckError, match="баланса"):
                await bs.probe({"target": "1.2.3.4"})

    @pytest.mark.asyncio
    async def test_not_configured(self):
        with patch.object(bs, "_stored_token", return_value=None):
            with pytest.raises(bs.BscheckError, match="не настроен"):
                await bs.get_operators()

    @pytest.mark.asyncio
    async def test_verify_false_on_unauthenticated(self):
        def h(r):
            return httpx.Response(401, json={"error": {"code": "unauthenticated"}})

        with patch("httpx.AsyncClient", _patched_client(h)):
            assert await bs.verify_token("bad") is False


# ── summarize_all (мульти-цель) ──────────────────────────────────


class TestSummarizeAll:
    def test_multi_target(self):
        result = {"by_target": {
            "1.1.1.1": {"by_operator": {"ufo1:mts": {"ok": True, "channel_state": "DPI_ON"}}},
            "2.2.2.2": {"by_operator": {"ufo1:mts": {"ok": False, "channel_state": "DPI_ON"}}}}}
        rows = bs.summarize_all(result)
        assert len(rows) == 2
        assert rows[0]["target"] == "1.1.1.1" and rows[0]["passed"] == 1
        assert rows[1]["target"] == "2.2.2.2" and rows[1]["passed"] == 0


# ── Скан /24 и VLESS ─────────────────────────────────────────────


class TestScansVless:
    @pytest.mark.asyncio
    async def test_scan_submit_and_status(self):
        def h(r):
            if r.url.path == "/v1/scans" and r.method == "POST":
                assert r.headers.get("Idempotency-Key")
                return httpx.Response(200, json={"outcome": "queued", "scan_id": 12345, "state": "running"})
            if r.url.path == "/v1/scans/12345":
                return httpx.Response(200, json={"scan_id": 12345, "state": "done",
                                                 "result": {"up_n": 7, "total": 256}})
            return httpx.Response(404)

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            sub = await bs.scans_submit({"cidr": "1.2.3.0/24", "operators": ["ufo1:mts"]})
            st = await bs.scans_status("12345")
        assert sub["scan_id"] == 12345 and st["state"] == "done" and st["result"]["up_n"] == 7

    @pytest.mark.asyncio
    async def test_scan_preview(self):
        def h(r):
            return httpx.Response(200, json={"cost_credits": 240, "total_ips": 256})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            p = await bs.scans_preview({"cidr": "1.2.3.0/24"})
        assert p["cost_credits"] == 240

    @pytest.mark.asyncio
    async def test_vless_submit_and_status(self):
        def h(r):
            if r.url.path == "/v1/vless" and r.method == "POST":
                assert r.headers.get("Idempotency-Key")
                return httpx.Response(200, json={"outcome": "queued", "test_id": 88, "cost_credits": 30})
            if r.url.path == "/v1/vless/88":
                return httpx.Response(200, json={"test_id": 88, "state": "done", "result_ready": True,
                    "result": [{"server_name": "s1", "ok": True, "tunnel_up": True, "speed_mbps": 42.0}]})
            return httpx.Response(404)

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            sub = await bs.vless_submit({"raw_input": "vless://x", "dpi": "on"})
            st = await bs.vless_status("88")
        assert sub["test_id"] == 88 and st["result_ready"] is True
        assert st["result"][0]["speed_mbps"] == 42.0


# ── Скан: только /24 ─────────────────────────────────────────────


class TestScanCidr:
    def test_normalizes_and_requires_24(self):
        from web.backend.api.v2.bscheck import ScanIn
        # host-биты нормализуются в .0/24
        assert ScanIn(cidr="1.2.3.4/24").cidr == "1.2.3.0/24"
        assert ScanIn(cidr="10.20.30.0/24").cidr == "10.20.30.0/24"
        # всё, что не /24 (или мусор), отклоняется
        for bad in ("1.2.3.0/16", "1.2.3.0/25", "1.2.3.0", "10.0.0.0/8", "300.1.1.0/24"):
            with pytest.raises(Exception):
                ScanIn(cidr=bad)


# ── Контракт 1.1: отмена, фильтр dpi, выбор ядра ─────────────────


class TestCancel:
    @pytest.mark.asyncio
    async def test_scan_cancel(self):
        seen = {}

        def h(r):
            seen["url"] = str(r.url)
            seen["idem"] = r.headers.get("Idempotency-Key")
            return httpx.Response(200, json={"scan_id": 7, "state": "cancelled",
                                             "done_ips": 90, "total_ips": 256, "n_jobs_stopped": 2})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            res = await bs.scans_cancel("7")
        assert res["state"] == "cancelled" and res["done_ips"] == 90
        assert seen["url"].endswith("/scans/7/cancel")
        assert seen["idem"] is None   # отмена бесплатна, ключ идемпотентности не нужен

    @pytest.mark.asyncio
    async def test_vless_cancel(self):
        def h(r):
            return httpx.Response(200, json={"test_id": 5, "cancelled": True,
                                             "stopped_legs": 3, "refunded_credits": 120})

        with _token(), patch("httpx.AsyncClient", _patched_client(h)):
            res = await bs.vless_cancel("5")
        assert res["cancelled"] is True and res["refunded_credits"] == 120


class TestContractModes:
    def test_dpi_off_accepted(self):
        """Режим «только без БС» появился в 1.1 — раньше валидатор его резал."""
        from web.backend.api.v2.bscheck import ProbeIn, ScanIn, VlessIn
        assert ProbeIn(target="1.2.3.4", dpi="off").dpi == "off"
        assert ScanIn(cidr="1.2.3.0/24", dpi="off").dpi == "off"
        assert VlessIn(raw_input="vless://x", dpi="off").dpi == "off"
        with pytest.raises(Exception):
            ProbeIn(target="1.2.3.4", dpi="bogus")

    def test_core_modes_and_legacy_alias(self):
        from web.backend.api.v2.bscheck import VlessIn
        assert VlessIn(raw_input="v").core == ""            # деф. — Авто
        assert VlessIn(raw_input="v", core="prerelease").core == "prerelease"
        assert VlessIn(raw_input="v", core="new").core == "prerelease"   # легаси-имя
        assert VlessIn(raw_input="v", core="auto").core == ""
        with pytest.raises(Exception):
            VlessIn(raw_input="v", core="bogus")

    def test_unit_item_keeps_old_names(self):
        """UI и журнал читают старые имена полей — отдаём оба набора."""
        from web.backend.api.v2.bscheck import _unit_item
        item = _unit_item({"op_key": "mts|цфо|on", "operator": "mts", "name": "МТС",
                           "region": "ЦФО", "region_code": "cfo", "dpi": "on",
                           "channel_state": "DPI_ON", "probeable": True})
        assert item["operator"] == item["id"] == "mts"
        assert item["region"] == item["region_label"] == "ЦФО"
        assert item["probeable"] == item["alive"] is True
        assert item["dpi"] == "on"
