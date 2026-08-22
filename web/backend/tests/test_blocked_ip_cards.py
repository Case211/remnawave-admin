"""Карточка уведомления о блокировке адреса.

Блокировка ставит DROP на весь трафик с адреса, а по подсети — со всего
диапазона, поэтому в уведомлении важно не «адрес закрыт», а кого это задело.
Разметка проверяется через тот же конвертер, что использует бот: без неё
карточка доедет плоской простынёй.
"""
from datetime import datetime, timedelta, timezone

from shared.tg_rich import html_to_blocks
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


class TestLayout:
    def test_becomes_heading_and_lists(self):
        card = blocked_ip_card(_row(), [_user("a")], pushed_nodes=3, admin_username="admin")
        types = [b.get("type") for b in html_to_blocks(card)]
        assert types[0] == "heading"
        assert "list" in types

    def test_long_list_is_collapsed(self):
        users = [_user(f"u{i}") for i in range(9)]
        card = blocked_ip_card(_row(), users)
        assert "<blockquote expandable>" in card
        assert "И ещё 4" in card


class TestContent:
    def test_shows_who_is_affected(self):
        card = blocked_ip_card(_row(), [_user("a"), _user("b", trial=False)])
        assert "Кого задевает (2)" in card
        assert "пробных: 1" in card

    def test_subnet_is_called_out(self):
        """Подсеть — цена ошибки другая, это должно быть видно сразу."""
        card = blocked_ip_card(_row(ip_cidr="91.201.236.0/24"), [])
        assert "подсеть" in card

    def test_single_address_has_no_subnet_warning(self):
        assert "подсеть" not in blocked_ip_card(_row(), [])

    def test_empty_list_says_so_plainly(self):
        card = blocked_ip_card(_row(), [])
        assert "подключений с этого адреса не было" in card.lower()

    def test_expiry_shown(self):
        assert "Бессрочно" in blocked_ip_card(_row(), [])
        assert "До " in blocked_ip_card(_row(expires_at=FUTURE), [])

    def test_warns_when_no_agents_connected(self):
        """Запись есть, а применить её не на чем — это надо сказать вслух."""
        assert "агентов нет" in blocked_ip_card(_row(), [], pushed_nodes=0)
        assert "Применено на нодах: 2" in blocked_ip_card(_row(), [], pushed_nodes=2)

    def test_html_in_username_is_escaped(self):
        card = blocked_ip_card(_row(), [_user("<b>evil</b>")])
        assert "&lt;b&gt;evil&lt;/b&gt;" in card
