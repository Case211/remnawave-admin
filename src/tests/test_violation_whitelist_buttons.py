"""Кнопки белого списка под уведомлением о нарушении.

Две кнопки: полный белый список и «не проверять по тому анализатору, который
и поднял тревогу». Разрез берётся из breakdown, поэтому кнопка всегда ведёт
в тот же разрез, что и само нарушение.
"""
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# src/handlers/__init__.py собирает все роутеры бота разом, а те объявляют
# FSM-состояния поверх замоканного aiogram — импорт пакета целиком падает
# ещё до тестируемого кода. Подменяем пакет заглушкой с тем же путём: сам
# модуль найдётся и импортируется, а соседние роутеры не тронутся.
if "src.handlers" not in sys.modules:
    _pkg = types.ModuleType("src.handlers")
    _pkg.__path__ = [str(Path(__file__).resolve().parent.parent / "handlers")]
    sys.modules["src.handlers"] = _pkg

from src.utils.notifications import VIOLATION_ANALYZERS, dominant_analyzer  # noqa: E402

USER_UUID = "11111111-2222-3333-4444-555555555555"


def _admin():
    admin = MagicMock()
    admin.account_id = 7
    admin.username = "root"
    admin.telegram_id = 100500
    admin.has_permission = AsyncMock(return_value=True)
    admin.get_visible_user_uuids = AsyncMock(return_value=None)
    return admin


def _callback(data: str):
    cb = MagicMock()
    cb.data = data
    cb.answer = AsyncMock()
    cb.from_user.first_name = "Admin"
    cb.from_user.id = 100500
    cb.message.text = "нарушение"
    cb.message.html_text = "нарушение"
    cb.message.edit_text = AsyncMock()
    return cb


class TestDominantAnalyzer:
    def test_picks_the_biggest_contributor(self):
        assert dominant_analyzer({
            "geo": {"score": 10.0},
            "hwid": {"score": 80.0},
            "device": {"score": 25.0},
        }) == "hwid"

    def test_reads_dataclass_shaped_entries(self):
        """Breakdown приходит и объектами анализаторов, не только словарями."""
        geo = MagicMock(score=5.0)
        temporal = MagicMock(score=40.0)
        assert dominant_analyzer({"geo": geo, "temporal": temporal}) == "temporal"

    def test_no_button_when_nothing_scored(self):
        """Предлагать разрез наугад хуже, чем не предлагать вовсе."""
        assert dominant_analyzer({"geo": {"score": 0}, "hwid": {"score": 0}}) is None
        assert dominant_analyzer({}) is None
        assert dominant_analyzer(None) is None

    def test_ignores_keys_that_are_not_analyzers(self):
        assert dominant_analyzer({"total": {"score": 99}, "geo": {"score": 3}}) == "geo"

    def test_keys_match_whitelist_contract(self):
        """Ключи breakdown должны совпадать с тем, что понимает excluded_analyzers."""
        assert set(VIOLATION_ANALYZERS) == {
            "temporal", "geo", "asn", "profile", "device", "hwid", "user_agent",
        }


class TestWhitelistFull:
    @pytest.mark.asyncio
    async def test_writes_full_whitelist(self):
        from src.handlers import violation_actions as va

        db = MagicMock()
        db.add_to_violation_whitelist = AsyncMock(return_value=(True, None))
        cb = _callback(f"vact:wl:{USER_UUID}")

        with patch.object(va, "db_service", db):
            await va._whitelist_full(cb, USER_UUID, _admin())

        kwargs = db.add_to_violation_whitelist.await_args.kwargs
        assert kwargs["user_uuid"] == USER_UUID
        # None = никаких проверок вообще, это и есть полный белый список
        assert kwargs["excluded_analyzers"] is None
        assert kwargs["admin_id"] == 7
        cb.answer.assert_awaited()

    @pytest.mark.asyncio
    async def test_reports_failure_instead_of_silence(self):
        from src.handlers import violation_actions as va

        db = MagicMock()
        db.add_to_violation_whitelist = AsyncMock(return_value=(False, "boom"))
        cb = _callback(f"vact:wl:{USER_UUID}")

        with patch.object(va, "db_service", db):
            await va._whitelist_full(cb, USER_UUID, _admin())

        cb.answer.assert_awaited()
        cb.message.edit_text.assert_not_awaited()


