"""Алерты поддержки: сказать один раз и не забыть сказать снова.

Просроченное обращение висит часами, и наивная проверка раз в минуту залила бы
оператора одинаковыми уведомлениями. Дедуп держится на отметке в памяти — но
она обязана сниматься, как только на тикет ответили, иначе следующая просрочка
пройдёт молча. Здесь сторож ровно на эту пару свойств.
"""
from datetime import datetime, timedelta, timezone

import pytest

from web.backend.core import support_alerts, support_ws_client


class _Conn:
    """Эмулирует два запроса проверки: выборку новых просрочек и «кто ещё ждёт».

    Первый исключает уже объявленные тикеты (это делает SQL, а не Python),
    второй отвечает, какие из объявленных всё ещё висят без ответа.
    """

    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, sql, *args, **kwargs):
        if "waiting_since < $1" in sql:
            alerted = set(args[1] or [])
            return [row for row in self._rows if row["id"] not in alerted]
        known = set(args[0] or [])
        return [{"id": row["id"]} for row in self._rows if row["id"] in known]

    async def fetchrow(self, *args, **kwargs):
        return self._rows[0] if self._rows else None


class _DB:
    is_connected = True

    def __init__(self, rows):
        self._rows = rows

    def acquire(self):
        conn = _Conn(self._rows)

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *args):
                return False

        return _Ctx()


def _row(ticket_id: int, minutes: int) -> dict:
    return {
        "id": ticket_id,
        "title": "Не подключается",
        "customer_name": "Алексей",
        "waiting_since": datetime.now(timezone.utc) - timedelta(minutes=minutes),
    }


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    support_alerts._sla_alerted.clear()
    monkeypatch.setattr(support_alerts, "alerts_enabled", lambda: True)
    monkeypatch.setattr(support_alerts, "sla_enabled", lambda: True)
    monkeypatch.setattr(support_alerts, "sla_minutes", lambda: 30)


@pytest.fixture
def sent(monkeypatch):
    calls: list[dict] = []

    async def fake_notify(
        title, body, *, severity, group_key, ticket_id, telegram_body=None, attachment=None,
        bot_user_id=None, username=None,
    ):
        calls.append({
            "title": title,
            "body": body,
            "severity": severity,
            "group_key": group_key,
            "ticket_id": ticket_id,
            "telegram_body": telegram_body,
            "attachment": attachment,
        })

    monkeypatch.setattr(support_alerts, "_notify", fake_notify)
    return calls


