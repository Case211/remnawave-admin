"""Торрент-уведомление называет ноду, с которой пришёл батч.

Раньше админ видел назначения и IP, но не видел, на какой ноде человек
качает, а это первый вопрос при разборе.
"""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import violation_notifier as vn


def _config():
    cfg = MagicMock()
    cfg.get = lambda key, default=None: default
    return cfg


async def _send(**kwargs) -> str:
    """HTML-фолбэк карточки, ушедшей в Telegram."""
    return (await _notify(**kwargs))["telegram_card"].to_html()


async def _notify(**kwargs) -> dict:
    vn._violation_notification_cache.clear()
    notify = AsyncMock()
    db = MagicMock()
    db.mark_user_violations_notified = AsyncMock()
    with patch("web.backend.core.notification_service.create_notification", notify), \
            patch.object(vn, "_recap", AsyncMock(return_value=None)), \
            patch("shared.database.db_service", db), \
            patch("shared.config_service.config_service", _config()):
        await vn.send_torrent_notification(
            user_uuid="11111111-1111-1111-1111-111111111111",
            user_info={"username": "alice"},
            torrent_events=[object()],
            destinations=["tracker.example.org:6881"],
            ips=["1.2.3.4"],
            **kwargs,
        )
    assert notify.await_count == 1
    return notify.call_args.kwargs


@pytest.mark.asyncio
async def test_opens_user_card_from_admin():
    # Без ссылки клик по уведомлению в колокольчике не делал ничего
    assert (await _notify())["link"] == "/users/11111111-1111-1111-1111-111111111111"


@pytest.mark.asyncio
async def test_node_named_in_the_summary():
    body = await _send(node_name="Germany <W>")
    assert "<b>alice</b> · <code>Germany &lt;W&gt;</code>" in body


@pytest.mark.asyncio
async def test_no_node_when_unknown():
    body = await _send()
    assert "Germany" not in body and "<b>alice</b>\n" in body


@pytest.mark.asyncio
async def test_window_counts_and_thresholds_shown():
    body = await _send(window={"minutes": 30, "events": 382, "peers": 20, "min_events": 5, "min_peers": 20})
    assert "Окно: 30 мин" in body
    assert "События: <b>382</b> · порог 5" in body
    assert "Адреса: <b>20</b> · порог 20" in body
    # в списке один адрес, остальные 19 — строкой «и ещё»
    assert "и ещё 19" in body


@pytest.mark.asyncio
async def test_peers_fold_into_details():
    card = (await _notify(window={"peers": 20}))["telegram_card"]
    details = next(blk for blk in card.to_blocks() if blk["type"] == "details")
    assert details["summary"] == "🌐 Адреса · 20"


@pytest.mark.asyncio
async def test_action_reflects_setting_not_hardcoded_block():
    assert "Только уведомление" in await _send()
    assert "Жёсткая блокировка" not in await _send()
    assert "отключён автоматически" in await _send(action="blocked")
    assert "Автоблокировка не удалась" in await _send(action="block_failed")


@pytest.mark.asyncio
async def test_no_whitelist_buttons_on_torrent():
    card = (await _notify())["telegram_card"]
    callbacks = [btn["callback_data"] for row in card.keyboard()["inline_keyboard"] for btn in row]
    assert "vact:block:11111111-1111-1111-1111-111111111111" in callbacks
    assert not any(cd.startswith("vact:wl") for cd in callbacks)
