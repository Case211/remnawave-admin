"""Переезд наказанного в резервный сквад и возврат обратно.

Половина меры обратима только если прежний состав сквадов снят ДО
переключения: панель хранит лишь текущий.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import shared.throttle as throttle

USER = "11111111-2222-3333-4444-555555555555"
SQUAD = "99999999-8888-7777-6666-555555555555"


def _cfg(squad_uuid=""):
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: (
        squad_uuid if key == "throttle_squad_uuid" else default
    )
    return cfg


def _db(existing=None):
    db = MagicMock()
    db.add_user_throttle = AsyncMock(return_value=(True, None))
    db.remove_user_throttle = AsyncMock(return_value=True)
    db.get_user_throttle = AsyncMock(return_value=existing)
    return db


class TestApplyThrottle:
    @pytest.mark.asyncio
    async def test_squads_are_untouched_when_reserve_not_configured(self):
        """Пустая настройка — режем скорость и не лезем в панель."""
        db = _db()
        with patch.object(throttle, "config_service", _cfg("")), \
             patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_set_squads", AsyncMock()) as move:
            ok, err, moved = await throttle.apply_throttle(USER, 1024)

        assert (ok, moved) == (True, False)
        move.assert_not_awaited()
        assert db.add_user_throttle.await_args.kwargs["prev_squads"] is None

    @pytest.mark.asyncio
    async def test_previous_squads_are_snapshotted_before_the_move(self):
        db = _db()
        with patch.object(throttle, "config_service", _cfg(SQUAD)), \
             patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_current_squads", AsyncMock(return_value=["squad-a", "squad-b"])), \
             patch.object(throttle, "_set_squads", AsyncMock(return_value=True)) as move:
            ok, err, moved = await throttle.apply_throttle(USER, 1024)

        assert (ok, moved) == (True, True)
        move.assert_awaited_once_with(USER, [SQUAD])
        assert db.add_user_throttle.await_args.kwargs["prev_squads"] == ["squad-a", "squad-b"]

    @pytest.mark.asyncio
    async def test_throttle_survives_a_failed_move(self):
        """Панель не ответила — скорость всё равно режем, половина меры лучше нуля."""
        db = _db()
        with patch.object(throttle, "config_service", _cfg(SQUAD)), \
             patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_current_squads", AsyncMock(return_value=["squad-a"])), \
             patch.object(throttle, "_set_squads", AsyncMock(return_value=False)):
            ok, err, moved = await throttle.apply_throttle(USER, 1024)

        assert (ok, moved) == (True, False)
        # Снимок не пишем: переезда не было, возвращать неоткуда и незачем
        assert db.add_user_throttle.await_args.kwargs["prev_squads"] is None

    @pytest.mark.asyncio
    async def test_second_throttle_does_not_overwrite_the_snapshot(self):
        """Повторное наказание застаёт человека уже в резервном — снимок не портим."""
        db = _db()
        with patch.object(throttle, "config_service", _cfg(SQUAD)), \
             patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_current_squads", AsyncMock(return_value=[SQUAD])), \
             patch.object(throttle, "_set_squads", AsyncMock(return_value=True)) as move:
            ok, err, moved = await throttle.apply_throttle(USER, 512)

        assert (ok, moved) == (True, False)
        move.assert_not_awaited()
        assert db.add_user_throttle.await_args.kwargs["prev_squads"] is None


class TestLiftThrottle:
    @pytest.mark.asyncio
    async def test_squads_are_restored(self):
        db = _db(existing={"prev_squads": ["squad-a", "squad-b"]})
        with patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_set_squads", AsyncMock(return_value=True)) as move:
            removed, restored = await throttle.lift_throttle(USER)

        assert (removed, restored) == (True, True)
        move.assert_awaited_once_with(USER, ["squad-a", "squad-b"])

    @pytest.mark.asyncio
    async def test_snapshot_stored_as_json_string_is_read_back(self):
        """asyncpg отдаёт jsonb то списком, то строкой — принимаем оба."""
        db = _db(existing={"prev_squads": '["squad-a"]'})
        with patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_set_squads", AsyncMock(return_value=True)) as move:
            await throttle.lift_throttle(USER)

        move.assert_awaited_once_with(USER, ["squad-a"])

    @pytest.mark.asyncio
    async def test_nothing_to_restore_when_there_was_no_move(self):
        db = _db(existing={"prev_squads": None})
        with patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_set_squads", AsyncMock()) as move:
            removed, restored = await throttle.lift_throttle(USER)

        assert (removed, restored) == (True, False)
        move.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_failed_restore_is_reported_loudly(self):
        """Человек остался в резервном сквадe — это нельзя проглотить молча."""
        db = _db(existing={"prev_squads": ["squad-a"]})
        with patch.object(throttle, "db_service", db), \
             patch.object(throttle, "_set_squads", AsyncMock(return_value=False)), \
             patch.object(throttle.logger, "error") as err:
            removed, restored = await throttle.lift_throttle(USER)

        assert (removed, restored) == (True, False)
        err.assert_called_once()
