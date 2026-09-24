"""Автоматизации: данные в событиях, новые пороги, параметры действий."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.automation_engine import AutomationEngine


def _rule(conditions):
    return {"conditions": conditions}


def test_in_list_operator_and_list_fields():
    engine = AutomationEngine()
    cond = [{"field": "country", "operator": "in", "value": "RU, BY"}]
    assert engine._evaluate_conditions(_rule(cond), {"country": "ru"})
    assert not engine._evaluate_conditions(_rule(cond), {"country": "DE"})
    # список в данных: хватает одного совпадения
    cond = [{"field": "countries", "operator": "not_in", "value": ["KZ"]}]
    assert engine._evaluate_conditions(_rule(cond), {"countries": ["RU", "DE"]})


def test_boolean_flags_compare_with_strings():
    engine = AutomationEngine()
    cond = [{"field": "is_vpn", "operator": "==", "value": "true"}]
    assert engine._evaluate_conditions(_rule(cond), {"is_vpn": True})
    assert not engine._evaluate_conditions(_rule(cond), {"is_vpn": False})


@pytest.mark.asyncio
async def test_users_online_threshold_for_one_node():
    engine = AutomationEngine()
    nodes = [{"uuid": "A", "name": "de1", "users_online": 400}, {"uuid": "B", "name": "fi1", "users_online": 50}]
    with patch("web.backend.core.api_helper.fetch_nodes_from_api", AsyncMock(return_value=nodes)):
        targets = await engine._threshold_targets(
            {"metric": "users_online", "operator": ">=", "value": 300, "node_uuid": "b"}, {})
    assert targets == []
    with patch("web.backend.core.api_helper.fetch_nodes_from_api", AsyncMock(return_value=nodes)):
        targets = await engine._threshold_targets(
            {"metric": "users_online", "operator": ">=", "value": 300, "node_uuid": "a"}, {})
    assert targets == [("node", "a", {"users_online": 400, "node_name": "de1"})]


@pytest.mark.asyncio
async def test_node_cpu_threshold_targets_each_node():
    engine = AutomationEngine()
    load = [{"uuid": "A", "name": "de1", "cpu_usage": 95.0, "memory_usage": 40.0, "disk_usage": 10.0},
            {"uuid": "B", "name": "fi1", "cpu_usage": 20.0, "memory_usage": 30.0, "disk_usage": 10.0}]
    with patch("web.backend.core.automation.node_load", AsyncMock(return_value=load)):
        targets = await engine._threshold_targets({"metric": "node_cpu_percent", "operator": ">", "value": 90}, {})
    assert [(t[0], t[1], t[2]["value"]) for t in targets] == [("node", "A", 95.0)]


@pytest.mark.asyncio
async def test_timed_block_schedules_unblock():
    engine = AutomationEngine()
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    schedule = AsyncMock()
    with patch("shared.data_access.resolve_panel_user_id", AsyncMock(return_value=42)), \
            patch("web.backend.core.api_helper._get_client", return_value=client), \
            patch("web.backend.core.webhook_security.fire_event", MagicMock()), \
            patch("web.backend.core.automation.schedule_pending_action", schedule):
        details = await engine._action_block_user(
            {"reason": "x", "duration_hours": 2}, "user", "u-1", {"rule_id": 7})
    assert "unblock_at" in details
    rule_id, action, target, _run_at = schedule.await_args.args
    assert (rule_id, action, target) == (7, "enable_user", "u-1")


@pytest.mark.asyncio
async def test_restart_is_rate_limited():
    engine = AutomationEngine()
    with patch("web.backend.core.automation.count_recent_successes", AsyncMock(return_value=3)):
        result, details = await engine._execute_action(
            {"id": 1, "action_type": "restart_node", "action_config": {"max_per_hour": 3}},
            "node", "n-1", {"rule_id": 1},
        )
    assert result == "skipped" and details["skipped"] == "rate_limited"


@pytest.mark.asyncio
async def test_notify_channels_severity_and_buttons():
    notify = AsyncMock()
    with patch("web.backend.core.notification_service.create_notification", notify):
        await AutomationEngine()._action_notify(
            {"channel": "telegram", "message": "x", "channels": ["in_app", "email", "sms"],
             "severity": "critical", "buttons": True},
            "user", "u-1", {"rule_name": "Правило"},
        )
    kwargs = notify.await_args.kwargs
    assert kwargs["channels"] == ["telegram", "in_app", "email"]
    assert kwargs["severity"] == "critical" and kwargs["title"] == "Правило"
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_pending_unblock_runs_and_logs():
    engine = AutomationEngine()
    resp = MagicMock(status_code=200)
    resp.raise_for_status = MagicMock()
    client = MagicMock()
    client.post = AsyncMock(return_value=resp)
    log = AsyncMock()
    with patch("web.backend.core.automation.claim_due_actions",
               AsyncMock(return_value=[{"id": 1, "rule_id": 7, "action": "enable_user", "target": "u-1"}])), \
            patch("web.backend.core.automation.finish_pending_action", AsyncMock()) as finish, \
            patch("web.backend.core.automation.write_automation_log", log), \
            patch("shared.data_access.resolve_panel_user_id", AsyncMock(return_value=42)), \
            patch("web.backend.core.api_helper._get_client", return_value=client):
        await engine._run_pending_actions()
    assert client.post.await_args.args[0] == "/api/users/42/actions/enable"
    finish.assert_awaited_with(1, "success")
    assert log.await_args.kwargs["action_taken"] == "enable_user"


@pytest.mark.asyncio
async def test_offline_event_carries_country_and_users_before():
    engine = AutomationEngine()
    engine._node_users_online["n"] = 120
    nodes = [{"uuid": "n", "name": "de1", "is_connected": False, "is_disabled": False, "country_code": "DE"}]
    with patch("web.backend.core.api_helper.fetch_nodes_from_api", AsyncMock(return_value=nodes)), \
            patch("web.backend.core.automation.get_enabled_event_rules", AsyncMock(return_value=[])), \
            patch("web.backend.core.webhook_security.fire_event", MagicMock()), \
            patch.object(engine, "handle_event", AsyncMock()) as handle:
        await engine._detect_events()
    payload = handle.await_args.args[1]
    assert payload["country_code"] == "DE" and payload["users_before"] == 120
