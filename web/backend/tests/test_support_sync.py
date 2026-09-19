"""Проекция тикетов: очередь строится по производным полям, а не по статусу бота.

Статусы бота (`open`, `answered`, `pending`) отвечают на вопрос «что с тикетом»,
а оператору нужен другой: «чьего хода ждут». Его считает `derive_fields` —
`waiting_since` заполнен ровно тогда, когда последним написал клиент. Здесь
сторож на эту логику и на то, что синк переживает недоступного бота.
"""
from datetime import datetime, timedelta, timezone

import pytest

from web.backend.api.v2 import support
from web.backend.core import support_sync


def _msg(minutes_ago: int, *, admin: bool, text: str = "", mid: int = 1) -> dict:
    return {
        "id": mid,
        "is_from_admin": admin,
        "message_text": text,
        "created_at": (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat(),
    }


def test_waiting_since_set_when_client_wrote_last():
    ticket = {"id": 1, "title": "Не подключается", "status": "open"}
    messages = [_msg(30, admin=False, text="помогите", mid=1), _msg(10, admin=False, text="ау", mid=2)]

    derived = support_sync.derive_fields(ticket, messages)

    assert derived["waiting_since"] is not None
    assert derived["last_message_from"] == "user"
    assert derived["first_response_at"] is None
    assert derived["messages_count"] == 2


def test_waiting_since_cleared_after_operator_reply():
    ticket = {"id": 1, "title": "Возврат", "status": "answered"}
    messages = [_msg(30, admin=False, text="верните деньги", mid=1), _msg(5, admin=True, text="проверяю", mid=2)]

    derived = support_sync.derive_fields(ticket, messages)

    assert derived["waiting_since"] is None
    assert derived["last_message_from"] == "admin"
    assert derived["first_response_at"] is not None


def test_closed_ticket_never_waits():
    ticket = {"id": 1, "title": "Старое", "status": "closed"}
    messages = [_msg(60, admin=False, text="вопрос", mid=1)]

    assert support_sync.derive_fields(ticket, messages)["waiting_since"] is None


def test_search_text_collects_title_and_messages():
    ticket = {"id": 1, "title": "Телевизор LG", "status": "open", "user": {"username": "dmitry"}}
    messages = [_msg(10, admin=False, text="как подключить телевизор", mid=1)]

    search = support_sync.derive_fields(ticket, messages)["search_text"]

    assert "Телевизор LG" in search
    assert "dmitry" in search
    assert "как подключить телевизор" in search


def test_empty_ticket_has_no_derived_timestamps():
    derived = support_sync.derive_fields({"id": 1, "status": "open"}, [])

    assert derived["messages_count"] == 0
    assert derived["last_message_at"] is None
    assert derived["waiting_since"] is None


@pytest.mark.asyncio
async def test_sync_survives_unreachable_bot(monkeypatch):
    class _Conn:
        async def fetch(self, *args, **kwargs):
            return []

        async def execute(self, *args, **kwargs):
            return None

    class _Acquire:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *args):
            return False

    class _DB:
        is_connected = True

        def acquire(self):
            return _Acquire()

    async def boom(*args, **kwargs):
        raise RuntimeError("bot is down")

    monkeypatch.setattr("shared.database.db_service", _DB())
    monkeypatch.setattr("shared.bedolaga_client.bedolaga_client.list_tickets", boom)

    result = await support_sync.sync_tickets()

    assert result == {"scanned": 0, "updated": 0, "skipped": 0}


# ── Очереди ──

def test_queue_wait_us_ignores_snoozed():
    params: list = []
    condition = support._queue_condition(support.QUEUE_WAIT_US, admin_id=1, params=params)

    assert "waiting_since IS NOT NULL" in condition
    assert "snooze_to" in condition
    assert params == []


def test_queue_mine_binds_admin():
    params: list = []
    condition = support._queue_condition(support.QUEUE_MINE, admin_id=42, params=params)

    assert params == [42]
    assert "a.admin_id = $1" in condition


def test_queue_late_binds_sla_threshold():
    params: list = []
    condition = support._queue_condition(support.QUEUE_LATE, admin_id=1, params=params)

    assert len(params) == 1 and isinstance(params[0], datetime)
    assert "waiting_since < $1" in condition
    # порог именно в прошлом — иначе в «просрочены» попали бы все подряд
    assert params[0] < datetime.now(timezone.utc)


def test_queue_all_has_no_filter():
    params: list = []
    assert support._queue_condition(support.QUEUE_ALL, admin_id=1, params=params) == "TRUE"
    assert params == []
