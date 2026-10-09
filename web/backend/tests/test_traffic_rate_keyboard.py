"""Кнопки карточки «Высокое потребление трафика»."""
from web.backend.core.traffic_rate_monitor import _traffic_rate_buttons


def _callbacks(rows: list) -> list:
    return [button.callback_data for row in rows for button in row]


def test_traffic_rate_card_offers_throttle():
    """Регрессия: клавиатура собиралась отдельно, и «🐌 Урезать скорость» на ней не было."""
    data = _callbacks(_traffic_rate_buttons("uuid-1"))
    assert "vact:thr:uuid-1" in data
    assert "vact:block:uuid-1" in data
    assert "vact:kill:uuid-1" in data
    assert "vact:reset:uuid-1" in data


def test_traffic_rate_card_has_no_whitelist():
    """Превышение порога — не анализатор нарушений, белый список на него не влияет."""
    data = _callbacks(_traffic_rate_buttons("uuid-1"))
    assert not any(cd.startswith("vact:wl") for cd in data)
