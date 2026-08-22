"""Сторож чёрного списка HWID.

Кейс 22.08: абузер привязал свой telegram_id к подписке, заведённой через
email, и та поднялась сама — DISABLED сменился на ACTIVE, срок уехал вперёд.
Блокировка по чёрному списку разовая и такого воскрешения не переживает,
поэтому сторож обходит список и гасит ожившие подписки снова.
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import hwid_guard

HWID = "4c0e56f81ec134dc"
UUID = "7df1da72-0f6d-4348-9d34-e8747d6fc903"
FUTURE = datetime.now(timezone.utc) + timedelta(days=18)
PAST = datetime.now(timezone.utc) - timedelta(days=1)


def _user(**over):
    user = {
        "user_uuid": UUID, "username": "user_email_aizeliteam", "status": "ACTIVE",
        "expire_at": FUTURE, "telegram_id": 5078118156, "removed_at": None,
    }
    user.update(over)
    return user


def _ctx(users, action="block", enabled=True, disable_ok=True):
    """Окружение прохода: список, юзеры на устройстве, панель и уведомления."""
    db = MagicMock()
    db.is_connected = True
    db.get_hwid_blacklist = AsyncMock(return_value=[
        {"hwid": HWID, "action": action, "reason": "Абуз триала"},
    ])
    db.find_users_by_hwid = AsyncMock(return_value=users)

    cfg = MagicMock()
    cfg.get = MagicMock(side_effect=lambda key, default=None:
                        enabled if key == "hwid_blacklist_guard_enabled" else default)

    api = MagicMock()
    api.disable_user = AsyncMock(return_value=None) if disable_ok else \
        AsyncMock(side_effect=RuntimeError("panel down"))

    notify = AsyncMock()
    monitor = MagicMock()
    monitor.get_user_active_connections = AsyncMock(return_value=[object(), object()])

    return db, cfg, api, notify, monitor


def _run(db, cfg, api, notify, monitor):
    return patch.multiple(
        "shared.database", db_service=db,
    ), patch("shared.config_service.config_service", cfg), \
        patch("shared.api_client.api_client", api), \
        patch("web.backend.core.notification_service.create_notification", notify), \
        patch("web.backend.api.v2.collector.connection_monitor", monitor), \
        patch("web.backend.api.v2.users._resolve_user_key", AsyncMock(return_value=1))


async def _once(db, cfg, api, notify, monitor):
    p1, p2, p3, p4, p5, p6 = _run(db, cfg, api, notify, monitor)
    with p1, p2, p3, p4, p5, p6:
        return await hwid_guard.run_once()


@pytest.fixture(autouse=True)
def _clear_state():
    hwid_guard._alerted.clear()
    yield
    hwid_guard._alerted.clear()


class TestGuard:
    @pytest.mark.asyncio
    async def test_revived_subscription_disabled_again(self):
        ctx = _ctx([_user()])
        disabled = await _once(*ctx)
        assert disabled == 1
        ctx[2].disable_user.assert_awaited_once()
        ctx[3].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_already_disabled_user_untouched(self):
        ctx = _ctx([_user(status="DISABLED")])
        assert await _once(*ctx) == 0
        ctx[2].disable_user.assert_not_awaited()
        ctx[3].assert_not_awaited()

    @pytest.mark.asyncio
    async def test_expired_subscription_untouched(self):
        ctx = _ctx([_user(status="ACTIVE", expire_at=PAST)])
        assert await _once(*ctx) == 0
        ctx[2].disable_user.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unlinked_device_still_counts(self):
        """Устройство отвязали, но подписка живёт — это и есть схема обхода."""
        ctx = _ctx([_user(removed_at=PAST)])
        assert await _once(*ctx) == 1
        ctx[2].disable_user.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_alert_entry_notifies_but_keeps_subscription(self):
        ctx = _ctx([_user()], action="alert")
        assert await _once(*ctx) == 0
        ctx[2].disable_user.assert_not_awaited()
        ctx[3].assert_awaited_once()

    @pytest.mark.asyncio
    async def test_alert_entry_does_not_repeat(self):
        """Цикл ходит раз в несколько минут — наблюдение шлём один раз."""
        ctx = _ctx([_user()], action="alert")
        await _once(*ctx)
        await _once(*ctx)
        assert ctx[3].await_count == 1

    @pytest.mark.asyncio
    async def test_disabled_setting_stops_guard(self):
        ctx = _ctx([_user()], enabled=False)
        assert await _once(*ctx) == 0
        ctx[0].get_hwid_blacklist.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_panel_failure_is_not_counted(self):
        ctx = _ctx([_user()], disable_ok=False)
        assert await _once(*ctx) == 0
        ctx[3].assert_not_awaited()
