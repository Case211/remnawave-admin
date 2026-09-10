"""Перевод с запасным текстом — регрессия #274.

Хендлеры зовут `_("ключ", default="Текст")`. Базовый `I18n.gettext()`
такого аргумента не знает, и вызов падал с TypeError — кнопки
подтверждения в боте не отрисовывались вовсе.

Живой gettext здесь не проверить: conftest бота подменяет весь aiogram
моками, так что базовый класс JsonI18n — MagicMock. Проверяем то, что
от моков не зависит: сигнатуру нашего метода и наличие текстов в обеих
локалях.
"""
import ast
import json
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
HANDLERS_DIR = PROJECT_ROOT / "src" / "handlers"
LOCALES_DIR = PROJECT_ROOT / "locales"

# `_("ключ", default="текст")` в любых кавычках
CALL_RE = re.compile(r"""_\(\s*(?P<q>["'])(?P<key>[a-z0-9_.]+)(?P=q)\s*,\s*default=""")


def _flatten(data: dict, prefix: str = "") -> dict:
    flat = {}
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flat.update(_flatten(value, full))
        else:
            flat[full] = value
    return flat


def _locale_keys(lang: str) -> set:
    path = LOCALES_DIR / lang / "messages.json"
    return set(_flatten(json.loads(path.read_text(encoding="utf-8-sig"))))


def _keys_used_with_default() -> set:
    keys = set()
    for path in HANDLERS_DIR.rglob("*.py"):
        keys.update(m.group("key") for m in CALL_RE.finditer(path.read_text(encoding="utf-8")))
    return keys


def test_gettext_accepts_default():
    """Аргумент `default` должен доходить до нашего переопределения,
    иначе базовый I18n.gettext снова свалится с TypeError.

    Читаем исходник, а не импортируем класс: с замоканным aiogram
    JsonI18n сам оказывается моком и сигнатуру не отдаёт."""
    module = ast.parse((PROJECT_ROOT / "src" / "utils" / "i18n.py").read_text(encoding="utf-8"))
    methods = [
        node
        for cls in module.body
        if isinstance(cls, ast.ClassDef) and cls.name == "JsonI18n"
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and node.name == "gettext"
    ]
    assert methods, "JsonI18n больше не переопределяет gettext"
    args = methods[0].args
    names = [a.arg for a in args.args + args.kwonlyargs]
    assert "default" in names


def test_handlers_actually_use_defaults():
    """Страховка теста ниже: если вызовов не нашлось, регулярка отстала
    от кода и проверка локалей молча превратилась бы в пустую."""
    assert _keys_used_with_default()


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_default_texts_are_translated(lang):
    """Запасной текст в коде русский — без ключа в локали английский
    интерфейс показывал бы его как есть."""
    missing = sorted(_keys_used_with_default() - _locale_keys(lang))
    assert not missing, f"нет в locales/{lang}/messages.json: {missing}"
