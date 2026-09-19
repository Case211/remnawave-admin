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
    def __init__(self, rows):
        self._rows = rows

    async def fetch(self, *args, **kwargs):
        return self._rows

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
    monkeypatch.setattr(support_alerts, "sla_minutes", lambda: 30)


@pytest.fixture
def sent(monkeypatch):
    calls: list[dict] = []

    async def fake_notify(title, body, *, severity, group_key, ticket_id):
        calls.append({"title": title, "severity": severity, "group_key": group_key, "ticket_id": ticket_id})

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
