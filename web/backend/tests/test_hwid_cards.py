"""Карточки HWID-уведомлений.

Бот строит из этого текста rich-сообщение (``shared/tg_rich.html_to_blocks``),
и разметка тут не косметика: первая строка обязана стать заголовком, поля с
отступом — списком. Сломается отступ — уведомление доедет плоской простынёй,
и заметить это по тестам самой отправки невозможно.
"""
from datetime import datetime, timedelta, timezone

from shared.tg_rich import html_to_blocks
from web.backend.core.hwid_cards import blacklist_card, device_line, reuse_card, revived_card

FUTURE = datetime.now(timezone.utc) + timedelta(days=18)
HWID = "4c0e56f81ec134dc"


def _user(name, **over):
    user = {"user_uuid": name, "username": name, "telegram_id": 100,
            "status": "ACTIVE", "is_trial": True}
    user.update(over)
    return user


def _types(card):
    return [b.get("type") for b in html_to_blocks(card)]


class TestRichLayout:
    def test_reuse_card_becomes_heading_and_lists(self):
        card = reuse_card(HWID, _user("new"), [_user("old", status="EXPIRED")], [])
        types = _types(card)
        assert types[0] == "heading"
        assert "list" in types, "поля должны стать списком, а не абзацем"

    def test_blacklist_card_becomes_heading_and_lists(self):
        types = _types(blacklist_card(HWID, {"reason": "Абуз"}, [_user("who")], True))
        assert types[0] == "heading"
        assert "list" in types

    def test_revived_card_becomes_heading_and_lists(self):
        types = _types(revived_card(HWID, {"reason": "Абуз"}, [_user("who")], True))
        assert types[0] == "heading"
        assert "list" in types


class TestContent:
    def test_repeat_trial_changes_the_headline(self):
        repeat = reuse_card(HWID, _user("new"), [_user("old")], [])
        stranger = reuse_card(HWID, _user("new"), [], [_user("other", telegram_id=999)])
        assert "Повторная пробная" in repeat.splitlines()[0]
        assert "переехал" in stranger.splitlines()[0]

    def test_subscription_state_is_spelled_out(self):
        card = reuse_card(HWID, _user("new", expire_at=FUTURE), [_user("old", status="EXPIRED")], [])
        assert "пробная" in card
        assert "истекла" in card

    def test_unlinked_device_is_dated(self):
        card = reuse_card(HWID, _user("new"),
                          [_user("old", removed_at=datetime(2026, 8, 22, 12, 48))], [])
        assert "Устройство отвязано: 22.08.2026 12:48" in card

    def test_active_connections_shown_when_present(self):
        card = revived_card(HWID, {}, [_user("who", active_connections=3)], True)
        assert "Подключений сейчас" in card

    def test_long_tail_is_collapsed(self):
        users = [_user(f"u{i}", telegram_id=i) for i in range(9)]
        card = blacklist_card(HWID, {}, users, True)
        assert "<blockquote expandable>" in card
        assert "И ещё 5" in card

    def test_device_line_reads_naturally(self):
        line = device_line({"platform": "android", "os_version": "15",
                            "device_model": "SM-A366E", "app_version": "Happ/3.25.1"})
        assert line == "Android 15 · SM-A366E (Happ/3.25.1)"

    def test_html_in_username_is_escaped(self):
        """Имя из панели попадает в разметку — без экранирования оно её порвёт."""
        card = revived_card(HWID, {}, [_user("<b>evil</b>")], True)
        assert "&lt;b&gt;evil&lt;/b&gt;" in card
        assert _types(card)[0] == "heading"
