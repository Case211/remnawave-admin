"""Tests for violation deduplication window and created-gated side effects.

Регрессия: старое pending-нарушение (вне окна выборки UI) вечно глушило новые
записи — уведомления шли, а вкладка «Нарушения» оставалась пустой; при этом
fire_event("violation.created") и автоблок срабатывали повторно на старый id.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

import web.backend.api.v2.collector as collector
from shared.database import db_service
from shared.violation_detector import ViolationAction

USER_UUID = "11111111-2222-3333-4444-555555555555"


def _make_conn(existing_row=None, insert_id=123):
    """asyncpg-connection mock: fetchrow — дедуп-выборка, fetchval — insert."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=existing_row)
    conn.fetchval = AsyncMock(return_value=insert_id)
    tx = MagicMock()
    tx.__aenter__ = AsyncMock(return_value=None)
    tx.__aexit__ = AsyncMock(return_value=False)
    conn.transaction = MagicMock(return_value=tx)
    return conn


def _patch_db(conn):
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    return (
        patch.object(type(db_service), "is_connected", PropertyMock(return_value=True)),
        patch.object(db_service, "acquire", MagicMock(return_value=cm)),
    )


class TestSaveViolationDedup:
    @pytest.mark.asyncio
    async def test_creates_when_no_pending(self):
        conn = _make_conn(existing_row=None, insert_id=123)
        p1, p2 = _patch_db(conn)
        with p1, p2:
            vid, created = await db_service.save_violation(
                user_uuid=USER_UUID, score=50.0, recommended_action="warn",
            )
        assert (vid, created) == (123, True)
        conn.fetchval.assert_awaited()

    @pytest.mark.asyncio
    async def test_dedup_returns_existing_within_window(self):
        conn = _make_conn(existing_row={"id": 42, "score": 50.0})
        p1, p2 = _patch_db(conn)
        with p1, p2:
            vid, created = await db_service.save_violation(
                user_uuid=USER_UUID, score=30.0, recommended_action="warn",
            )
        assert (vid, created) == (42, False)
        conn.fetchval.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_higher_score_escalates_past_dedup(self):
        """Торрент (score=100) должен пробивать pending-предупреждение."""
        conn = _make_conn(existing_row={"id": 42, "score": 50.0}, insert_id=124)
        p1, p2 = _patch_db(conn)
        with p1, p2:
            vid, created = await db_service.save_violation(
                user_uuid=USER_UUID, score=100.0, recommended_action="hard_block",
            )
        assert (vid, created) == (124, True)
        conn.fetchval.assert_awaited()

    @pytest.mark.asyncio
    async def test_dedup_query_is_window_bounded(self):
        """SQL дедупа обязан ограничивать pending по detected_at, иначе
        нарушение годовалой давности глушит новые записи вечно."""
        conn = _make_conn(existing_row=None)
        p1, p2 = _patch_db(conn)
        with p1, p2:
            await db_service.save_violation(
                user_uuid=USER_UUID, score=50.0, recommended_action="warn",
            )
        dedup_sql = conn.fetchrow.await_args.args[0]
        assert "detected_at >" in dedup_sql
        assert "action_taken IS NULL" in dedup_sql

    @pytest.mark.asyncio
    async def test_not_connected_returns_none_false(self):
        with patch.object(type(db_service), "is_connected", PropertyMock(return_value=False)):
            assert await db_service.save_violation(
                user_uuid=USER_UUID, score=50.0, recommended_action="warn",
            ) == (None, False)


def _score(action=ViolationAction.HARD_BLOCK):
    return SimpleNamespace(
        total=85.0,
        recommended_action=action,
        reasons=["3 IP при лимите 1"],
        breakdown={},
        confidence=0.9,
    )


def _trial_score(accomplices: list[str]):
    """Нарушение по абузу пробных подписок со списком соучастников от анализатора."""
    return SimpleNamespace(
        total=100.0,
        recommended_action=ViolationAction.HARD_BLOCK,
        reasons=["Абуз пробных подписок: 2 аккаунтов с активным триалом на одном устройстве (порог: 1)"],
        breakdown={
            "hwid": SimpleNamespace(
                score=100.0,
                matched_details=None,
                active_trial_accomplices=accomplices,
            ),
        },
        confidence=0.3,
    )


