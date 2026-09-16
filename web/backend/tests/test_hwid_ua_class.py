"""Класс UA устройства считает бэкенд — с пользовательскими regex из настроек.

Регрессия: фронт классифицировал по своей копии списка, и клиент, добавленный
в «Дополнительный whitelist UA» в настройках, всё равно светился «неизвестным».
"""
from unittest.mock import MagicMock, patch

from web.backend.api.v2 import users


def _config(whitelist=None, blacklist=None):
    cfg = MagicMock()
    cfg.get = lambda key, default=None: {
        "violation_ua_whitelist_extra": whitelist or [],
        "violation_ua_blacklist_extra": blacklist or [],
    }.get(key, default)
    return cfg


def _classify(ua, **config):
    users._ua_analyzer = None
    with patch("shared.config_service.config_service", _config(**config)):
        return users._ua_class(ua)


def test_builtin_clients_are_valid():
    assert _classify("INCY/2.6.1/ios CFNetwork/3860.700.1 Darwin/25.6.0") == "valid"
    assert _classify("Happ/4.4.1/Android/1789110731330196751") == "valid"


def test_settings_whitelist_makes_unknown_client_valid():
    assert _classify("MyClient/1.0") == "unknown"
    assert _classify("MyClient/1.0", whitelist=["^MyClient/"]) == "valid"


def test_settings_blacklist_marks_client_as_script():
    assert _classify("SuspiciousBot/2.0", blacklist=["^SuspiciousBot/"]) == "bot_library"


def test_empty_and_stub():
    assert _classify("") == "empty"
    assert _classify("Mozilla/5.0") == "stub"
