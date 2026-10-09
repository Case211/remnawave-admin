"""Карточка уведомления о блокировке адреса.

Блокировка ставит DROP на весь трафик с адреса, а по подсети — со всего
диапазона, поэтому в уведомлении важно не «адрес закрыт», а кого это задело.
Карточка — shared.tg_card: люди идут таблицей, HTML-фолбэк проверяется тут
же, на него она уходит, если rich не принят.
"""
from datetime import datetime, timedelta, timezone

from web.backend.core.blocked_ip_cards import blocked_ip_card

FUTURE = datetime.now(timezone.utc) + timedelta(days=7)


def _row(**over):
    row = {
        "ip_cidr": "91.201.236.46/32", "reason": "Абуз триала",
        "asn_org": "Rostelecom", "country_code": "RU", "expires_at": None,
    }
    row.update(over)
    return row


def _user(name, trial=True, active=True, conns=5):
    return {
        "user_uuid": f"uuid-{name}", "username": name, "telegram_id": 100,
        "status": "ACTIVE" if active else "DISABLED",
        "is_trial": trial, "is_active": active, "conns": conns, "last_seen": None,
    }


def _html(*args, **kwargs) -> str:
    return blocked_ip_card(*args, **kwargs).to_html()


class TestLayout:
    def test_heading_and_people_table(self):
        card = blocked_ip_card(_row(), [_user("a")], pushed_nodes=3, admin_username="admin")
        types = [blk["type"] for blk in card.to_blocks()]
        assert types[0] == "heading" and types[-1] == "footer"
        people = [blk for blk in card.to_blocks() if blk["type"] == "table"][-1]
        assert people["cells"][0][0]["text"] == "Аккаунт"

    def test_long_list_is_collapsed(self):
        users = [_user(f"u{i}") for i in range(9)]
        tail = next(blk for blk in blocked_ip_card(_row(), users).to_blocks() if blk["type"] == "details")
        assert tail["summary"] == "… и ещё 4"

    def test_reason_is_quoted_with_who_added_it(self):
        quote = next(blk for blk in blocked_ip_card(_row(), [], admin_username="admin").to_blocks()
                     if blk["type"] == "blockquote")
        assert quote["credit"] == "admin"


class TestContent:
    def test_shows_who_is_affected(self):
        html = _html(_row(), [_user("a"), _user("b", trial=False)])
        assert "Кого задевает · 2" in html
        assert "пробных: 1" in html

    def test_subnet_is_called_out(self):
        """Подсеть — цена ошибки другая, это должно быть видно сразу."""
        assert "подсеть" in _html(_row(ip_cidr="91.201.236.0/24"), [])

    def test_single_address_has_no_subnet_warning(self):
        assert "подсеть" not in _html(_row(), [])

    def test_empty_list_says_so_plainly(self):
        assert "подключений с этого адреса не было" in _html(_row(), []).lower()

    def test_expiry_shown(self):
        assert "Срок: бессрочно" in _html(_row(), [])
        assert "<tg-time" in _html(_row(expires_at=FUTURE), [])

    def test_warns_when_no_agents_connected(self):
        """Запись есть, а применить её не на чем — это надо сказать вслух."""
        assert "агентов нет" in _html(_row(), [], pushed_nodes=0)
        assert "Применено на нодах: <b>2</b>" in _html(_row(), [], pushed_nodes=2)

    def test_html_in_username_is_escaped(self):
        assert "&lt;b&gt;evil&lt;/b&gt;" in _html(_row(), [_user("<b>evil</b>")])
