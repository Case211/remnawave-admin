"""Автоответ в часы тишины: главное — он не выдаёт себя за ответ оператора.

Робот отвечает от имени админа, поэтому без отметки очередь решила бы, что
обращению уже ответили: ожидание обнулилось бы и ночной тикет уехал бы из «в
обработке». Здесь сторож ровно на это, плюс на окно через полночь и на то, что
первый проход синка не разошлёт роботов по всей истории обращений.
"""
from datetime import datetime, timedelta, timezone

import pytest

from web.backend.core import support_auto_reply, support_sync


def _config(monkeypatch, **values):
    defaults = {
        "support_auto_reply_enabled": True,
        "support_auto_reply_text": "Обращение №{id} принято, оператор на связи с {until}.",
        "support_quiet_hours_start": "22:00",
        "support_quiet_hours_end": "08:00",
        "support_quiet_hours_tz": "UTC",
    }
    defaults.update(values)

    class _Config:
        def get(self, key, default=None):
            return defaults.get(key, default)

    monkeypatch.setattr("shared.config_service.config_service", _Config())


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, 20, hour, minute, tzinfo=timezone.utc)


# ── Окно тишины ──


def test_quiet_window_wraps_over_midnight(monkeypatch):
    _config(monkeypatch)

    assert support_auto_reply.in_quiet_hours(_at(23, 30)) is True
    assert support_auto_reply.in_quiet_hours(_at(3)) is True
    assert support_auto_reply.in_quiet_hours(_at(12)) is False
    assert support_auto_reply.in_quiet_hours(_at(8)) is False


def test_daytime_window_does_not_wrap(monkeypatch):
    _config(monkeypatch, support_quiet_hours_start="13:00", support_quiet_hours_end="14:00")

    assert support_auto_reply.in_quiet_hours(_at(13, 30)) is True
    assert support_auto_reply.in_quiet_hours(_at(15)) is False


def test_equal_bounds_disable_quiet_hours(monkeypatch):
    # Одинаковые границы читаются как «тишины нет», а не как «тишина всегда».
    _config(monkeypatch, support_quiet_hours_start="09:00", support_quiet_hours_end="09:00")

    assert support_auto_reply.in_quiet_hours(_at(9)) is False


def test_unknown_zone_falls_back_to_utc(monkeypatch):
    _config(monkeypatch, support_quiet_hours_tz="Mars/Olympus")

    assert support_auto_reply.in_quiet_hours(_at(23)) is True


def test_reply_text_fills_number_and_hour(monkeypatch):
    _config(monkeypatch)

    assert support_auto_reply.reply_text(77) == "Обращение №77 принято, оператор на связи с 08:00."


# ── Отправка ──


class _Conn:
    def __init__(self, claimed: bool = True):
        self.claimed = claimed
        self.queries: list[str] = []

    async def fetchrow(self, sql, *args):
        self.queries.append(sql)
        return {"ticket_id": args[0]} if self.claimed else None

    async def fetch(self, sql, *args):
        self.queries.append(sql)
        return []

    async def execute(self, sql, *args):
        self.queries.append(sql)
        return "UPDATE 1"


def _db(conn):
    class _Acquire:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *args):
            return False

    class _DB:
        is_connected = True

        def acquire(self):
            return _Acquire()

    return _DB()


@pytest.fixture
def sent(monkeypatch):
    calls: list[tuple[int, str]] = []

    async def fake_reply(ticket_id, text, *args, **kwargs):
        calls.append((ticket_id, text))
        return {"message": {"id": 555}}

    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.reply_ticket", fake_reply)

    async def noop_sync(ticket_id):
        return True

    async def noop_notify(*args, **kwargs):
        return None

    monkeypatch.setattr(support_sync, "sync_ticket", noop_sync)
    monkeypatch.setattr("web.backend.core.support_alerts.notify_auto_reply", noop_notify)
    return calls


def _fresh_ticket(**extra) -> dict:
    ticket = {
        "id": 42,
        "status": "open",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "messages": [{"id": 1, "is_from_admin": False}],
    }
    ticket.update(extra)
    return ticket


