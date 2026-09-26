"""Tests for the durable delayed-enforcement state machine."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio

import pytest

from web.backend.core import enforcement_workflow as workflow


USER_UUID = "11111111-2222-3333-4444-555555555555"


def database(conn):
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=conn)
    context.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock(is_connected=True)
    db.acquire.return_value = context
    db.is_user_violation_whitelisted = AsyncMock(return_value=(False, None))
    db.update_violation_action = AsyncMock()
    return db


def settings(**values):
    defaults = {
        "enforcement_enabled": True, "enforcement_mode": "dry_run",
        "enforcement_scope": "trial_only", "enforcement_grace_hours": 12,
        "enforcement_final_action": "manual_review", "enforcement_pilot_user_uuids": [],
        "enforcement_delivery_attempts": 3, "enforcement_delivery_failure": "manual_review",
        "enforcement_pause_for_support": True, "enforcement_throttle_kbit": 1024,
    }
    defaults.update(values)
    return lambda key, default=None: defaults.get(key, default)


@pytest.mark.asyncio
async def test_disabled_workflow_preserves_existing_immediate_action():
    with patch.object(workflow.config_service, "get", side_effect=settings(enforcement_enabled=False)):
        assert await workflow.create_enforcement_case(
            violation_id=1, user_uuid=USER_UUID,
            signals=[{"code": "hwid.active_trial_accounts"}], recommended_action="hard_block",
        ) is False


@pytest.mark.asyncio
async def test_dry_run_is_persisted_and_defers_real_action():
    conn = AsyncMock()
    with patch.object(workflow, "db_service", database(conn)), patch.object(
        workflow.config_service, "get", side_effect=settings(),
    ):
        result = await workflow.create_enforcement_case(
            violation_id=7, user_uuid=USER_UUID,
            signals=[{"code": "hwid.active_trial_accounts"}], recommended_action="hard_block",
        )
    assert result is True
    args = conn.execute.await_args.args
    assert args[4:7] == ("dry_run", "dry_run", "manual_review")
    assert args[8] == "simulated"


@pytest.mark.asyncio
async def test_pilot_excludes_other_users_without_database_write():
    db = MagicMock()
    with patch.object(workflow, "db_service", db), patch.object(
        workflow.config_service, "get",
        side_effect=settings(enforcement_pilot_user_uuids=["aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"]),
    ):
        result = await workflow.create_enforcement_case(
            violation_id=7, user_uuid=USER_UUID,
            signals=[{"code": "hwid.active_trial_accounts"}], recommended_action="hard_block",
        )
    assert result is False
    db.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_minimum_score_excludes_low_score_without_database_write():
    db = MagicMock()
    with patch.object(workflow, "db_service", db), patch.object(
        workflow.config_service, "get", side_effect=settings(enforcement_min_score=80),
    ):
        result = await workflow.create_enforcement_case(
            violation_id=7, user_uuid=USER_UUID, score=79,
            signals=[{"code": "hwid.active_trial_accounts"}], recommended_action="hard_block",
        )
    assert result is False
    db.acquire.assert_not_called()


@pytest.mark.asyncio
async def test_delivered_notice_starts_fresh_grace_period():
    case = {"id": 3, "violation_id": 7}
    claimed = {**case, "attempt_count": 1, "policy_snapshot": {"grace_hours": 12}}
    violation = {"id": 7, "user_uuid": USER_UUID, "score": 100, "telegram_id": 123}
    conn = AsyncMock()
    conn.fetchrow.side_effect = [claimed, violation]
    send = AsyncMock(return_value={"sent": True})
    with patch.object(workflow, "db_service", database(conn)), patch.object(
        workflow.config_service, "get", side_effect=settings(),
    ), patch("web.backend.core.violation_notices.send_notice", new=send):
        await workflow._send_notice(case)
    assert "status='grace_period'" in conn.execute.await_args.args[0]
    assert "12" in send.await_args.kwargs["body_suffix"]


@pytest.mark.asyncio
async def test_delivery_failure_routes_to_manual_review_after_retries():
    case = {"id": 3, "violation_id": 7}
    claimed = {**case, "attempt_count": 3, "policy_snapshot": {
        "grace_hours": 12, "delivery_attempts": 3, "delivery_failure": "manual_review",
    }}
    conn = AsyncMock()
    conn.fetchrow.side_effect = [claimed, {"id": 7, "user_uuid": USER_UUID, "score": 100}]
    with patch.object(workflow, "db_service", database(conn)), patch(
        "web.backend.core.violation_notices.send_notice", new=AsyncMock(return_value={"sent": False, "reason": "no_channel"}),
    ):
        await workflow._send_notice(case)
    assert conn.execute.await_args.args[2:4] == ("manual_review", "notice_failed")


@pytest.mark.asyncio
async def test_whitelist_recheck_cancels_before_disable():
    case = {"id": 4, "violation_id": 8, "user_uuid": USER_UUID, "status": "due",
            "mode": "enforce", "final_action": "disable"}
    conn = AsyncMock()
    conn.fetchrow.return_value = {"id": 8, "action_taken": None}
    conn.fetchval.return_value = 1
    db = database(conn)
    db.is_user_violation_whitelisted.return_value = (True, None)
    api = MagicMock(disable_user=AsyncMock())
    with patch.object(workflow, "db_service", db), patch("shared.api_client.api_client", api):
        await workflow.process_case(case)
    api.disable_user.assert_not_awaited()
    assert "status='cancelled'" in conn.execute.await_args.args[0]


@pytest.mark.asyncio
async def test_deliver_only_records_would_action_without_mutating_user():
    case = {"id": 4, "violation_id": 8, "user_uuid": USER_UUID, "status": "due",
            "mode": "deliver_only", "final_action": "disable"}
    conn = AsyncMock()
    conn.fetchrow.return_value = {"id": 8, "action_taken": None}
    conn.fetchval.side_effect = [1, 4]
    db = database(conn)
    api = MagicMock(disable_user=AsyncMock())
    with patch.object(workflow, "db_service", db), patch("shared.api_client.api_client", api):
        await workflow.process_case(case)
    api.disable_user.assert_not_awaited()
    db.update_violation_action.assert_not_awaited()


@pytest.mark.asyncio
async def test_enforce_disable_updates_user_and_resolves_violation_once():
    case = {"id": 4, "violation_id": 8, "user_uuid": USER_UUID, "status": "due",
            "mode": "enforce", "final_action": "disable"}
    conn = AsyncMock()
    conn.fetchrow.return_value = {"id": 8, "action_taken": None}
    conn.fetchval.side_effect = [1, 4, 4]
    db = database(conn)
    api = MagicMock(disable_user=AsyncMock())
    with patch.object(workflow, "db_service", db), patch(
        "shared.api_client.api_client", api,
    ), patch("shared.data_access.resolve_panel_user_id", new=AsyncMock(return_value=USER_UUID)):
        await workflow.process_case(case)
    api.disable_user.assert_awaited_once_with(USER_UUID)
    db.update_violation_action.assert_awaited_once_with(
        violation_id=8, action_taken="disable", admin_telegram_id=None,
        admin_comment="Delayed enforcement workflow",
    )


@pytest.mark.asyncio
async def test_support_pause_requires_exactly_one_identity_match():
    conn = AsyncMock()
    conn.fetch.return_value = [{"uuid": USER_UUID}, {"uuid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}]
    with patch.object(workflow, "db_service", database(conn)):
        matched, cases = await workflow.pause_for_support_identity(email="shared@example.com")
    assert (matched, cases) == (2, [])


@pytest.mark.asyncio
async def test_expired_worker_claim_is_recoverable_after_restart(monkeypatch):
    conn = AsyncMock()
    conn.fetch.return_value = []
    calls = 0
    async def sleep(_):
        nonlocal calls
        calls += 1
        if calls > 1: raise asyncio.CancelledError
    monkeypatch.setattr(workflow, "db_service", database(conn))
    monkeypatch.setattr(workflow.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        await workflow.enforcement_loop()
    assert "worker lease expired" in conn.execute.await_args.args[0]