def _handle_violation_mocks(save_result, config: dict | None = None):
    """Общий набор патчей для collector._handle_violation."""
    cfg = {"violation_auto_hard_block": True}
    if config:
        cfg.update(config)
    db = MagicMock()
    db.save_violation = AsyncMock(return_value=save_result)
    # Обе отметки идут через await: обычный MagicMock тут падает в except и вызов
    # выглядит «прошедшим», хотя ничего не произошло
    db.mark_violation_notified = AsyncMock(return_value=True)
    db.update_violation_action = AsyncMock(return_value=True)
    monitor = MagicMock()
    monitor.get_user_active_connections = AsyncMock(return_value=[])
    return db, monitor, [
        patch.object(collector, "db_service", db),
        patch.object(collector, "connection_monitor", monitor),
        patch.object(collector, "fire_event", MagicMock()),
        patch.object(
            collector.config_service, "get",
            side_effect=lambda key, default=None: cfg.get(key, default),
        ),
        patch(
            "web.backend.core.violation_notifier.send_violation_notification",
            new_callable=AsyncMock,
        ),
        patch("shared.api_client.api_client.disable_user", new_callable=AsyncMock),
        patch("web.backend.api.v2.websocket.broadcast_violation", new_callable=AsyncMock),
    ]


class TestHandleViolationCreatedGate:
    @pytest.mark.asyncio
    async def test_dedup_suppresses_events_and_autoblock(self):
        db, monitor, patches = _handle_violation_mocks(save_result=(42, False))
        with patches[0], patches[1], patches[2] as fire, patches[3], patches[4], patches[5] as disable, patches[6]:
            await collector._handle_violation(USER_UUID, _score(), None, [], False)
        fire.assert_not_called()
        disable.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_created_fires_event_and_autoblocks(self):
        db, monitor, patches = _handle_violation_mocks(save_result=(43, True))
        with patches[0], patches[1], patches[2] as fire, patches[3], patches[4], patches[5] as disable, patches[6]:
            await collector._handle_violation(USER_UUID, _score(), None, [], False)
        fired_events = [c.args[0] for c in fire.call_args_list]
        assert "violation.created" in fired_events
        assert "user.blocked" in fired_events
        disable.assert_awaited_once_with(USER_UUID)

    @pytest.mark.asyncio
    async def test_autoblock_toggle_off_skips_disable(self):
        db, monitor, patches = _handle_violation_mocks(
            save_result=(44, True), config={"violation_auto_hard_block": False},
        )
        with patches[0], patches[1], patches[2] as fire, patches[3], patches[4], patches[5] as disable, patches[6]:
            await collector._handle_violation(USER_UUID, _score(), None, [], False)
        fired_events = [c.args[0] for c in fire.call_args_list]
        assert "violation.created" in fired_events
        assert "user.blocked" not in fired_events
        disable.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_trial_abuse_blocks_accomplices_and_resolves(self):
        """Абуз триалов: блокируется вся связка, а не только проверяемый, и запись
        помечается решённой — систему уже отработала, ручного решения не ждёт."""
        db, monitor, patches = _handle_violation_mocks(save_result=(46, True))
        with patches[0], patches[1], patches[2] as fire, patches[3], patches[4], patches[5] as disable, patches[6]:
            await collector._handle_violation(
                USER_UUID, _trial_score(["acc-uuid-1", "acc-uuid-2"]), None, [], False,
            )
        disabled = [c.args[0] for c in disable.await_args_list]
        assert disabled == [USER_UUID, "acc-uuid-1", "acc-uuid-2"]
        assert [c.args[0] for c in fire.call_args_list].count("user.blocked") == 3
        db.update_violation_action.assert_awaited_once()
        assert db.update_violation_action.await_args.kwargs["action_taken"] == "hard_block"
        assert db.update_violation_action.await_args.kwargs["admin_telegram_id"] is None

    @pytest.mark.asyncio
    async def test_accomplice_failure_does_not_stop_the_rest(self):
        """Падение блокировки одного соучастника не должно ронять остальных."""
        db, monitor, patches = _handle_violation_mocks(save_result=(47, True))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as disable, patches[6]:
            disable.side_effect = [None, RuntimeError("panel down"), None]
            await collector._handle_violation(
                USER_UUID, _trial_score(["acc-bad", "acc-good"]), None, [], False,
            )
        assert [c.args[0] for c in disable.await_args_list] == [USER_UUID, "acc-bad", "acc-good"]
        db.update_violation_action.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_sent_notification_is_marked(self):
        """Уведомление уходит до сохранения записи, поэтому отметку ставит пайплайн —
        на ней держится кулдаун повторных уведомлений."""
        db, monitor, patches = _handle_violation_mocks(save_result=(48, True))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            await collector._handle_violation(USER_UUID, _score(), None, [], False)
        db.mark_violation_notified.assert_awaited_once_with(48)

    @pytest.mark.asyncio
    async def test_whitelisted_violation_is_not_marked_notified(self):
        """Юзеру из белого списка уведомление не отправляли — отметки быть не должно."""
        db, monitor, patches = _handle_violation_mocks(save_result=(49, True))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            await collector._handle_violation(USER_UUID, _score(), None, [], True)
        db.mark_violation_notified.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_non_hard_block_never_disables(self):
        db, monitor, patches = _handle_violation_mocks(save_result=(45, True))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5] as disable, patches[6]:
            await collector._handle_violation(
                USER_UUID, _score(action=ViolationAction.WARN), None, [], False,
            )
        disable.assert_not_awaited()