@pytest.mark.asyncio
async def test_robot_answers_at_night(monkeypatch, sent):
    _config(monkeypatch)
    monkeypatch.setattr("shared.database.db_service", _db(_Conn()))
    monkeypatch.setattr(support_auto_reply, "in_quiet_hours", lambda moment=None: True)

    assert await support_auto_reply.maybe_auto_reply(_fresh_ticket()) is True
    assert sent[0][0] == 42


@pytest.mark.asyncio
async def test_no_robot_during_working_hours(monkeypatch, sent):
    _config(monkeypatch)
    monkeypatch.setattr("shared.database.db_service", _db(_Conn()))
    monkeypatch.setattr(support_auto_reply, "in_quiet_hours", lambda moment=None: False)

    assert await support_auto_reply.maybe_auto_reply(_fresh_ticket()) is False
    assert sent == []


@pytest.mark.asyncio
async def test_old_tickets_are_left_alone(monkeypatch, sent):
    # Первый проход синка видит всю историю: робот не должен писать всем подряд.
    _config(monkeypatch)
    monkeypatch.setattr("shared.database.db_service", _db(_Conn()))
    monkeypatch.setattr(support_auto_reply, "in_quiet_hours", lambda moment=None: True)
    old = _fresh_ticket(created_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat())

    assert await support_auto_reply.maybe_auto_reply(old) is False
    assert sent == []


@pytest.mark.asyncio
async def test_no_robot_after_operator_reply(monkeypatch, sent):
    _config(monkeypatch)
    monkeypatch.setattr("shared.database.db_service", _db(_Conn()))
    monkeypatch.setattr(support_auto_reply, "in_quiet_hours", lambda moment=None: True)
    answered = _fresh_ticket(messages=[{"id": 1, "is_from_admin": False}, {"id": 2, "is_from_admin": True}])

    assert await support_auto_reply.maybe_auto_reply(answered) is False
    assert sent == []


@pytest.mark.asyncio
async def test_second_call_does_not_double_reply(monkeypatch, sent):
    # Бронь занята — событие пришло дважды, клиент получает робота один раз.
    _config(monkeypatch)
    monkeypatch.setattr("shared.database.db_service", _db(_Conn(claimed=False)))
    monkeypatch.setattr(support_auto_reply, "in_quiet_hours", lambda moment=None: True)

    assert await support_auto_reply.maybe_auto_reply(_fresh_ticket()) is False
    assert sent == []


@pytest.mark.asyncio
async def test_disabled_setting_keeps_robot_silent(monkeypatch, sent):
    _config(monkeypatch, support_auto_reply_enabled=False)
    monkeypatch.setattr("shared.database.db_service", _db(_Conn()))

    assert await support_auto_reply.maybe_auto_reply(_fresh_ticket()) is False
    assert sent == []


# ── Главное: очередь не считает робота оператором ──


def _msg(minutes_ago: int, *, admin: bool, mid: int) -> dict:
    return {
        "id": mid,
        "is_from_admin": admin,
        "message_text": "",
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
    }


def test_auto_reply_keeps_ticket_waiting_for_us():
    ticket = {"id": 1, "title": "Не подключается", "status": "answered"}
    messages = [_msg(40, admin=False, mid=1), _msg(39, admin=True, mid=2)]

    derived = support_sync.derive_fields(ticket, messages, auto_ids={2})

    assert derived["waiting_since"] is not None, "робот не считается ответом оператора"
    assert derived["first_response_at"] is None, "метрика реакции не должна ловить автоответ"
    assert derived["messages_count"] == 2, "в ленте автоответ остаётся"


def test_real_reply_still_clears_waiting():
    ticket = {"id": 1, "title": "Не подключается", "status": "answered"}
    messages = [_msg(40, admin=False, mid=1), _msg(39, admin=True, mid=2)]

    derived = support_sync.derive_fields(ticket, messages, auto_ids=set())

    assert derived["waiting_since"] is None
    assert derived["first_response_at"] is not None
