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
    vn._violation_notification_cache.clear()
    notify = AsyncMock()
    db = MagicMock()
    db.mark_user_violations_notified = AsyncMock()
    with patch("web.backend.core.notification_service.create_notification", notify), \
            patch.object(vn, "_recap_lines", AsyncMock(return_value=[])), \
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
    return notify.call_args.kwargs["telegram_body"]


@pytest.mark.asyncio
async def test_node_line_present_when_known():
    body = await _send(node_name="Germany <W>")
    assert "🖥 Нода: <code>Germany &lt;W&gt;</code>" in body


@pytest.mark.asyncio
async def test_no_node_line_when_unknown():
    body = await _send()
    assert "Нода:" not in body
