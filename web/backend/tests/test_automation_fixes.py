"""Автоматизации: срабатывание по цели и по падению, cron по часам панели,
условия во всех типах правил, экранирование и проверка правил."""
import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from web.backend.core.automation import AUTOMATION_TEMPLATES
from web.backend.core.automation_engine import AutomationEngine, cron_due, cron_matches
from web.backend.schemas.automation import AutomationRuleCreate


def _load_migration():
    """Миграция 0117 ради чистой функции _shift_cron.

    CI ставит только web/backend/requirements.txt, без alembic: папка alembic/
    репозитория видна тогда пустым пакетом, и `from alembic import op` падает.
    Функции op не нужен — на время загрузки подставляем заглушку.
    """
    path = Path(__file__).resolve().parents[3] / "alembic" / "versions" / "20260924_0117_automation_fixes.py"
    spec = importlib.util.spec_from_file_location("m0117", path)
    module = importlib.util.module_from_spec(spec)
    stub = types.ModuleType("alembic")
    stub.op = MagicMock()
    with patch.dict(sys.modules, {"alembic": stub}):
        spec.loader.exec_module(module)
    return module


# ── CRON ──────────────────────────────────────────────────────────────

def test_cron_due_catches_a_skipped_minute():
    now = datetime(2026, 9, 24, 9, 1, 30)
    # Проверка была в 08:59:50, следующая пришлась на 09:01 — 09:00 не потеряно
    assert cron_due("0 9 * * *", now - timedelta(seconds=100), now)
    assert not cron_due("0 9 * * *", now - timedelta(seconds=30), now)


def test_cron_sunday_as_seven_and_range_steps():
    sunday = datetime(2026, 9, 27, 10, 0)
    assert cron_matches("0 10 * * 7", sunday)
    assert cron_matches("0 10 * * 0", sunday)
    assert cron_matches("0 8-12/2 * * *", sunday)
    assert not cron_matches("0 9-12/2 * * *", sunday)


def test_migration_shifts_utc_cron_into_panel_zone():
    m = _load_migration()
    assert m._shift_cron("0 5 * * *", 3) == "0 8 * * *"
    assert m._shift_cron("30 22 * * 1", 3) == "30 1 * * 2"   # через полночь — на следующий день
    assert m._shift_cron("*/5 * * * *", 3) == "*/5 * * * *"
    assert m._shift_cron("0 22 1 * *", 3) is None           # день месяца через полночь — не трогаем


# ── События ───────────────────────────────────────────────────────────

async def _process(engine, rule, event, payload):
    lock = AsyncMock(return_value=True)
    with patch("web.backend.core.automation.try_acquire_target", lock), \
            patch("web.backend.core.automation.write_automation_log", AsyncMock()), \
            patch("web.backend.core.webhook_security.fire_event", MagicMock()), \
            patch.object(engine, "_execute_action", AsyncMock(return_value=("success", {}))):
        await engine._process_event_rule(rule, event, payload)
    return lock


@pytest.mark.asyncio
async def test_lock_is_per_target_not_per_rule():
    rule = {"id": 1, "name": "r", "action_type": "block_user", "trigger_config": {}, "conditions": []}
    lock = await _process(AutomationEngine(), rule, "violation.detected", {"user_uuid": "u-1", "score": 90})
    assert lock.await_args.args == (1, "u-1", 30)


@pytest.mark.asyncio
async def test_offline_node_fires_once_per_outage():
    rule = {"id": 2, "name": "r", "action_type": "notify",
            "trigger_config": {"offline_minutes": 5}, "conditions": []}
    lock = await _process(AutomationEngine(), rule, "node.went_offline", {
        "node_uuid": "n-1", "offline_minutes": 12, "offline_since": "2026-09-24T08:00:00+00:00",
    })
    rule_id, key, seconds = lock.await_args.args
    assert key == "n-1@2026-09-24T08:00:00+00:00" and seconds >= 86400


@pytest.mark.asyncio
async def test_disabled_nodes_are_not_offline():
    engine = AutomationEngine()
    nodes = [
        {"uuid": "off", "name": "down", "is_connected": False, "is_disabled": False},
        {"uuid": "dis", "name": "manual", "is_connected": False, "is_disabled": True},
    ]
    with patch("web.backend.core.api_helper.fetch_nodes_from_api", AsyncMock(return_value=nodes)), \
            patch("web.backend.core.automation.get_enabled_event_rules", AsyncMock(return_value=[])), \
            patch("web.backend.core.webhook_security.fire_event", MagicMock()), \
            patch.object(engine, "handle_event", AsyncMock()) as handle:
        await engine._detect_events()
    assert [c.args[1]["node_uuid"] for c in handle.await_args_list] == ["off"]


