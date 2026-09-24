"""Мягкая блокировка: 0 или пусто в скорости — без лимита.

Раньше пустая или нулевая скорость по умолчанию молча превращалась в 1024,
и кнопка в боте урезала человека, хотя в настройках стоял ноль.
"""
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

import shared.throttle as throttle
from web.backend.schemas.violation import ThrottleAddRequest

USER = "11111111-2222-3333-4444-555555555555"


def _cfg(value):
    cfg = MagicMock()
    cfg.get = lambda key, default=None: value if key == "throttle_default_kbit" else default
    return cfg


@pytest.mark.parametrize("value,expected", [
    ("2048", 2048), (1024, 1024), ("0", 0), (0, 0), ("", 0), (None, 0), ("abc", 0), ("-5", 0),
])
def test_default_rate_zero_or_empty_means_no_limit(value, expected):
    with patch.object(throttle, "config_service", _cfg(value)):
        assert throttle.default_rate_kbit() == expected


@pytest.mark.parametrize("rate", [None, 0, 64, 1024])
def test_request_accepts_no_limit_and_real_speeds(rate):
    assert ThrottleAddRequest(user_uuid=USER, rate_kbit=rate).rate_kbit == rate


@pytest.mark.parametrize("rate", [1, 32, 63, -1])
def test_request_rejects_speeds_that_are_not_a_throttle(rate):
    """Меньше 64 кбит/с соединение не живёт — это уже не урезание."""
    with pytest.raises(ValidationError):
        ThrottleAddRequest(user_uuid=USER, rate_kbit=rate)
