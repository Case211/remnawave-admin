"""BOT_PROXY_URL: отсев схем, которые прокси-клиент не осилит.

pydantic сам по себе пропускает любую схему, а aiohttp-socks понимает
только http/socks4/socks5 — на остальных aiogram падает уже в рантайме
с «Invalid scheme component», где про .env не сказано ни слова. Поэтому
схема проверяется на старте, с внятным сообщением.
"""
import os

import pytest
from pydantic import ValidationError

from src.config import PROXY_SCHEMES, Settings

BASE_ENV = {"BOT_TOKEN": "123:ABC", "API_BASE_URL": "http://localhost:8080"}


def _settings(proxy_url=None):
    env = dict(BASE_ENV)
    if proxy_url is not None:
        env["BOT_PROXY_URL"] = proxy_url
    saved = {k: os.environ.get(k) for k in ("BOT_TOKEN", "API_BASE_URL", "BOT_PROXY_URL")}
    os.environ.pop("BOT_PROXY_URL", None)
    os.environ.update(env)
    try:
        return Settings()
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.mark.parametrize(
    "url",
    [
        "socks5://user:pass@1.2.3.4:1080",
        "socks4://1.2.3.4:1080",
        "http://proxy.local:3128",
    ],
)
def test_supported_schemes_accepted(url):
    assert _settings(url).bot_proxy_url is not None


@pytest.mark.parametrize("url", ["socks5h://1.2.3.4:9050", "https://proxy.local:3128"])
def test_unsupported_schemes_rejected_at_startup(url):
    with pytest.raises(ValidationError) as exc:
        _settings(url)
    assert "BOT_PROXY_URL" in str(exc.value)


def test_socks5h_hint_points_at_socks5():
    """Самая вероятная ошибка — лишняя «h»; подсказка должна её назвать."""
    with pytest.raises(ValidationError) as exc:
        _settings("socks5h://1.2.3.4:9050")
    assert "socks5" in str(exc.value)


def test_proxy_is_optional():
    assert _settings().bot_proxy_url is None


def test_schemes_match_what_client_supports():
    assert PROXY_SCHEMES == ("http", "socks4", "socks5")
