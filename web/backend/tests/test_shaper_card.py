"""Карточка штрафа шейпера: кто, где, сколько и до какого времени урезан."""
from datetime import datetime, timezone

from web.backend.core.shaper_rollout import build_penalty_card

UNTIL = datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc)
EV = {"ip": "203.0.113.7", "bytes": 3 * 1024 ** 3, "until": UNTIL}
SETTINGS = {"penalty_kbit": 2000, "penalty_window_sec": 60}


def test_card_names_user_node_and_penalty():
    html = build_penalty_card("Germany <W>", SETTINGS, EV, [{"username": "alice", "uuid": "u1"}]).to_html()
    assert "<b>alice</b> · Germany &lt;W&gt;" in html
    assert "за 60 с" in html
    assert "Скорость: <b>до 2 Мбит/с</b>" in html
    assert "IP: <code>203.0.113.7</code>" in html


def test_penalty_end_is_shown_in_reader_timezone():
    blocks = build_penalty_card("Germany W", SETTINGS, EV, [{"username": None, "uuid": "abcdef0123"}]).to_blocks()
    fields = next(blk for blk in blocks if blk["type"] == "table")
    until = next(row[1]["text"] for row in fields["cells"] if row[0]["text"] == "До")
    assert until["type"] == "date_time" and until["unix_time"] == int(UNTIL.timestamp())
    assert until["date_time_format"] == "t"


def test_without_settings_no_speed_promise():
    """Настроек нет — не обещаем ни скорость, ни срок."""
    html = build_penalty_card("Germany W", None, EV, [{"username": "alice", "uuid": "u1"}]).to_html()
    assert "Скорость" not in html and "До:" not in html
