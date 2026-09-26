"""Мера правила — заодно соучастникам накрутки триалов по HWID.

Без этого связка остаётся рабочей: после меры к одному остальные видят уже
один живой триал и под правило не попадают. Но чужое решение мера не
перебивает: уже заблокированных, ограниченных и клиентов из белого списка не трогаем.
"""
from unittest.mock import AsyncMock, patch

import pytest

from web.backend.core.automation_engine import AutomationEngine
from web.backend.schemas.automation import AutomationRuleCreate


class _Conn:
    def __init__(self, statuses: dict, throttled: set = frozenset()):
        self.statuses = statuses
        self.throttled = throttled

    async def fetchval(self, sql, *args):
        if "user_throttles" in sql:
            return 1 if args[0] in self.throttled else None
        return self.statuses.get(args[0])


def _db(conn, whitelisted: set = frozenset()):
    class _Acquire:
        async def __aenter__(self):
            return conn

        async def __aexit__(self, *exc):
            return False

    class _DB:
        is_connected = True

        def acquire(self):
            return _Acquire()

        async def is_user_violation_whitelisted(self, user_uuid):
            return user_uuid in whitelisted, None

    return _DB()


RULE = {"id": 7, "name": "r", "action_type": "block_user", "action_config": {"with_accomplices": True, "duration_hours": 24}}
CONTEXT = {"violation_id": 5, "user_uuid": "u-main", "username": "main", "trial_accomplices": ["a-ok", "a-blocked", "a-white", "u-main"]}


async def _run(engine, rule, context, conn, whitelisted=frozenset()):
    handler = AsyncMock(return_value={"action": rule["action_type"]})
    with patch.object(engine, f"_action_{rule['action_type']}", handler), \
            patch("shared.database.db_service", _db(conn, whitelisted)):
        result, details = await engine._execute_single(dict(rule), "user", "u-main", dict(context))
    return handler, result, details


@pytest.mark.asyncio
async def test_measure_reaches_accomplices_but_respects_decisions():
    conn = _Conn({"a-ok": "ACTIVE", "a-blocked": "DISABLED", "a-white": "ACTIVE"})
    handler, result, details = await _run(AutomationEngine(), RULE, CONTEXT, conn, whitelisted={"a-white"})

    targets = [c.args[2] for c in handler.await_args_list]
    assert targets == ["u-main", "a-ok"], "сам нарушитель и свободный соучастник; себя вторично — нет"
    assert result == "success"
    assert {r["user_uuid"]: r.get("reason") for r in details["accomplices"]} == {
        "a-ok": None, "a-blocked": "already_applied", "a-white": "whitelisted",
    }
    # Соучастнику — без флага (не рекурсия) и без чужого имени в событиях
    accomplice_call = handler.await_args_list[1]
    assert "with_accomplices" not in accomplice_call.args[0] and accomplice_call.args[0]["duration_hours"] == 24
    assert accomplice_call.args[3]["username"] is None and accomplice_call.args[3]["accomplice_of"] == "u-main"


@pytest.mark.asyncio
async def test_throttle_skips_accomplice_with_own_limit():
    rule = {**RULE, "action_type": "throttle_user", "action_config": {"rate_kbit": 1024, "with_accomplices": True}}
    conn = _Conn({"a-ok": "ACTIVE", "a-blocked": "ACTIVE", "a-white": "ACTIVE"}, throttled={"a-blocked"})
    handler, _, details = await _run(AutomationEngine(), rule, CONTEXT, conn)

    assert [c.args[2] for c in handler.await_args_list] == ["u-main", "a-ok", "a-white"]
    assert next(r for r in details["accomplices"] if r["user_uuid"] == "a-blocked")["reason"] == "already_applied"


@pytest.mark.asyncio
async def test_without_option_only_the_offender_is_touched():
    rule = {**RULE, "action_config": {"duration_hours": 24}}
    handler, _, details = await _run(AutomationEngine(), rule, CONTEXT, _Conn({}))

    assert [c.args[2] for c in handler.await_args_list] == ["u-main"]
    assert "accomplices" not in details


@pytest.mark.asyncio
async def test_failed_accomplice_does_not_stop_the_rest():
    conn = _Conn({"a-ok": "ACTIVE", "a-blocked": "ACTIVE", "a-white": "ACTIVE"})
    engine = AutomationEngine()
    handler = AsyncMock(side_effect=[{"action": "block_user"}, RuntimeError("panel down"), {}, {}])
    with patch.object(engine, "_action_block_user", handler), patch("shared.database.db_service", _db(conn)):
        result, details = await engine._execute_single(dict(RULE), "user", "u-main", dict(CONTEXT))

    assert result == "success"
    assert [r["result"] for r in details["accomplices"]] == ["error", "success", "success"]


def test_schema_accepts_accomplices_option():
    rule = AutomationRuleCreate(
        name="r", category="violations", trigger_type="event", trigger_config={"event": "violation.detected"},
        action_type="block_user", action_config={"with_accomplices": True},
        extra_actions=[{"action_type": "throttle_user", "action_config": {"with_accomplices": True}, "delay_hours": 12}],
    )

    assert rule.action_config["with_accomplices"] is True
