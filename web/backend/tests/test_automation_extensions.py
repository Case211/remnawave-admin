"""Расширения автоматизаций: цепочка действий, «ИЛИ», своя пауза, тихие часы."""
from datetime import datetime

import pytest
from pydantic import ValidationError

from web.backend.core.automation_engine import AutomationEngine, _cooldown_seconds, quiet_window_end
from web.backend.schemas.automation import AutomationRuleCreate

BASE = dict(name="r", category="users", trigger_type="event",
            trigger_config={"event": "violation.detected"}, action_type="notify", action_config={})


def test_quiet_window_across_midnight():
    assert quiet_window_end("23:00", "08:00", datetime(2026, 9, 24, 23, 30)) == datetime(2026, 9, 25, 8, 0)
    assert quiet_window_end("23:00", "08:00", datetime(2026, 9, 24, 3, 0)) == datetime(2026, 9, 24, 8, 0)
    assert quiet_window_end("23:00", "08:00", datetime(2026, 9, 24, 12, 0)) is None


def test_quiet_window_same_day_and_invalid():
    assert quiet_window_end("13:00", "14:00", datetime(2026, 9, 24, 13, 10)) == datetime(2026, 9, 24, 14, 0)
    assert quiet_window_end("", "08:00", datetime(2026, 9, 24, 3, 0)) is None
    assert quiet_window_end("25:00", "08:00", datetime(2026, 9, 24, 3, 0)) is None


def test_cooldown_seconds():
    assert _cooldown_seconds({}, 30) == 30
    assert _cooldown_seconds({"cooldown_minutes": 15}, 30) == 900


def test_conditions_any_and_all():
    engine = AutomationEngine()
    conditions = [{"field": "score", "operator": ">=", "value": 90}, {"field": "is_vpn", "operator": "==", "value": "true"}]
    ctx = {"score": 50, "is_vpn": True}
    assert not engine._evaluate_conditions({"conditions": conditions, "trigger_config": {}}, ctx)
    assert engine._evaluate_conditions({"conditions": conditions, "trigger_config": {"conditions_match": "any"}}, ctx)


@pytest.mark.asyncio
async def test_extra_actions_run_after_primary(monkeypatch):
    engine = AutomationEngine()
    calls = []

    async def fake_single(rule, target_type, target_id, context):
        calls.append(rule["action_type"])
        return "success", {"action": rule["action_type"]}

    monkeypatch.setattr(engine, "_execute_single", fake_single)
    rule = {"id": 1, "action_type": "notify", "action_config": {},
            "extra_actions": [{"action_type": "throttle_user", "action_config": {"rate_kbit": 512}}]}
    result, details = await engine._execute_action(rule, "user", "u1", {})
    assert calls == ["notify", "throttle_user"]
    assert result == "success" and details["then"][0]["action"] == "throttle_user"


@pytest.mark.asyncio
async def test_extra_actions_skipped_when_primary_fails(monkeypatch):
    engine = AutomationEngine()
    calls = []

    async def fake_single(rule, target_type, target_id, context):
        calls.append(rule["action_type"])
        return "error", {"error": "boom"}

    monkeypatch.setattr(engine, "_execute_single", fake_single)
    rule = {"id": 1, "action_type": "notify", "extra_actions": [{"action_type": "block_user", "action_config": {}}]}
    result, _ = await engine._execute_action(rule, "user", "u1", {})
    assert calls == ["notify"] and result == "error"


@pytest.mark.asyncio
async def test_warn_user_needs_violation():
    details = await AutomationEngine()._action_warn_user({}, "user", "u1", {})
    assert details["skipped"] and details["reason"] == "no_violation"


def test_schema_accepts_new_fields():
    rule = AutomationRuleCreate(**{
        **BASE,
        "trigger_config": {"event": "user.expired", "cooldown_minutes": 60, "conditions_match": "any"},
        "action_config": {"quiet_from": "23:00", "quiet_to": "08:00"},
        "extra_actions": [{"action_type": "throttle_user", "action_config": {"rate_kbit": 1024, "duration_hours": 24}}],
    })
    assert rule.extra_actions[0].action_type == "throttle_user"


@pytest.mark.parametrize("patch", [
    {"trigger_config": {"event": "violation.detected", "conditions_match": "maybe"}},
    {"trigger_config": {"event": "violation.detected", "cooldown_minutes": -1}},
    {"extra_actions": [{"action_type": "throttle_user", "action_config": {"bogus": 1}}]},
    {"extra_actions": [{"action_type": "notify", "action_config": {}}] * 6},
])
def test_schema_rejects_bad_extensions(patch):
    with pytest.raises(ValidationError):
        AutomationRuleCreate(**{**BASE, **patch})


def test_sustained_waits_for_minutes():
    from datetime import timedelta

    engine = AutomationEngine()
    targets = [("node", "n1", {"value": 95})]
    cfg = {"for_minutes": 2}
    assert engine._sustained(1, cfg, targets) == []
    # отсчёт идёт с первого превышения; через 2 минуты цель проходит
    engine._threshold_since[(1, "n1")] -= timedelta(minutes=2)
    assert engine._sustained(1, cfg, targets) == targets
    # вернулась ниже порога — отсчёт сбрасывается
    engine._sustained(1, cfg, [])
    assert (1, "n1") not in engine._threshold_since
    assert engine._sustained(1, {}, targets) == targets


@pytest.mark.asyncio
async def test_notify_can_skip_telegram(monkeypatch):
    sent = {}

    async def fake_create_notification(**kwargs):
        sent.update(kwargs)

    monkeypatch.setattr("web.backend.core.notification_service.create_notification", fake_create_notification)
    engine = AutomationEngine()
    await engine._action_notify({"message": "x", "telegram": False, "channels": ["in_app"]}, "system", None, {})
    assert sent["channels"] == ["in_app"]
    await engine._action_notify({"message": "x", "channels": []}, "system", None, {})
    assert sent["channels"] == ["telegram"]
