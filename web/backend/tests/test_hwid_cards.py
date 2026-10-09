"""Карточки HWID-уведомлений (shared.tg_card).

Люди идут таблицей, длинный хвост сворачивается, время — в поясе читателя.
HTML-фолбэк проверяется тут же: на него карточка уходит, если rich не принят,
и сломанное экранирование порвало бы именно его.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from shared import timefmt
from web.backend.core.hwid_cards import blacklist_card, device_line, reuse_card, revived_card

FUTURE = datetime.now(timezone.utc) + timedelta(days=18)
HWID = "4c0e56f81ec134dc"


def _user(name, **over):
    user = {"user_uuid": name, "username": name, "telegram_id": 100,
            "status": "ACTIVE", "is_trial": True}
    user.update(over)
    return user


def _types(card):
    return [blk["type"] for blk in card.to_blocks()]


def _copied(value, label=None):
    """Поле, которое копируется касанием: кнопка copy_text внутри текста."""
    return {"type": "button", "button": {"text": label or value, "copy_text": {"text": value}}}


def _people(card):
    """Таблица людей — та, что с шапкой «Аккаунт»."""
    tables = [blk for blk in card.to_blocks() if blk["type"] == "table"]
    return next(t for t in tables if t["cells"][0][0]["text"] == "Аккаунт")


class TestRichLayout:
    def test_cards_open_with_heading_and_list_people_in_a_table(self):
        for card in (
            reuse_card(HWID, _user("new"), [_user("old", status="EXPIRED")], []),
            blacklist_card(HWID, {"reason": "Абуз"}, [_user("who")], True),
            revived_card(HWID, {"reason": "Абуз"}, [_user("who")], True),
        ):
            types = _types(card)
            assert types[0] == "heading"
            assert "table" in types
            assert types[-1] == "footer"

    def test_account_name_is_copied_and_profile_is_a_link(self):
        people = _people(revived_card(HWID, {}, [_user("who")], True))
        assert all(cell.get("is_header") for cell in people["cells"][0])
        assert people["cells"][1][0]["text"] == [
            _copied("who"),
            " · ",
            {"type": "url", "text": "профиль", "url": "tg://user?id=100"},
        ]

    def test_without_telegram_only_the_name(self):
        people = _people(revived_card(HWID, {}, [_user("who", telegram_id=None)], True))
        assert people["cells"][1][0]["text"] == _copied("who")

    def test_without_name_the_full_uuid_is_copied(self):
        user = _user("x", telegram_id=None, username=None, user_uuid="0123456789abcdef")
        people = _people(revived_card(HWID, {}, [user], True))
        assert people["cells"][1][0]["text"] == _copied("0123456789abcdef", "01234567")


class TestContent:
    def test_repeat_trial_changes_the_headline(self):
        repeat = reuse_card(HWID, _user("new"), [_user("old")], [])
        stranger = reuse_card(HWID, _user("new"), [], [_user("other", telegram_id=999)])
        assert "Повторная пробная" in repeat.title_text()
        assert "переехал" in stranger.title_text()

    def test_subscription_state_is_spelled_out(self):
        html = reuse_card(HWID, _user("new", expire_at=FUTURE), [_user("old", status="EXPIRED")], []).to_html()
        assert "пробная" in html
        assert "истекла" in html

    def test_unlinked_device_is_dated(self):
        """Время из базы (UTC) показывается в зоне панели и подписано."""
        with patch.object(timefmt, "zone_name", return_value="Europe/Moscow"):
            html = reuse_card(HWID, _user("new"),
                              [_user("old", removed_at=datetime(2026, 8, 22, 12, 48))], []).to_html()
        assert "отвязано 22.08.2026 15:48 МСК" in html

    def test_active_connections_shown_when_present(self):
        people = _people(revived_card(HWID, {}, [_user("who", active_connections=3)], True))
        now_col = [cell["text"] for cell in people["cells"][0]].index("Сейчас")
        assert people["cells"][1][now_col]["text"] == "3"

    def test_long_tail_is_collapsed(self):
        users = [_user(f"u{i}", telegram_id=i + 1) for i in range(9)]
        card = blacklist_card(HWID, {}, users, True)
        assert len(_people(card)["cells"]) == 1 + 5  # шапка и пятеро
        tail = next(blk for blk in card.to_blocks() if blk["type"] == "details")
        assert tail["summary"] == "… и ещё 4"
        assert "u5" in str(tail["blocks"])

    def test_reason_and_who_added(self):
        html = blacklist_card(HWID, {"reason": "Абуз", "added_by_username": "admin"}, [_user("who")], True).to_html()
        assert "Причина в списке: Абуз" in html
        assert "Внёс: admin" in html

    def test_device_line_reads_naturally(self):
        line = device_line({"platform": "android", "os_version": "15",
                            "device_model": "SM-A366E", "app_version": "Happ/3.25.1"})
        assert line == "Android 15 · SM-A366E (Happ/3.25.1)"

    def test_html_in_username_is_escaped(self):
        """Имя из панели попадает в разметку — без экранирования оно её порвёт."""
        card = revived_card(HWID, {}, [_user("<b>evil</b>")], True)
        assert "&lt;b&gt;evil&lt;/b&gt;" in card.to_html()
        assert _people(card)["cells"][1][0]["text"][0]["button"]["text"] == "<b>evil</b>"  # в rich — как есть
