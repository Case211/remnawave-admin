"""Прямые вызовы Bot API тем же путём, что и бот.

Уведомления (``tg_rich``) и бэкапы ходят в Telegram напрямую через httpx, минуя
aiogram-сессию бота. На сервере без прямого доступа к Telegram бот через
``BOT_PROXY_URL`` работает, а уведомления и бэкапы молча не доходят. Здесь оба
пути сводятся к одним настройкам: ``BOT_API_ROOT`` и ``BOT_PROXY_URL``.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from shared.logger import logger

DEFAULT_API_ROOT = "https://api.telegram.org"
_socks_warned = False


def api_root() -> str:
    """Корень Bot API: свой сервер из BOT_API_ROOT или официальный."""
    value = (os.environ.get("BOT_API_ROOT") or "").strip().rstrip("/")
    return value or DEFAULT_API_ROOT


def proxy_url() -> Optional[str]:
    """Прокси до Telegram из BOT_PROXY_URL, если задан."""
    value = (os.environ.get("BOT_PROXY_URL") or "").strip()
    return value or None


def method_url(token: str, method: str) -> str:
    return f"{api_root()}/bot{token}/{method}"


def client_kwargs(timeout: float) -> dict[str, Any]:
    """Аргументы для ``httpx.AsyncClient``: таймаут и прокси бота.

    SOCKS в httpx требует пакет socksio; без него прокси не применяется, а в лог
    один раз уходит внятная причина вместо ImportError из глубины httpx.
    """
    global _socks_warned
    kwargs: dict[str, Any] = {"timeout": timeout}
    proxy = proxy_url()
    if not proxy:
        return kwargs
    if proxy.lower().startswith("socks"):
        try:
            import socksio  # noqa: F401
        except ImportError:
            if not _socks_warned:
                logger.error(
                    "BOT_PROXY_URL (%s): для SOCKS в httpx нужен пакет socksio, "
                    "уведомления и бэкапы пойдут напрямую",
                    proxy.rsplit("@", 1)[-1],
                )
                _socks_warned = True
            return kwargs
    kwargs["proxy"] = proxy
    return kwargs
