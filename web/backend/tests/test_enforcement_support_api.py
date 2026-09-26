from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest

from web.backend.api.v3 import enforcement
from web.backend.api.v3.deps import ApiKeyUser


USER_UUID = "11111111-2222-3333-4444-555555555555"


class Transaction:
    async def __aenter__(self): return self
    async def __aexit__(self, *_): return False


class Database:
    is_connected = True
    def __init__(self, conn): self.conn = conn
    @asynccontextmanager
    async def acquire(self): yield self.conn


def body():
    return enforcement.SupportEvent(
        user=enforcement.UserIdentity(uuid=USER_UUID),
        ticket=enforcement.TicketReference(provider="generic-helpdesk", external_id="ticket-123"),
    )


def api_user():
    return ApiKeyUser(key_id=1, key_name="support", scopes=["enforcement:support"])


@pytest.mark.asyncio
async def test_support_event_is_idempotent_and_pauses_case(monkeypatch):
    conn = AsyncMock()
    conn.transaction = lambda: Transaction()
    conn.fetchrow.return_value = {"id": 9}
    conn.fetch.side_effect = [[{"uuid": USER_UUID}], [{"id": 31}]]
    monkeypatch.setattr(enforcement, "db_service", Database(conn))
    result = await enforcement.support_event(body(), "message-1", api_user())
    assert result["paused_cases"] == 1
    assert result["case_ids"] == [31]
    assert "paused_for_support" in conn.fetch.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_duplicate_support_event_has_no_second_side_effect(monkeypatch):
    conn = AsyncMock()
    conn.transaction = lambda: Transaction()
    conn.fetchrow.side_effect = [None, {"matched_users": 1, "paused_cases": 1}]
    monkeypatch.setattr(enforcement, "db_service", Database(conn))
    result = await enforcement.support_event(body(), "message-1", api_user())
    assert result == {"accepted": True, "duplicate": True, "matched_users": 1, "paused_cases": 1}
    conn.fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_ambiguous_identity_does_not_pause_any_case(monkeypatch):
    conn = AsyncMock()
    conn.transaction = lambda: Transaction()
    conn.fetchrow.return_value = {"id": 9}
    conn.fetch.return_value = [{"uuid": USER_UUID}, {"uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}]
    monkeypatch.setattr(enforcement, "db_service", Database(conn))
    result = await enforcement.support_event(body(), None, api_user())
    assert result["matched_users"] == 2
    assert result["paused_cases"] == 0
    assert conn.fetch.await_count == 1
