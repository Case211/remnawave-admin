"""Отчёты торрент-блокировщика: как они выглядят в уведомлении.

Событие ``torrent_blocker.report`` приходит вебхуком от панели. Отчёт
собирается из полей, которые плагин прислал, — состав у него меняется от
версии к версии, и уведомление не должно от этого разъезжаться.
"""
import sys
import types
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _light_import():
    """Модуль вебхука тянет пакет хендлеров ради одного множества.

    Хендлеры — это роутеры на живом aiogram, которого в тестах нет.
    Подменяем ровно то, что нужно, вместо того чтобы поднимать полбота.
    """
    if "src.handlers.state" not in sys.modules:
        stub = types.ModuleType("src.handlers.state")
        stub.BOT_CREATING_USERS = set()
        sys.modules["src.handlers.state"] = stub
    yield


async def _render(event_data: dict) -> str:
    """Отдаёт текст уведомления, которое ушло бы владельцу."""
    from src.services.webhook import _handle_torrent_blocker_event

    with patch("src.services.webhook.send_generic_notification", new=AsyncMock()) as notif:
        await _handle_torrent_blocker_event(AsyncMock(), "torrent_blocker.report", event_data)
    assert notif.await_count == 1
    return notif.call_args.kwargs["message"]


FULL_REPORT = {
    "node": {"name": "Germany W", "uuid": "b808c051-69df-4b1e-9a55-000000000001"},
    "username": "user_zptj8dd8",
    "email": "user_zptj8dd8@local",
    "ip": "178.177.22.7",
    "destination": "tracker.opentrackr.org:1337",
    "action": "blocked",
    "reason": "BitTorrent handshake",
}


@pytest.mark.asyncio
async def test_user_named_once_even_when_report_has_both_fields():
    """Человек один, а полей под него два: username и email.

    Пока подписи были одинаковые, уведомление показывало «Пользователь»
    дважды подряд — с логином и с автогенерируемым адресом того же
    абонента.
    """
    message = await _render(FULL_REPORT)
    assert message.count("Пользователь:") == 1
    assert "user_zptj8dd8" in message
    assert "user_zptj8dd8@local" not in message


@pytest.mark.asyncio
async def test_email_used_when_login_missing():
    report = dict(FULL_REPORT)
    report.pop("username")
    message = await _render(report)
    assert "user_zptj8dd8@local" in message


@pytest.mark.asyncio
async def test_report_carries_node_and_details():
    message = await _render(FULL_REPORT)
    for expected in ("Germany W", "178.177.22.7", "tracker.opentrackr.org:1337",
                     "blocked", "BitTorrent handshake"):
        assert expected in message, expected


@pytest.mark.asyncio
async def test_bare_report_still_readable():
    # Плагин прислал только факт срабатывания — уведомление не должно
    # оказаться пустым.
    message = await _render({})
    assert message.strip()


@pytest.mark.asyncio
async def test_html_from_report_is_escaped():
    message = await _render({"username": "<b>evil</b>", "node": {"name": "<i>n</i>"}})
    assert "<b>evil</b>" not in message
    assert "&lt;b&gt;evil&lt;/b&gt;" in message
