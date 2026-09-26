"""Отложенный шаг цепочки: «предупредить, через 12 ч урезать».

Мера уходит живому клиенту спустя часы после срабатывания, когда всё могло
поменяться, поэтому сторожим три вещи: шаг действительно ждёт (и не
дублируется), перед выполнением перепроверяет нарушение и не перебивает решение
человека, а выполненный или пропущенный шаг честно пишется в журнал.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError

from web.backend.core.automation_engine import AutomationEngine
from web.backend.schemas.automation import AutomationRuleCreate

BASE = dict(
    name="r", category="violations", trigger_type="event",
    trigger_config={"event": "violation.detected"}, action_type="warn_user", action_config={},
)
THROTTLE = {"action_type": "throttle_user", "action_config": {"rate_kbit": 1024, "duration_hours": 24}}


# ── Схема ──


def test_schema_accepts_delayed_step_on_violation():
    rule = AutomationRuleCreate(**{**BASE, "extra_actions": [{**THROTTLE, "delay_hours": 12}]})

    assert rule.extra_actions[0].delay_hours == 12
    assert rule.extra_actions[0].unless_support is True, "пауза по обращению включена по умолчанию"


@pytest.mark.parametrize("override", [
    # Без нарушения в контексте перепроверять нечего
    {"trigger_config": {"event": "user.expired"}, "extra_actions": [{**THROTTLE, "delay_hours": 1}]},
    {"trigger_type": "schedule", "trigger_config": {"interval_minutes": 60},
     "extra_actions": [{**THROTTLE, "delay_hours": 1}]},
    # Порядок в списке — порядок выполнения
    {"extra_actions": [{**THROTTLE, "delay_hours": 12}, {"action_type": "notify", "delay_hours": 1}]},
    {"extra_actions": [{**THROTTLE, "delay_hours": 721}]},
    {"extra_actions": [{**THROTTLE, "delay_hours": -1}]},
])
def test_schema_rejects_bad_delays(override):
    with pytest.raises(ValidationError):
        AutomationRuleCreate(**{**BASE, **override})


# ── Постановка в очередь ──


def _rule(**extra):
    return {"id": 7, "name": "Мягкая мера", "is_enabled": True, "action_type": "warn_user",
            "action_config": {}, "extra_actions": [{**THROTTLE, "delay_hours": 12}], **extra}


@pytest.mark.asyncio
async def test_delayed_step_waits_instead_of_running(monkeypatch):
    engine = AutomationEngine()
    ran = []

    async def fake_single(rule, target_type, target_id, context):
        ran.append(rule["action_type"])
        return "success", {}

    monkeypatch.setattr(engine, "_execute_single", fake_single)
    schedule = AsyncMock(return_value=True)
    with patch("web.backend.core.automation.schedule_pending_action", schedule):
        result, details = await engine._execute_action(_rule(), "user", "u-1", {"violation_id": 5})

    assert ran == ["warn_user"], "урезать сразу нельзя — шаг ждёт"
    assert result == "success" and details["then"][0]["result"] == "scheduled"
    rule_id, action, target, run_at, payload = schedule.await_args.args
    assert (rule_id, action, target) == (7, "chain_step", "u-1")
    assert timedelta(hours=11.9) < run_at - datetime.now(timezone.utc) <= timedelta(hours=12)
    assert payload["action_type"] == "throttle_user" and payload["step"] == 0
    assert payload["context"]["violation_id"] == 5 and payload["unless_support"] is True


@pytest.mark.asyncio
async def test_second_trigger_does_not_queue_second_measure(monkeypatch):
    engine = AutomationEngine()
    monkeypatch.setattr(engine, "_execute_single", AsyncMock(return_value=("success", {})))
    with patch("web.backend.core.automation.schedule_pending_action", AsyncMock(return_value=False)):
        _, details = await engine._execute_action(_rule(), "user", "u-1", {"violation_id": 6})

    assert details["then"][0] == {"action": "throttle_user", "result": "skipped", "details": {"reason": "already_scheduled"}}


@pytest.mark.asyncio
async def test_nothing_waits_when_warning_failed(monkeypatch):
    """Не вышло предупредить — и мера по предупреждению не ставится."""
    engine = AutomationEngine()
    monkeypatch.setattr(engine, "_execute_single", AsyncMock(return_value=("error", {"error": "boom"})))
    schedule = AsyncMock(return_value=True)
    with patch("web.backend.core.automation.schedule_pending_action", schedule):
        await engine._execute_action(_rule(), "user", "u-1", {"violation_id": 5})

    schedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_undelivered_warning_blocks_the_measure(monkeypatch):
    """Предупреждение не дошло — меру не ставим: иначе она снова без объяснений."""
    engine = AutomationEngine()
    monkeypatch.setattr(engine, "_execute_single", AsyncMock(return_value=("skipped", {"reason": "no_recipient"})))
    schedule = AsyncMock(return_value=True)
    with patch("web.backend.core.automation.schedule_pending_action", schedule):
        _, details = await engine._execute_action(_rule(), "user", "u-1", {"violation_id": 5})

    schedule.assert_not_awaited()
    assert details["then"][0]["details"]["reason"] == "warning_not_delivered"


@pytest.mark.asyncio
async def test_already_warned_customer_still_gets_the_measure(monkeypatch):
    engine = AutomationEngine()
    monkeypatch.setattr(engine, "_execute_single", AsyncMock(return_value=("skipped", {"reason": "already_notified"})))
    schedule = AsyncMock(return_value=True)
    with patch("web.backend.core.automation.schedule_pending_action", schedule):
        await engine._execute_action(_rule(), "user", "u-1", {"violation_id": 5})

    schedule.assert_awaited_once()


@pytest.mark.asyncio
async def test_warning_as_chain_step_gates_later_measure(monkeypatch):
    engine = AutomationEngine()

    async def fake_single(rule, target_type, target_id, context):
        if rule["action_type"] == "warn_user":
            return "skipped", {"reason": "mail_failed"}
        return "success", {}

    monkeypatch.setattr(engine, "_execute_single", fake_single)
    rule = _rule(action_type="notify", extra_actions=[
        {"action_type": "warn_user", "action_config": {}},
        {**THROTTLE, "delay_hours": 12},
    ])
    schedule = AsyncMock(return_value=True)
    with patch("web.backend.core.automation.schedule_pending_action", schedule):
        _, details = await engine._execute_action(rule, "user", "u-1", {"violation_id": 5})

    schedule.assert_not_awaited()
    assert details["then"][1]["details"]["reason"] == "warning_not_delivered"


# ── Наступивший шаг ──


def _item(**payload_extra):
    payload = {
        "step": 0, "action_type": "throttle_user", "action_config": {"rate_kbit": 1024},
        "unless_support": True, "target_type": "user", "context": {"violation_id": 5},
        "started_at": "2026-09-26T00:00:00+00:00", **payload_extra,
    }
    return {"id": 11, "rule_id": 7, "action": "chain_step", "target": "u-1", "payload": json.dumps(payload)}


async def _run(engine, rule, blocker=None):
    finish, log = AsyncMock(), AsyncMock()
    with patch("web.backend.core.automation.get_automation_rule_by_id", AsyncMock(return_value=rule)), \
            patch("web.backend.core.automation.finish_pending_action", finish), \
            patch("web.backend.core.automation.write_automation_log", log), \
            patch.object(engine, "_step_blocker", AsyncMock(return_value=blocker)):
        await engine._run_chain_step(_item())
    return finish, log


@pytest.mark.asyncio
async def test_due_step_runs_with_snapshot(monkeypatch):
    engine = AutomationEngine()
    single = AsyncMock(return_value=("success", {"action": "throttle_user"}))
    monkeypatch.setattr(engine, "_execute_single", single)

    finish, log = await _run(engine, _rule())

    sub_rule, target_type, target_id, context = single.await_args.args
    assert sub_rule["action_type"] == "throttle_user" and sub_rule["action_config"] == {"rate_kbit": 1024}
    assert (target_type, target_id, context["violation_id"]) == ("user", "u-1", 5)
    finish.assert_awaited_with(11, "success")
    assert log.await_args.kwargs["details"]["delayed"] is True


@pytest.mark.asyncio
async def test_disabled_rule_cancels_waiting_step(monkeypatch):
    engine = AutomationEngine()
    single = AsyncMock()
    monkeypatch.setattr(engine, "_execute_single", single)

    finish, log = await _run(engine, _rule(is_enabled=False))

    single.assert_not_awaited()
    finish.assert_awaited_with(11, "skipped")
    assert log.await_args.kwargs["details"]["reason"] == "rule_disabled"


@pytest.mark.asyncio
async def test_changed_case_is_skipped_with_reason(monkeypatch):
    engine = AutomationEngine()
    single = AsyncMock()
    monkeypatch.setattr(engine, "_execute_single", single)

    finish, log = await _run(engine, _rule(), blocker="support_contacted")

    single.assert_not_awaited()
    assert log.await_args.kwargs["result"] == "skipped"
    assert log.await_args.kwargs["details"]["reason"] == "support_contacted"


@pytest.mark.asyncio
async def test_pending_loop_hands_chain_steps_to_their_runner():
    engine = AutomationEngine()
    item = _item()
    with patch("web.backend.core.automation.claim_due_actions", AsyncMock(return_value=[item])), \
            patch.object(engine, "_run_chain_step", AsyncMock()) as run:
        await engine._run_pending_actions()

    run.assert_awaited_once_with(item)


# ── Перепроверка ──


class _Conn:
    def __init__(self, violation, status="ACTIVE", throttled=False):
        self.violation = violation
        self.status = status
        self.throttled = throttled

    async def fetchrow(self, sql, *args):
        return self.violation

    async def fetchval(self, sql, *args):
        if "user_throttles" in sql:
            return 1 if self.throttled else None
        return self.status


def _db(conn, whitelisted=False):
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
            return whitelisted, None

    return _DB()


VIOLATION = {"user_uuid": "u-1", "telegram_id": 42, "action_taken": None}
PAYLOAD = {"unless_support": True, "started_at": "2026-09-26T00:00:00+00:00"}


async def _blocker(conn, action="throttle_user", payload=PAYLOAD, whitelisted=False, support=False, context=None):
    with patch("shared.database.db_service", _db(conn, whitelisted)), \
            patch("web.backend.core.automation.support_contact_since", AsyncMock(return_value=support)):
        ctx = {"violation_id": 5} if context is None else context
        return await AutomationEngine()._step_blocker(action, "u-1", payload, ctx)


@pytest.mark.asyncio
async def test_fresh_case_is_allowed():
    assert await _blocker(_Conn(VIOLATION)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("violation, reason", [
    (None, "violation_not_found"),
    ({**VIOLATION, "action_taken": "annulled"}, "violation_annulled"),
    # Оператор уже решил сам — отложенная мера его решение не перебивает
    ({**VIOLATION, "action_taken": "ignore"}, "violation_resolved"),
    ({**VIOLATION, "action_taken": "hard_block"}, "violation_resolved"),
])
async def test_violation_state_stops_the_step(violation, reason):
    assert await _blocker(_Conn(violation)) == reason


@pytest.mark.asyncio
async def test_missing_user_stops_the_step():
    assert await _blocker(_Conn(VIOLATION, status=None)) == "user_not_found"


@pytest.mark.asyncio
async def test_block_on_top_of_block_is_skipped():
    """Иначе «заблокировать на сутки» через сутки разблокировало бы навсегда заблокированного."""
    assert await _blocker(_Conn(VIOLATION, status="DISABLED"), action="block_user") == "already_applied"


@pytest.mark.asyncio
async def test_throttle_does_not_override_operator_limit():
    assert await _blocker(_Conn(VIOLATION, throttled=True)) == "already_applied"


@pytest.mark.asyncio
async def test_whitelisted_customer_is_left_alone():
    assert await _blocker(_Conn(VIOLATION), whitelisted=True) == "whitelisted"


@pytest.mark.asyncio
async def test_support_contact_pauses_the_measure():
    assert await _blocker(_Conn(VIOLATION), support=True) == "support_contacted"


@pytest.mark.asyncio
async def test_external_support_contact_works_without_telegram_id():
    violation = {**VIOLATION, "telegram_id": None}
    support = AsyncMock(return_value=True)
    with patch("shared.database.db_service", _db(_Conn(violation))), \
            patch("web.backend.core.automation.support_contact_since", support):
        result = await AutomationEngine()._step_blocker("throttle_user", "u-1", PAYLOAD, {"violation_id": 5})
    assert result == "support_contacted"
    support.assert_awaited_once_with(None, datetime.fromisoformat(PAYLOAD["started_at"]), user_uuid="u-1")


@pytest.mark.asyncio
async def test_support_lookup_includes_external_events_by_user_uuid():
    from web.backend.core.automation import support_contact_since

    conn = AsyncMock()
    conn.fetchval.return_value = True
    since = datetime.fromisoformat(PAYLOAD["started_at"])
    with patch("shared.database.db_service", _db(conn)):
        assert await support_contact_since(None, since, user_uuid="u-1") is True
    sql, telegram_id, actual_since, user_uuid = conn.fetchval.await_args.args
    assert "external_support_events" in sql
    assert (telegram_id, actual_since, user_uuid) == (None, since, "u-1")


@pytest.mark.asyncio
async def test_support_check_can_be_turned_off():
    payload = {**PAYLOAD, "unless_support": False}
    assert await _blocker(_Conn(VIOLATION), payload=payload, support=True) is None


@pytest.mark.asyncio
async def test_step_without_violation_is_not_rechecked():
    assert await _blocker(_Conn(None), context={}) is None


# ── Тестовый прогон ──


@pytest.mark.asyncio
async def test_dry_run_shows_chain_delays():
    rule = {**_rule(), "trigger_type": "event", "trigger_config": {"event": "violation.detected"}}
    with patch("web.backend.core.automation.get_automation_rule_by_id", AsyncMock(return_value=rule)):
        result = await AutomationEngine().dry_run(7)

    assert result["summary"]["steps"] == [{"action_type": "throttle_user", "delay_hours": 12.0}]
