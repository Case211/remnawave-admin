"""Прямые вызовы Bot API идут через BOT_API_ROOT и BOT_PROXY_URL, как и бот.

История: у клиента бот ходил в Telegram через socks5 из .env, а уведомления
и бэкапы слались напрямую в api.telegram.org и молча не доходили.
"""
import sys
from unittest.mock import patch

import pytest

from shared import tg_http, tg_rich


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("BOT_API_ROOT", raising=False)
    monkeypatch.delenv("BOT_PROXY_URL", raising=False)
    monkeypatch.setattr(tg_http, "_socks_warned", False)


class TestSettings:
    def test_defaults(self):
        assert tg_http.api_root() == "https://api.telegram.org"
        assert tg_http.proxy_url() is None
        assert tg_http.client_kwargs(15) == {"timeout": 15}

    def test_custom_api_root_without_trailing_slash(self, monkeypatch):
        monkeypatch.setenv("BOT_API_ROOT", "https://tg.local:8443/ ")
        assert tg_http.method_url("1:A", "sendMessage") == "https://tg.local:8443/bot1:A/sendMessage"

    def test_http_proxy_goes_to_client(self, monkeypatch):
        monkeypatch.setenv("BOT_PROXY_URL", "http://proxy.local:3128")
        assert tg_http.client_kwargs(120) == {"timeout": 120, "proxy": "http://proxy.local:3128"}

    def test_socks_proxy_goes_to_client_when_socksio_present(self, monkeypatch):
        monkeypatch.setenv("BOT_PROXY_URL", "socks5://user:pass@1.2.3.4:1080")
        monkeypatch.setitem(sys.modules, "socksio", object())
        assert tg_http.client_kwargs(15)["proxy"] == "socks5://user:pass@1.2.3.4:1080"

    def test_socks_without_socksio_is_reported_once_without_credentials(self, monkeypatch):
        monkeypatch.setenv("BOT_PROXY_URL", "socks5://user:secret@1.2.3.4:1080")
        monkeypatch.setitem(sys.modules, "socksio", None)  # import падает как при отсутствии пакета
        with patch.object(tg_http.logger, "error") as error:
            assert "proxy" not in tg_http.client_kwargs(15)
            assert "proxy" not in tg_http.client_kwargs(15)
        assert error.call_count == 1
        logged = error.call_args.args[1]
        assert "secret" not in logged and "1.2.3.4:1080" in logged


class TestTgRichUsesBotSettings:
    """tg_rich строит адрес из BOT_API_ROOT и передаёт прокси в httpx."""

    def _client(self, seen):
        class _Resp:
            status_code = 200
            text = "ok"

        class _Client:
            def __init__(self, **kwargs):
                seen["kwargs"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json=None):
                seen.setdefault("urls", []).append(url)
                return _Resp()

        return _Client

    @pytest.mark.asyncio
    async def test_proxy_and_root_reach_httpx(self, monkeypatch):
        monkeypatch.setenv("BOT_API_ROOT", "https://tg.local")
        monkeypatch.setenv("BOT_PROXY_URL", "http://proxy.local:3128")
        seen: dict = {}
        with patch.object(tg_rich.httpx, "AsyncClient", self._client(seen)), \
             patch.object(tg_rich, "_rich_enabled", return_value=False):
            assert await tg_rich.send_rich_or_html("1:A", 5, "<b>hi</b>") is True
        assert seen["kwargs"] == {"timeout": 15, "proxy": "http://proxy.local:3128"}
        assert seen["urls"] == ["https://tg.local/bot1:A/sendMessage"]


class TestBackupUsesBotSettings:
    """Бэкап в Telegram уходит через тот же прокси и корень API, что и бот."""

    @pytest.mark.asyncio
    async def test_send_document_via_proxy(self, tmp_path, monkeypatch):
        from web.backend.core import backup_service

        monkeypatch.setattr(backup_service, "BACKUP_DIR", tmp_path)
        monkeypatch.setenv("BOT_API_ROOT", "https://tg.local")
        monkeypatch.setenv("BOT_PROXY_URL", "socks5://1.2.3.4:1080")
        monkeypatch.setitem(sys.modules, "socksio", object())
        (tmp_path / "db_backup_a.sql.gz").write_bytes(b"dump")
        seen: dict = {}

        class _Resp:
            status_code = 200
            text = ""

        class _Client:
            def __init__(self, **kwargs):
                seen["kwargs"] = kwargs

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, data=None, files=None):
                seen["url"] = url
                return _Resp()

        with patch("httpx.AsyncClient", _Client):
            result = await backup_service.send_backup_to_telegram("db_backup_a.sql.gz", chat_id="1", bot_token="t")

        assert result["parts_sent"] == 1
        assert seen["url"] == "https://tg.local/bott/sendDocument"
        assert seen["kwargs"] == {"timeout": 120, "proxy": "socks5://1.2.3.4:1080"}
