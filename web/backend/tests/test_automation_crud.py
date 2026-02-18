"""Tests for web.backend.core.automation — CRUD operations and templates.

Covers: AUTOMATION_TEMPLATES, list_automation_rules, get_automation_rules_stats,
get_automation_rule_by_id, create_automation_rule, update_automation_rule,
toggle_automation_rule, delete_automation_rule, increment_trigger_count,
try_acquire_trigger, write_automation_log, get_automation_logs,
get_enabled_rules_by_trigger_type, get_enabled_event_rules.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.automation import (
    AUTOMATION_TEMPLATES,
    list_automation_rules,
    get_automation_rules_stats,
    get_automation_rule_by_id,
    create_automation_rule,
    update_automation_rule,
    toggle_automation_rule,
    delete_automation_rule,
    increment_trigger_count,
    try_acquire_trigger,
    write_automation_log,
    get_automation_logs,
    get_enabled_rules_by_trigger_type,
    get_enabled_event_rules,
)


def _make_db(conn):
    db = MagicMock()
    db.is_connected = True
    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db.acquire.return_value = cm
    return db


def _conn(**kw):
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.fetch = AsyncMock(return_value=[])
    conn.fetchval = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value="")
    for k, v in kw.items():
        setattr(conn, k, v)
    return conn


# ── Templates ──────────────────────────────────────────────────


class TestAutomationTemplates:

    def test_templates_exist(self):
        assert len(AUTOMATION_TEMPLATES) >= 5

    def test_template_structure(self):
        for tpl in AUTOMATION_TEMPLATES:
            assert "id" in tpl
            assert "name" in tpl
            assert "trigger_type" in tpl
            assert "action_type" in tpl

    def test_unique_ids(self):
        ids = [t["id"] for t in AUTOMATION_TEMPLATES]
        assert len(ids) == len(set(ids))


# ── list_automation_rules ──────────────────────────────────────


class TestListAutomationRules:

    async def test_basic_list(self):
        conn = _conn()
        conn.fetchval = AsyncMock(return_value=3)
        conn.fetch = AsyncMock(return_value=[
            {"id": 1, "name": "Rule 1"},
            {"id": 2, "name": "Rule 2"},
        ])
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            rules, total = await list_automation_rules()

        assert total == 3
        assert len(rules) == 2

    async def test_with_filters(self):
        conn = _conn()
        conn.fetchval = AsyncMock(return_value=1)
        conn.fetch = AsyncMock(return_value=[{"id": 1}])
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            rules, total = await list_automation_rules(
                category="violations", trigger_type="event", is_enabled=True,
            )

        assert total == 1

    async def test_pagination(self):
        conn = _conn()
        conn.fetchval = AsyncMock(return_value=50)
        conn.fetch = AsyncMock(return_value=[])
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            rules, total = await list_automation_rules(page=3, per_page=10)

        assert total == 50

    async def test_on_error(self):
        db = MagicMock()
        db.acquire.side_effect = Exception("fail")

        with patch("shared.database.db_service", db):
            rules, total = await list_automation_rules()

        assert rules == []
        assert total == 0


# ── get_automation_rules_stats ────────────────────────────────


class TestGetAutomationRulesStats:

    async def test_returns_stats(self):
        conn = _conn(fetchrow=AsyncMock(return_value={"total_active": 5, "total_triggers": 100}))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            stats = await get_automation_rules_stats()

        assert stats["total_active"] == 5
        assert stats["total_triggers"] == 100

    async def test_on_error(self):
        db = MagicMock()
        db.acquire.side_effect = Exception("fail")

        with patch("shared.database.db_service", db):
            stats = await get_automation_rules_stats()

        assert stats == {"total_active": 0, "total_triggers": 0}


# ── get_automation_rule_by_id ─────────────────────────────────


class TestGetAutomationRuleById:

    async def test_found(self):
        row = {"id": 1, "name": "Rule"}
        conn = _conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await get_automation_rule_by_id(1)

        assert result["name"] == "Rule"

    async def test_not_found(self):
        conn = _conn()
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await get_automation_rule_by_id(999)

        assert result is None


# ── create_automation_rule ────────────────────────────────────


class TestCreateAutomationRule:

    async def test_creates_rule(self):
        row = {"id": 1, "name": "New Rule", "is_enabled": True}
        conn = _conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await create_automation_rule(
                name="New Rule",
                description="Desc",
                is_enabled=True,
                category="violations",
                trigger_type="event",
                trigger_config={"event": "violation.detected"},
                conditions=[],
                action_type="block_user",
                action_config={},
                created_by=1,
            )

        assert result["name"] == "New Rule"

    async def test_on_error(self):
        db = MagicMock()
        db.acquire.side_effect = Exception("fail")

        with patch("shared.database.db_service", db):
            result = await create_automation_rule(
                "n", "d", True, "c", "event", {}, [], "notify", {}, None,
            )

        assert result is None


# ── update_automation_rule ────────────────────────────────────


class TestUpdateAutomationRule:

    async def test_updates_fields(self):
        row = {"id": 1, "name": "Updated", "is_enabled": False}
        conn = _conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await update_automation_rule(1, name="Updated", is_enabled=False)

        assert result["name"] == "Updated"

    async def test_no_fields_delegates_to_get(self):
        with patch("web.backend.core.automation.get_automation_rule_by_id",
                    new_callable=AsyncMock, return_value={"id": 1}) as mock_get:
            result = await update_automation_rule(1)

        assert result == {"id": 1}
        mock_get.assert_awaited_once()

    async def test_json_fields_serialized(self):
        row = {"id": 1, "trigger_config": '{"event":"x"}'}
        conn = _conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await update_automation_rule(
                1, trigger_config={"event": "x"},
            )

        assert result is not None


# ── toggle_automation_rule ────────────────────────────────────


class TestToggleAutomationRule:

    async def test_toggles(self):
        row = {"id": 1, "is_enabled": False}
        conn = _conn(fetchrow=AsyncMock(return_value=row))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await toggle_automation_rule(1)

        assert result["is_enabled"] is False

    async def test_not_found(self):
        conn = _conn()
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await toggle_automation_rule(999)

        assert result is None


# ── delete_automation_rule ────────────────────────────────────


class TestDeleteAutomationRule:

    async def test_deletes(self):
        conn = _conn(execute=AsyncMock(return_value="DELETE 1"))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await delete_automation_rule(1)

        assert result is True

    async def test_not_found(self):
        conn = _conn(execute=AsyncMock(return_value="DELETE 0"))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await delete_automation_rule(999)

        assert result is False


# ── increment_trigger_count ───────────────────────────────────


class TestIncrementTriggerCount:

    async def test_increments(self):
        conn = _conn()
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            await increment_trigger_count(1)

        conn.execute.assert_awaited_once()


# ── try_acquire_trigger ───────────────────────────────────────


class TestTryAcquireTrigger:

    async def test_acquired(self):
        conn = _conn(fetchrow=AsyncMock(return_value={"id": 1}))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await try_acquire_trigger(1, min_interval_seconds=60)

        assert result is True

    async def test_not_acquired(self):
        conn = _conn(fetchrow=AsyncMock(return_value=None))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await try_acquire_trigger(1)

        assert result is False


# ── write_automation_log ──────────────────────────────────────


class TestWriteAutomationLog:

    async def test_writes_entry(self):
        conn = _conn()
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            await write_automation_log(
                rule_id=1, target_type="user", target_id="uuid-1",
                action_taken="block_user", result="success",
                details={"reason": "sharing"},
            )

        conn.execute.assert_awaited_once()


# ── get_automation_logs ───────────────────────────────────────


class TestGetAutomationLogs:

    async def test_basic(self):
        conn = _conn()
        conn.fetchval = AsyncMock(return_value=10)
        conn.fetch = AsyncMock(return_value=[{"id": 1}])
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            logs, total = await get_automation_logs()

        assert total == 10
        assert len(logs) == 1

    async def test_with_filters(self):
        conn = _conn()
        conn.fetchval = AsyncMock(return_value=5)
        conn.fetch = AsyncMock(return_value=[])
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            logs, total = await get_automation_logs(
                rule_id=1, result="success",
                date_from="2026-01-01", date_to="2026-12-31",
            )

        assert total == 5

    async def test_cursor_pagination(self):
        conn = _conn()
        conn.fetchval = AsyncMock(return_value=100)
        conn.fetch = AsyncMock(return_value=[])
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            logs, total = await get_automation_logs(cursor=50)

        assert total == 100


# ── get_enabled_rules_by_trigger_type ─────────────────────────


class TestGetEnabledRulesByTriggerType:

    async def test_returns_rules(self):
        rows = [{"id": 1, "trigger_type": "schedule"}]
        conn = _conn(fetch=AsyncMock(return_value=rows))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await get_enabled_rules_by_trigger_type("schedule")

        assert len(result) == 1


# ── get_enabled_event_rules ──────────────────────────────────


class TestGetEnabledEventRules:

    async def test_returns_matching_rules(self):
        rows = [{"id": 1, "trigger_type": "event"}]
        conn = _conn(fetch=AsyncMock(return_value=rows))
        db = _make_db(conn)

        with patch("shared.database.db_service", db):
            result = await get_enabled_event_rules("violation.detected")

        assert len(result) == 1

    async def test_on_error(self):
        db = MagicMock()
        db.acquire.side_effect = Exception("fail")

        with patch("shared.database.db_service", db):
            result = await get_enabled_event_rules("x")

        assert result == []