def test_offline_since_comes_from_panel_status_change():
    changed = (datetime.now(timezone.utc) - timedelta(hours=2)).replace(microsecond=0)
    since = AutomationEngine._offline_since({"last_status_change": changed.isoformat().replace("+00:00", "Z")})
    assert since == changed
    # Время из будущего (часы панели убежали) — считаем от «сейчас»
    future = AutomationEngine._offline_since({"last_status_change": "2999-01-01T00:00:00Z"})
    assert future <= datetime.now(timezone.utc)


# ── Условия и сообщения ───────────────────────────────────────────────

def test_old_condition_field_names_still_work():
    rule = {"conditions": [{"field": "online_count", "operator": ">=", "value": 100}]}
    assert AutomationEngine()._evaluate_conditions(rule, {"users_online": 150})


@pytest.mark.asyncio
async def test_threshold_rule_applies_conditions_per_target():
    engine = AutomationEngine()
    rule = {"id": 3, "name": "r", "action_type": "notify",
            "trigger_config": {"metric": "user_traffic_percent", "operator": ">=", "value": 90},
            "conditions": [{"field": "percent", "operator": ">=", "value": 99}]}
    users = [
        {"uuid": "a", "username": "a", "traffic_limit_bytes": 100, "used_traffic_bytes": 95},
        {"uuid": "b", "username": "b", "traffic_limit_bytes": 100, "used_traffic_bytes": 100},
    ]
    execute = AsyncMock(return_value=("success", {}))
    with patch("web.backend.core.automation.get_enabled_rules_by_trigger_type", AsyncMock(return_value=[rule])), \
            patch("web.backend.core.automation.users_over_traffic", AsyncMock(return_value=users)), \
            patch("web.backend.core.automation.try_acquire_target", AsyncMock(return_value=True)), \
            patch("web.backend.core.automation.write_automation_log", AsyncMock()), \
            patch.object(engine, "_execute_action", execute):
        await engine._check_threshold_rules()
    assert [c.args[2] for c in execute.await_args_list] == ["b"]


@pytest.mark.asyncio
async def test_telegram_values_are_escaped():
    notify = AsyncMock()
    with patch("web.backend.core.notification_service.create_notification", notify):
        await AutomationEngine()._action_notify(
            {"channel": "telegram", "message": "Юзер {user}"}, "user", "u", {"username": "<script>"},
        )
    assert notify.await_args.kwargs["telegram_body"] == "Юзер &lt;script&gt;"


@pytest.mark.asyncio
async def test_torrent_is_not_sent_to_automations_as_violation():
    from web.backend.api.v2 import websocket
    engine = MagicMock()
    engine.handle_event = AsyncMock()
    with patch.object(websocket.manager, "broadcast", AsyncMock()), \
            patch("web.backend.core.automation_engine.engine", engine):
        await websocket.broadcast_violation({"type": "torrent", "score": 100.0})
    engine.handle_event.assert_not_called()


# ── Проверка правил ───────────────────────────────────────────────────

def test_unknown_event_and_removed_metric_are_rejected():
    base = {"name": "r", "category": "system", "action_type": "notify"}
    with pytest.raises(ValidationError):
        AutomationRuleCreate(**base, trigger_type="event", trigger_config={"event": "violation.created"})
    with pytest.raises(ValidationError):
        AutomationRuleCreate(**base, trigger_type="threshold",
                             trigger_config={"metric": "node_uptime_percent", "operator": ">=", "value": 1})


@pytest.mark.asyncio
async def test_update_goes_through_the_same_validation(client):
    existing = {
        "id": 5, "name": "r", "description": "d", "is_enabled": False, "category": "system",
        "trigger_type": "schedule", "trigger_config": {"cron": "0 9 * * *"}, "conditions": [],
        "action_type": "notify", "action_config": {"channel": "telegram", "message": "x"},
    }
    update = AsyncMock()
    with patch("web.backend.api.v2.automations.get_automation_rule_by_id", AsyncMock(return_value=existing)), \
            patch("web.backend.api.v2.automations.update_automation_rule", update):
        resp = await client.put("/api/v2/automations/5", json={"action_config": {"evil": 1}})
    assert resp.status_code == 422
    update.assert_not_awaited()


def test_cleanup_template_has_no_dead_condition():
    tpl = next(t for t in AUTOMATION_TEMPLATES if t["id"] == "cleanup_expired")
    assert tpl["conditions"] == []
