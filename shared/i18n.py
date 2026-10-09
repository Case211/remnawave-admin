"""Переводы для shared и бэкенда — те же locales, что у бота.

Бот переводит свои экраны через aiogram, а уведомления, которые собираются
в shared и в бэкенде, раньше писались по-русски прямо в коде. tr() читает
тот же locales/<язык>/messages.json на языке бота (bot_language в
настройках) с откатом на русский и, в крайнем случае, на сам ключ.
"""
from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"
DEFAULT_LANG = "ru"


def _flatten(data: dict, prefix: str = "") -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, full))
        else:
            flat[full] = str(value)
    return flat


@lru_cache(maxsize=None)
def _messages(lang: str) -> dict[str, str]:
    try:
        return _flatten(json.loads((LOCALES_DIR / lang / "messages.json").read_text(encoding="utf-8-sig")))
    except (OSError, ValueError):
        return {}


def language() -> str:
    """Язык бота: настройки панели → DEFAULT_LOCALE → русский."""
    try:
        from shared.config_service import config_service
        if config_service._initialized:
            lang = config_service.get("bot_language")
            if lang:
                return str(lang)
    except Exception:
        pass
    return os.environ.get("DEFAULT_LOCALE") or DEFAULT_LANG


def tr(key: str, /, **kwargs: Any) -> str:
    lang = language()
    template = _messages(lang).get(key)
    if template is None and lang != DEFAULT_LANG:
        template = _messages(DEFAULT_LANG).get(key)
    if template is None:
        return key
    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template