@pytest.mark.asyncio
async def test_breach_alerts_once(monkeypatch, sent):
    monkeypatch.setattr("shared.database.db_service", _DB([_row(11, 45)]))

    assert await support_alerts.check_sla_breaches() == 1
    assert await support_alerts.check_sla_breaches() == 0
    assert len(sent) == 1
    assert sent[0]["group_key"] == "support_sla_11"
    assert sent[0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_alert_repeats_after_ticket_was_answered(monkeypatch, sent):
    monkeypatch.setattr("shared.database.db_service", _DB([_row(11, 45)]))
    await support_alerts.check_sla_breaches()

    # ответили — тикет ушёл из выборки, отметка должна сняться
    monkeypatch.setattr("shared.database.db_service", _DB([]))
    await support_alerts.check_sla_breaches()
    assert support_alerts._sla_alerted == set()

    # клиент написал снова и снова ждёт — предупреждаем ещё раз
    monkeypatch.setattr("shared.database.db_service", _DB([_row(11, 40)]))
    assert await support_alerts.check_sla_breaches() == 1
    assert len(sent) == 2


@pytest.mark.asyncio
async def test_alerts_can_be_switched_off(monkeypatch, sent):
    monkeypatch.setattr(support_alerts, "alerts_enabled", lambda: False)
    monkeypatch.setattr("shared.database.db_service", _DB([_row(11, 90)]))

    assert await support_alerts.check_sla_breaches() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_sla_switch_off_silences_breaches(monkeypatch, sent):
    """Контроль срока выключен — о просрочке не сообщаем вовсе."""
    monkeypatch.setattr(support_alerts, "sla_enabled", lambda: False)
    monkeypatch.setattr("shared.database.db_service", _DB([_row(11, 120)]))

    assert await support_alerts.check_sla_breaches() == 0
    assert sent == []


@pytest.mark.asyncio
async def test_new_ticket_alert_respects_setting(monkeypatch, sent):
    monkeypatch.setattr(support_alerts, "new_ticket_alerts_enabled", lambda: False)
    await support_alerts.notify_new_ticket({"id": 5, "title": "Вопрос"})
    assert sent == []

    monkeypatch.setattr(support_alerts, "new_ticket_alerts_enabled", lambda: True)
    await support_alerts.notify_new_ticket({"id": 5, "title": "Вопрос", "customer_name": "Ирина"})
    assert sent and sent[0]["group_key"] == "support_new_5"


# ── Подписка на события бота ──

@pytest.mark.asyncio
async def test_message_event_syncs_ticket(monkeypatch):
    synced: list[int] = []

    async def fake_sync(ticket_id):
        synced.append(ticket_id)
        return True

    monkeypatch.setattr("web.backend.core.support_sync.sync_ticket", fake_sync)

    assert await support_ws_client.handle_event("ticket.message_added", {"ticket_id": 42}) is True
    assert synced == [42]


@pytest.mark.asyncio
async def test_unknown_event_is_ignored(monkeypatch):
    async def fail(ticket_id):
        raise AssertionError("синк не должен вызываться")

    monkeypatch.setattr("web.backend.core.support_sync.sync_ticket", fail)
    assert await support_ws_client.handle_event("user.created", {"user_id": 1}) is False


@pytest.mark.asyncio
async def test_event_without_ticket_id_is_ignored(monkeypatch):
    async def fail(ticket_id):
        raise AssertionError("синк не должен вызываться")

    monkeypatch.setattr("web.backend.core.support_sync.sync_ticket", fail)
    assert await support_ws_client.handle_event("ticket.created", {"foo": "bar"}) is False


@pytest.mark.asyncio
async def test_created_event_triggers_alert(monkeypatch):
    alerted: list[dict] = []

    async def fake_sync(ticket_id):
        return False  # бот недоступен — проекция не обновилась, алерт всё равно нужен

    async def fake_alert(ticket):
        alerted.append(ticket)

    monkeypatch.setattr("web.backend.core.support_sync.sync_ticket", fake_sync)
    monkeypatch.setattr("web.backend.core.support_alerts.notify_new_ticket", fake_alert)

    await support_ws_client.handle_event("ticket.created", {"ticket_id": 7, "title": "Оплата"})

    assert alerted and alerted[0]["title"] == "Оплата"


def test_ws_url_built_from_api_url(monkeypatch):
    class _Settings:
        bedolaga_api_url = "https://bot.example.com/api"
        bedolaga_api_token = "secret-token"

    monkeypatch.setattr("web.backend.core.config.get_web_settings", lambda: _Settings())
    assert support_ws_client._ws_url() == "wss://bot.example.com/api/ws?token=secret-token"


def test_ws_url_is_none_without_settings(monkeypatch):
    class _Settings:
        bedolaga_api_url = ""
        bedolaga_api_token = ""

    monkeypatch.setattr("web.backend.core.config.get_web_settings", lambda: _Settings())
    assert support_ws_client._ws_url() is None


def test_scrub_hides_token_from_logs():
    """websockets печатает полный URI в ошибках — токен туда попасть не должен."""
    message = "server rejected WebSocket connection: wss://bot/ws?token=super-secret HTTP 403"
    scrubbed = support_ws_client._scrub(message)
    assert "super-secret" not in scrubbed
    assert "token=***" in scrubbed


# ── Ссылка на обращение в Telegram ──


def _panel_url(monkeypatch, value: str):
    class _Config:
        def get(self, key, default=None):
            return value if key == "web_panel_public_url" else default

    monkeypatch.setattr("shared.config_service.config_service", _Config())


def test_alert_carries_button_to_the_ticket(monkeypatch):
    _panel_url(monkeypatch, "https://panel.example.com/")

    markup = support_alerts._ticket_button(42)

    assert markup["inline_keyboard"][0][0]["url"] == "https://panel.example.com/support?ticket=42"


def test_no_link_without_public_url(monkeypatch):
    # Пустая настройка — ссылок нет, но действия остаются: они работают без панели.
    _panel_url(monkeypatch, "")

    flat = [b for row in support_alerts._ticket_button(42)["inline_keyboard"] for b in row]
    assert not any(b.get("url") for b in flat)
    assert any(b.get("callback_data") == "sact:take:42" for b in flat)


def test_no_link_for_plain_http(monkeypatch):
    # Telegram отклоняет http-кнопку вместе со всем сообщением — лучше без неё.
    _panel_url(monkeypatch, "http://panel.example.com")

    flat = [b for row in support_alerts._ticket_button(42)["inline_keyboard"] for b in row]
    assert not any(b.get("url") for b in flat)


# ── Карточка нового обращения ──


@pytest.mark.asyncio
async def test_new_ticket_alert_carries_the_card(monkeypatch, sent):
    """В чат уходит не строка «имя: тема», а кто написал, о чём и с чем пришёл."""
    async def row(ticket_id):
        return {
            "id": ticket_id,
            "title": "Тест тикет-системы",
            "customer_name": "Илья",
            "telegram_id": 366945364,
            "bot_user_id": 667,
            "last_message_text": "Привет, это тест тикет системы админки и вложения",
            "attachments": 1,
        }

    async def context(bot_user_id):
        return (
            [("📱", "Username", "@ispanec_nn"), ("🆔", "Telegram ID", "366945364"),
             ("💳", "Подписка", "активна · до 2026-10-19"), ("💰", "Баланс", "100 ₽")],
            {"username": "ispanec_nn", "telegram_id": 366945364},
        )

    async def last_message(ticket_id):
        return {"id": 9, "has_media": True, "media_type": "photo", "media_items": None}

    async def attachment(ticket_id, message):
        return {"content": b"jpeg", "kind": "photo", "name": "ticket-65.jpg"}

    monkeypatch.setattr(support_alerts, "_ticket_row", row)
    monkeypatch.setattr(support_alerts, "_customer_fields", context)
    monkeypatch.setattr(support_alerts, "_last_message", last_message)
    monkeypatch.setattr(support_alerts, "_attachment", attachment)
    monkeypatch.setattr(support_alerts, "new_ticket_alerts_enabled", lambda: True)

    await support_alerts.notify_new_ticket({"id": 65})

    card = sent[0]["telegram_body"]
    assert "Илья" in card
    assert "Тест тикет-системы" in card
    assert "тест тикет системы админки" in card
    assert "Telegram ID:</b> 366945364" in card, "оператору нужен id, а не только имя"
    assert "Вложений" not in card, "число вложений в карточке не нужно — файл приходит следом"
    assert sent[0]["attachment"]["kind"] == "photo", "скриншот клиента уходит файлом"
    assert "Баланс:</b> 100 ₽" in card
    # Колокольчик в панели остаётся коротким — там рядом сама карточка.
    assert sent[0]["body"] == "Илья: Тест тикет-системы"


@pytest.mark.asyncio
async def test_new_ticket_alert_survives_silent_bot(monkeypatch, sent):
    """Бот не ответил про клиента — уведомление всё равно уходит."""
    async def row(ticket_id):
        return {"id": ticket_id, "title": "Не работает", "customer_name": "Пётр", "bot_user_id": 5}

    async def no_context(bot_user_id):
        return [], {}

    monkeypatch.setattr(support_alerts, "_ticket_row", row)
    monkeypatch.setattr(support_alerts, "_customer_fields", no_context)
    monkeypatch.setattr(support_alerts, "new_ticket_alerts_enabled", lambda: True)

    await support_alerts.notify_new_ticket({"id": 7})

    assert "Пётр" in sent[0]["telegram_body"]
    assert "кабинет" in sent[0]["telegram_body"]


def test_card_escapes_customer_text():
    """Имя и текст приходят от клиента: разметку в них ломать нельзя."""
    assert support_alerts._short("  много   пробелов  ") == "много пробелов"
    assert len(support_alerts._short("x" * 400)) == 300


# ── Ответ клиента в открытом обращении ──


def _reply_row(**extra):
    row = {
        "id": 65,
        "title": "Не подключается",
        "customer_name": "Игорь",
        "bot_user_id": 667,
        "status": "answered",
        "last_message_from": "user",
        "last_message_text": "всё ещё не работает",
        "last_message_at": datetime.now(timezone.utc).isoformat(),
        "attachments": 0,
    }
    row.update(extra)
    return row


@pytest.fixture(autouse=True)
def _forget_replies():
    support_alerts._reply_alerted.clear()
    yield
    support_alerts._reply_alerted.clear()


@pytest.mark.asyncio
async def test_customer_reply_alerts_once(monkeypatch, sent):
    row = _reply_row()

    async def fetch(ticket_id):
        return row

    monkeypatch.setattr(support_alerts, "_ticket_row", fetch)
    monkeypatch.setattr(support_alerts, "new_message_alerts_enabled", lambda: True)

    await support_alerts.notify_customer_reply({"id": 65})
    await support_alerts.notify_customer_reply({"id": 65})

    assert len(sent) == 1, "событие бота и синк не должны дублировать уведомление"
    assert "всё ещё не работает" in sent[0]["telegram_body"]
    assert sent[0]["title"] == "Ответ клиента по #65"


@pytest.mark.asyncio
async def test_own_reply_does_not_alert(monkeypatch, sent):
    async def fetch(ticket_id):
        return _reply_row(last_message_from="admin")

    monkeypatch.setattr(support_alerts, "_ticket_row", fetch)
    monkeypatch.setattr(support_alerts, "new_message_alerts_enabled", lambda: True)

    await support_alerts.notify_customer_reply({"id": 65})

    assert sent == []


@pytest.mark.asyncio
async def test_closed_ticket_does_not_alert(monkeypatch, sent):
    async def fetch(ticket_id):
        return _reply_row(status="closed")

    monkeypatch.setattr(support_alerts, "_ticket_row", fetch)
    monkeypatch.setattr(support_alerts, "new_message_alerts_enabled", lambda: True)

    await support_alerts.notify_customer_reply({"id": 65})

    assert sent == []


@pytest.mark.asyncio
async def test_old_reply_does_not_alert(monkeypatch, sent):
    # Синк после простоя переберёт всю очередь — вчерашние ответы не новость.
    stale = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()

    async def fetch(ticket_id):
        return _reply_row(last_message_at=stale)

    monkeypatch.setattr(support_alerts, "_ticket_row", fetch)
    monkeypatch.setattr(support_alerts, "new_message_alerts_enabled", lambda: True)

    await support_alerts.notify_customer_reply({"id": 65})

    assert sent == []


@pytest.mark.asyncio
async def test_reply_alert_respects_setting(monkeypatch, sent):
    async def fetch(ticket_id):
        return _reply_row()

    monkeypatch.setattr(support_alerts, "_ticket_row", fetch)
    monkeypatch.setattr(support_alerts, "new_message_alerts_enabled", lambda: False)

    await support_alerts.notify_customer_reply({"id": 65})

    assert sent == []


def test_card_has_no_attachment_counter():
    """Число вложений не пишем: файл приходит следом и говорит сам за себя."""
    card = support_alerts._card([("👤", "Клиент", "Илья")], "текст")

    assert "Вложений" not in card
    assert "<blockquote expandable>текст</blockquote>" in card
    assert card.startswith("   👤 <b>Клиент:</b>"), "поля идут списком rich-разметки"


def test_keyboard_offers_actions_without_panel_url(monkeypatch):
    """Кнопки действий работают и без публичного адреса — ссылки просто пропадают."""
    monkeypatch.setattr(support_alerts, "_panel_base", lambda: "")

    keyboard = support_alerts._ticket_button(65, bot_user_id=667, username="ispanec_nn")
    flat = [button for row in keyboard["inline_keyboard"] for button in row]

    assert any(b.get("callback_data") == "sact:take:65" for b in flat)
    assert any(b.get("callback_data") == "sact:close:65" for b in flat)
    assert any(b.get("url") == "https://t.me/ispanec_nn" for b in flat)
    assert not any("/support?ticket=" in (b.get("url") or "") for b in flat)


def test_keyboard_links_into_panel(monkeypatch):
    monkeypatch.setattr(support_alerts, "_panel_base", lambda: "https://panel.example.com")

    keyboard = support_alerts._ticket_button(65, bot_user_id=667, username=None)
    flat = [button for row in keyboard["inline_keyboard"] for button in row]

    assert any(b.get("url") == "https://panel.example.com/support?ticket=65" for b in flat)
    assert any(b.get("url") == "https://panel.example.com/bedolaga/customers/667" for b in flat)
    # Личку без username не предлагаем: Telegram отклонит такую ссылку.
    assert not any("t.me" in (b.get("url") or "") for b in flat)