class TestWhitelistPartial:
    @pytest.mark.asyncio
    async def test_excludes_single_analyzer(self):
        from src.handlers import violation_actions as va

        db = MagicMock()
        db.is_user_violation_whitelisted = AsyncMock(return_value=(False, None))
        db.add_to_violation_whitelist = AsyncMock(return_value=(True, None))
        cb = _callback(f"vact:wlp_hwid:{USER_UUID}")

        with patch.object(va, "db_service", db):
            await va._whitelist_partial(cb, USER_UUID, "hwid", _admin())

        assert db.add_to_violation_whitelist.await_args.kwargs["excluded_analyzers"] == ["hwid"]

    @pytest.mark.asyncio
    async def test_keeps_previous_exclusions(self):
        """Запись одна на юзера и перезаписывается целиком — старый разрез нельзя терять."""
        from src.handlers import violation_actions as va

        db = MagicMock()
        db.is_user_violation_whitelisted = AsyncMock(return_value=(True, ["geo"]))
        db.add_to_violation_whitelist = AsyncMock(return_value=(True, None))
        cb = _callback(f"vact:wlp_hwid:{USER_UUID}")

        with patch.object(va, "db_service", db):
            await va._whitelist_partial(cb, USER_UUID, "hwid", _admin())

        assert db.add_to_violation_whitelist.await_args.kwargs["excluded_analyzers"] == ["geo", "hwid"]

    @pytest.mark.asyncio
    async def test_repeated_press_does_not_duplicate(self):
        from src.handlers import violation_actions as va

        db = MagicMock()
        db.is_user_violation_whitelisted = AsyncMock(return_value=(True, ["hwid"]))
        db.add_to_violation_whitelist = AsyncMock(return_value=(True, None))
        cb = _callback(f"vact:wlp_hwid:{USER_UUID}")

        with patch.object(va, "db_service", db):
            await va._whitelist_partial(cb, USER_UUID, "hwid", _admin())

        assert db.add_to_violation_whitelist.await_args.kwargs["excluded_analyzers"] == ["hwid"]

    @pytest.mark.asyncio
    async def test_does_not_narrow_a_full_whitelist(self):
        """Полный белый список шире частичного — молча сужать его нельзя."""
        from src.handlers import violation_actions as va

        db = MagicMock()
        db.is_user_violation_whitelisted = AsyncMock(return_value=(True, None))
        db.add_to_violation_whitelist = AsyncMock()
        cb = _callback(f"vact:wlp_geo:{USER_UUID}")

        with patch.object(va, "db_service", db):
            await va._whitelist_partial(cb, USER_UUID, "geo", _admin())

        db.add_to_violation_whitelist.assert_not_awaited()
        cb.answer.assert_awaited()

    @pytest.mark.asyncio
    async def test_rejects_analyzer_that_does_not_exist(self):
        """callback_data приходит снаружи — разрез принимаем только известный."""
        from src.handlers import violation_actions as va

        db = MagicMock()
        db.is_user_violation_whitelisted = AsyncMock()
        db.add_to_violation_whitelist = AsyncMock()
        cb = _callback(f"vact:wlp_sudo:{USER_UUID}")

        with patch.object(va, "db_service", db):
            await va._whitelist_partial(cb, USER_UUID, "sudo", _admin())

        db.add_to_violation_whitelist.assert_not_awaited()
        db.is_user_violation_whitelisted.assert_not_awaited()


class TestWhitelistPermissions:
    def test_whitelisting_requires_resolve_permission(self):
        """Белый список отключает защиту — право то же, что на разбор нарушения."""
        from src.handlers.violation_actions import needs_resolve_permission

        assert needs_resolve_permission("wl") is True
        for analyzer in VIOLATION_ANALYZERS:
            assert needs_resolve_permission(f"wlp_{analyzer}") is True

    def test_read_only_action_stays_free(self):
        """Просмотр карточки правом не гейтится — так было и до белого списка."""
        from src.handlers.violation_actions import needs_resolve_permission

        assert needs_resolve_permission("info") is False

    def test_existing_mutating_actions_still_gated(self):
        from src.handlers.violation_actions import needs_resolve_permission

        for action in ("block", "kill", "dismiss", "reset"):
            assert needs_resolve_permission(action) is True
