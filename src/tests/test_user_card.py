"""Карточка юзера в боте: поля копируются касанием, ссылка подписки — в «Карточке»."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.utils import notifications

URL = "https://sub.example.com/r89z4xBgsVmFk-Qa"
OLD = {"uuid": "u-1", "username": "alice", "status": "ACTIVE", "expireAt": "2027-01-08T09:41:00Z",
       "description": "Илья @alice", "email": "alice@example.com", "telegramId": 366945364,
       "subscriptionUrl": URL}


def _buttons(node):
    """Все кнопки copy_text в дереве блоков."""
    if isinstance(node, dict):
        if node.get("type") == "button" and "copy_text" in node.get("button", {}):
            yield node["button"]
        for value in node.values():
            yield from _buttons(value)
    elif isinstance(node, list):
        for value in node:
            yield from _buttons(value)


async def _card(action, info, old=None):
    send = AsyncMock()
    with patch.object(notifications, "get_settings", return_value=MagicMock()), \
            patch.object(notifications, "is_notification_type_enabled", return_value=True), \
            patch.object(notifications, "resolve_notifications_chat_id", return_value=-100), \
            patch.object(notifications, "resolve_notification_topic", return_value=None), \
            patch.object(notifications, "_local_user_uuid", AsyncMock(return_value=None)), \
            patch.object(notifications, "_resolve_squads_display", AsyncMock(return_value="—")), \
            patch.object(notifications, "_send_card", send):
        await notifications.send_user_notification(AsyncMock(), action, info, old_user_info=old)
    return send.await_args.kwargs["card"]


@pytest.mark.asyncio
async def test_updated_card_has_copyable_fields_and_subscription_link():
    card = await _card("updated", {**OLD, "expireAt": "2027-01-13T09:41:00Z"}, OLD)
    blocks = card.to_blocks()
    copied = {b["copy_text"]["text"] for b in _buttons(blocks)}
    assert {"alice", "u-1", "366945364", "alice@example.com", "Илья @alice"} <= copied
    details = next(blk for blk in blocks if blk["type"] == "details")
    link = [b for b in _buttons(details) if b["copy_text"]["text"] == URL]
    assert link and URL not in link[0]["text"]  # ссылка даёт доступ — на кнопке её не видно


@pytest.mark.asyncio
async def test_diff_dates_fit_the_phone_screen():
    """Было/стало — дата без подписи зоны, иначе третья колонка уезжает за экран."""
    card = await _card("updated", {**OLD, "expireAt": "2027-01-13T09:41:00Z"}, OLD)
    diff = next(blk for blk in card.to_blocks() if blk["type"] == "table" and len(blk["cells"][0]) == 3)
    old, new = diff["cells"][1][1]["text"]["text"], diff["cells"][1][2]["text"]["text"]
    assert len(old) == len("08.01.2027 14:41") and "UTC" not in old and "UTC" not in new


@pytest.mark.asyncio
async def test_created_card_keeps_subscription_link_hidden():
    card = await _card("created", OLD)
    assert URL in {b["copy_text"]["text"] for b in _buttons(card.to_blocks())}
    assert f"<tg-spoiler><code>{URL}</code></tg-spoiler>" in card.to_html()
