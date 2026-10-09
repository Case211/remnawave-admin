"""Карточки атаки на ноду: «сейчас против обычного» таблицей, признаки списком."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from web.backend.core.attack_detector import _fmt_duration, finished_card, started_card

SAMPLE = SimpleNamespace(name="Germany <W>", node_uuid="n1", rx_bps=125_000_000, rx_pps=1_200_000)
BASELINE = SimpleNamespace(rx_bps=2_500_000, rx_pps=40_000)


def test_started_card_compares_now_with_usual():
    card = started_card(SAMPLE, SimpleNamespace(reasons=["syn_flood", "nic_drops"]), BASELINE)
    table = next(blk for blk in card.to_blocks() if blk["type"] == "table")
    head, rx, pps = table["cells"]
    assert [cell["text"] for cell in head] == ["Показатель", "Сейчас", "Обычно"]
    assert rx[1]["text"] == {"type": "bold", "text": "1000 Мбит/с"}
    assert rx[2]["text"] == "20 Мбит/с"
    assert pps[1]["text"] == {"type": "bold", "text": "1 200 000"}
    signs = next(blk for blk in card.to_blocks() if blk["type"] == "list")
    assert signs["items"][0]["blocks"][0]["text"] == "SYN-флуд (ядро отвечает syncookies)"
    # имя ноды экранируется в HTML-фолбэке — раньше шло в разметку как есть
    assert "Germany &lt;W&gt;" in card.to_html()


def test_escalation_has_its_own_headline():
    card = started_card(SAMPLE, SimpleNamespace(reasons=["syn_flood"]), BASELINE, escalated=True)
    assert card.title_text() == "Атака усилилась"


def test_finished_card_dates_are_in_reader_timezone():
    start = datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc)
    card = finished_card({"name": "Germany W", "started_at": start,
                          "last_seen_at": start + timedelta(minutes=95), "peak_rx_bps": 125_000_000})
    html = card.to_html()
    assert "Длилась: <b>1 ч 35 мин</b>" in html
    assert "Пик приёма: 1000 Мбит/с" in html
    assert html.count("<tg-time") == 3  # начало, конец и подвал


def test_short_attack_counts_minutes():
    start = datetime(2026, 10, 9, 10, 0)
    assert _fmt_duration(start, start + timedelta(seconds=30)) == "1 мин"
