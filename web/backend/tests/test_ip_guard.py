"""Сторож адресов: несколько пробных подписок с одного IP.

HWID клиент называет сам и подделывает заголовком, адрес выдаёт провайдер —
поэтому связка по адресу переживает то, что HWID-детект уже не видит. Но за
адресом мобильного оператора стоит CGNAT на весь район, и там несколько разных
людей с пробными — норма; отсюда отдельный порог и тесты на него.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import ip_guard

IP = "91.201.236.46"


def _user(name, trial=True, conns=5, **over):
    user = {
        "uuid": f"uuid-{name}", "username": name, "telegram_id": 100,
        "email": None, "status": "ACTIVE", "is_trial": trial, "is_active": True,
        "conns": conns, "last_seen": None, "created_at": None, "expire_at": None,
    }
    user.update(over)
    return user


def _group(users, mobile=False, **over):
    group = {
        "ip": IP, "accounts": len(users), "is_mobile": mobile,
        "is_proxy": False, "is_hosting": False,
        "asn_org": "PVimpelCom" if mobile else "Rostelecom", "country_code": "RU",
        "users": users,
    }
    group.update(over)
    return group


async def _run(group, *, enabled=True, notified=False, settings=None):
    values = {"violations_ip_trial_guard_enabled": enabled}
    values.update(settings or {})

    db = MagicMock()
    db.is_connected = True
    db.get_shared_ip_accounts = AsyncMock(return_value=[group] if group else [])

    cfg = MagicMock()
    cfg.get = MagicMock(side_effect=lambda key, default=None: values.get(key, default))

    notify = AsyncMock()
    with patch("shared.database.db_service", db), \
         patch("shared.config_service.config_service", cfg), \
         patch.object(ip_guard, "_recently_notified", AsyncMock(return_value=notified)), \
         patch("web.backend.core.notification_service.create_notification", notify):
        reported = await ip_guard.run_once()
    return reported, notify


class TestThresholds:
    @pytest.mark.asyncio
    async def test_two_trials_on_home_ip_reported(self):
        reported, notify = await _run(_group([_user("a"), _user("b")]))
        assert reported == 1
        notify.assert_awaited_once()
        assert notify.await_args.kwargs["source_id"] == IP

    @pytest.mark.asyncio
    async def test_mobile_ip_needs_higher_count(self):
        """CGNAT оператора: двое с пробными за одним адресом — не событие."""
        reported, notify = await _run(_group([_user("a"), _user("b")], mobile=True))
        assert reported == 0
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_mobile_ip_reported_above_its_threshold(self):
        users = [_user(f"u{i}") for i in range(4)]
        reported, _ = await _run(_group(users, mobile=True))
        assert reported == 1

    @pytest.mark.asyncio
    async def test_paid_accounts_do_not_count(self):
        """За домашним адресом живёт квартира — платные подписки это норма."""
        group = _group([_user("a"), _user("b", trial=False), _user("c", trial=False)])
        reported, notify = await _run(group)
        assert reported == 0
        notify.assert_not_awaited()


class TestSilence:
    @pytest.mark.asyncio
    async def test_recently_notified_is_skipped(self):
        reported, notify = await _run(_group([_user("a"), _user("b")]), notified=True)
        assert reported == 0
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disabled_setting_stops_guard(self):
        reported, notify = await _run(_group([_user("a"), _user("b")]), enabled=False)
        assert reported == 0
        notify.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_zero_threshold_disables(self):
        reported, _ = await _run(
            _group([_user("a"), _user("b")]),
            settings={"violations_ip_trial_accounts": 0},
        )
        assert reported == 0


class TestCard:
    def test_card_lists_accounts_and_provider(self):
        card = ip_guard.build_card(
            _group([_user("first", conns=41), _user("second", conns=1)]),
            [_user("first", conns=41), _user("second", conns=1)],
        )
        html = card.to_html()
        assert card.to_blocks()[0] == {"type": "heading", "text": "🌐 " + card.title_text(), "size": 3}
        assert IP in html
        assert "Rostelecom" in html
        people = [blk for blk in card.to_blocks() if blk["type"] == "table"][-1]
        conns = [cell["text"] for cell in people["cells"][0]].index("Подключений")
        assert people["cells"][1][conns]["text"] == "41"  # у первого; последнего входа нет

    def test_mobile_card_says_so(self):
        users = [_user("a"), _user("b")]
        card = ip_guard.build_card(_group(users, mobile=True), users)
        assert "CGNAT" in card.to_html()

    def test_long_list_is_collapsed(self):
        users = [_user(f"u{i}") for i in range(9)]
        card = ip_guard.build_card(_group(users), users)
        tail = next(blk for blk in card.to_blocks() if blk["type"] == "details")
        assert tail["summary"] == "… и ещё 4"

    def test_buttons_carry_ip_actions_inside_the_message(self):
        users = [_user("a"), _user("b")]
        card = ip_guard.build_card(_group(users), users)
        embedded = [btn for blk in card.to_blocks() if blk["type"] == "buttons" for btn in blk["buttons"]]
        data = [btn["callback_data"] for btn in embedded]
        assert data == [f"ipact:block:{IP}", f"ipact:users:{IP}", f"ipact:mute:{IP}"]
        assert embedded[0]["style"] == "danger"
        # в HTML-фолбэке те же кнопки — клавиатурой
        assert [b["callback_data"] for row in card.keyboard()["inline_keyboard"] for b in row] == data

    def test_callback_data_fits_telegram_limit(self):
        """Telegram режет callback_data на 64 байтах — с IPv6 это близко к краю."""
        for row in ip_guard.ip_buttons("2001:0db8:85a3:0000:0000:8a2e:0370:7334"):
            for button in row:
                assert len(button.callback_data.encode()) <= 64
