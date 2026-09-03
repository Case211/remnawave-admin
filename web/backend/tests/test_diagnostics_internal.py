"""Снимок коллектора в раздельном режиме доступен без INTERNAL_API_SECRET.

Ключ выводится из WEB_SECRET_KEY, одинакового у api и коллектора, поэтому на
установке без INTERNAL_API_SECRET серия больше не остаётся без коллектора.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from web.backend.api.v2 import diagnostics


def _settings(secret_key: str):
    return lambda: SimpleNamespace(secret_key=secret_key)


class TestInternalSecret:
    def test_derived_from_web_secret_key(self, monkeypatch):
        monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
        with patch.object(diagnostics, "get_web_settings", _settings("k" * 32)):
            first, second = diagnostics._internal_secret(), diagnostics._internal_secret()
        with patch.object(diagnostics, "get_web_settings", _settings("j" * 32)):
            other = diagnostics._internal_secret()
        assert first == second
        assert first != other
        assert "k" * 32 not in first

    def test_explicit_secret_wins(self, monkeypatch):
        monkeypatch.setenv("INTERNAL_API_SECRET", "explicit-secret")
        with patch.object(diagnostics, "get_web_settings", _settings("k" * 32)):
            assert diagnostics._internal_secret() == "explicit-secret"


class TestCollectorSnapshotRoute:
    def _request(self, header: str | None) -> MagicMock:
        req = MagicMock()
        req.headers = {} if header is None else {"X-Internal-Api-Secret": header}
        return req

    @pytest.mark.asyncio
    async def test_accepts_derived_key(self, monkeypatch):
        monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
        with patch.object(diagnostics, "get_web_settings", _settings("k" * 32)), \
                patch.object(diagnostics, "_process_snapshot", return_value={"app_mode": "collector"}):
            resp = await diagnostics.collector_memory_snapshot(self._request(diagnostics._internal_secret()))
        assert resp == {"app_mode": "collector"}

    @pytest.mark.asyncio
    async def test_rejects_wrong_or_missing_key(self, monkeypatch):
        monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
        with patch.object(diagnostics, "get_web_settings", _settings("k" * 32)), \
                patch.object(diagnostics, "_process_snapshot", return_value={"app_mode": "collector"}):
            wrong = await diagnostics.collector_memory_snapshot(self._request("nope"))
            missing = await diagnostics.collector_memory_snapshot(self._request(None))
        assert wrong.status_code == 401
        assert missing.status_code == 401

    @pytest.mark.asyncio
    async def test_api_side_sends_same_key(self, monkeypatch):
        monkeypatch.delenv("INTERNAL_API_SECRET", raising=False)
        sent = {}

        class _Resp:
            status_code = 200

            def json(self):
                return {"app_mode": "collector"}

        class _Client:
            def __init__(self, *a, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, headers=None):
                sent["url"], sent["headers"] = url, headers
                return _Resp()

        with patch.object(diagnostics, "get_web_settings", _settings("k" * 32)), \
                patch.object(diagnostics.httpx, "AsyncClient", _Client):
            snap = await diagnostics._fetch_collector_snapshot()
            expected = diagnostics._internal_secret()
        assert snap == {"app_mode": "collector"}
        assert sent["headers"]["X-Internal-Api-Secret"] == expected
        assert sent["url"].endswith("/api/v2/collector/diagnostics/memory")
