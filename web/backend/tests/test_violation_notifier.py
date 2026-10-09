"""Tests for web.backend.core.violation_notifier — notification formatting and throttling.

Covers: _cleanup_cache, _short_provider, send_violation_notification (throttling,
message formatting, hwid devices, edge cases), rich-карточка и её кнопки.
"""
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core import violation_notifier as vn
from web.backend.core.violation_notifier import (
    _cleanup_cache,
    _short_provider,
    _violation_notification_cache,
    VIOLATION_NOTIFICATION_COOLDOWN_MINUTES,
    send_violation_notification,
)


# ── _short_provider tests ────────────────────────────────────


class TestShortProvider:
    def test_short_name_unchanged(self):
        assert _short_provider("Comcast") == "Comcast"

    def test_long_name_truncated(self):
        long = "Very Long Internet Service Provider Name Inc."
        result = _short_provider(long)
        assert len(result) == 25
        assert result.endswith("...")

    def test_empty(self):
        assert _short_provider(None) == ""
        assert _short_provider("") == ""

    def test_exactly_25_chars(self):
        name = "A" * 25
        assert _short_provider(name) == name


# ── _cleanup_cache tests ─────────────────────────────────────


class TestCleanupCache:
    def setup_method(self):
        _violation_notification_cache.clear()

    def teardown_method(self):
        _violation_notification_cache.clear()

    def test_removes_old_entries(self):
        _violation_notification_cache["old"] = datetime.utcnow() - timedelta(hours=2)
        _violation_notification_cache["fresh"] = datetime.utcnow()
        _cleanup_cache()
        assert "old" not in _violation_notification_cache
        assert "fresh" in _violation_notification_cache

    def test_empty_cache(self):
        _cleanup_cache()
        assert len(_violation_notification_cache) == 0


# ── send_violation_notification tests ─────────────────────────


class TestSendViolationNotification:
    def setup_method(self):
        _violation_notification_cache.clear()

    def teardown_method(self):
        _violation_notification_cache.clear()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_sends_basic_notification(self, mock_create):
        violation_score = {"total": 75.0, "breakdown": {}, "recommended_action": "warn"}
        user_info = {
            "username": "testuser",
            "hwidDeviceLimit": 3,
        }

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score=violation_score,
            user_info=user_info,
        )

        mock_create.assert_awaited_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs["type"] == "violation"
        assert call_kwargs.kwargs["severity"] == "warning"
        assert call_kwargs.kwargs["source"] == "collector"
        assert call_kwargs.kwargs["source_id"] == "uuid-123"
        # клик по уведомлению в админке ведёт в карточку юзера
        assert call_kwargs.kwargs["link"] == "/users/uuid-123"

        # Check throttle cache updated
        assert "uuid-123" in _violation_notification_cache

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_throttled_within_cooldown(self, mock_create):
        _violation_notification_cache["uuid-123"] = datetime.utcnow()

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score={"total": 80},
        )

        mock_create.assert_not_awaited()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_not_throttled_after_cooldown(self, mock_create):
        _violation_notification_cache["uuid-123"] = (
            datetime.utcnow() - timedelta(minutes=VIOLATION_NOTIFICATION_COOLDOWN_MINUTES + 1)
        )

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score={"total": 80, "breakdown": {}},
            user_info={"username": "test", "hwidDeviceLimit": 1},
        )

        mock_create.assert_awaited_once()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_force_bypasses_throttle(self, mock_create):
        _violation_notification_cache["uuid-123"] = datetime.utcnow()

        await send_violation_notification(
            user_uuid="uuid-123",
            violation_score={"total": 90, "breakdown": {}},
            user_info={"username": "test", "hwidDeviceLimit": 1},
            force=True,
        )

        mock_create.assert_awaited_once()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_critical_severity_for_high_score(self, mock_create):
        await send_violation_notification(
            user_uuid="uuid-high",
            violation_score={"total": 85.0, "breakdown": {}},
            user_info={"username": "baduser", "hwidDeviceLimit": 2},
        )

        mock_create.assert_awaited_once()
        assert mock_create.call_args.kwargs["severity"] == "critical"

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_message_contains_user_info(self, mock_create):
        await send_violation_notification(
            user_uuid="uuid-msg",
            violation_score={"total": 60.0, "breakdown": {}},
            user_info={
                "username": "alice",
                "email": "alice@example.com",
                "telegramId": 99999,
                "hwidDeviceLimit": 3,
                "description": "VIP user",
            },
        )

        body = mock_create.call_args.kwargs["body"]
        assert "alice@example.com" in body
        assert "99999" in body
        assert "VIP user" in body

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_ip_count_from_temporal_breakdown(self, mock_create):
        violation_score = {
            "total": 70.0,
            "breakdown": {
                "temporal": {"simultaneous_connections_count": 5},
            },
        }

        await send_violation_notification(
            user_uuid="uuid-ip",
            violation_score=violation_score,
            user_info={"username": "test", "hwidDeviceLimit": 2},
        )

        body = mock_create.call_args.kwargs["body"]
        assert "5 IP из 2" in body

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_device_limit_zero_shows_infinity(self, mock_create):
        await send_violation_notification(
            user_uuid="uuid-inf",
            violation_score={"total": 60, "breakdown": {}},
            user_info={"username": "test", "hwidDeviceLimit": 0},
        )

        body = mock_create.call_args.kwargs["body"]
        assert "\u221e" in body

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_fetches_user_info_from_db_when_not_provided(self, mock_create):
        mock_db = MagicMock()
        mock_db.get_user_by_uuid = AsyncMock(return_value={
            "username": "from_db", "hwidDeviceLimit": 1,
        })

        with patch("shared.database.db_service", mock_db):
            await send_violation_notification(
                user_uuid="uuid-nodb",
                violation_score={"total": 60, "breakdown": {}},
                user_info=None,
            )

        body = mock_create.call_args.kwargs["body"]
        assert "from_db" in body


# ── Рекомендация против свершившегося факта ───────────────────


def _card_of(mock_create):
    return mock_create.call_args.kwargs["telegram_card"]


def _body_of(mock_create):
    """HTML-фолбэк карточки, ушедшей в Telegram."""
    return _card_of(mock_create).to_html()


class TestRecommendationWording:
    def setup_method(self):
        _violation_notification_cache.clear()

    def teardown_method(self):
        _violation_notification_cache.clear()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_non_blocking_verdict_reads_as_advice(self, mock_create):
        """«ДЕЙСТВИЕ: ВРЕМЕННАЯ БЛОКИРОВКА» читалось как уже случившийся бан."""
        await send_violation_notification(
            user_uuid="uuid-1",
            violation_score={"total": 85.0, "breakdown": {}, "recommended_action": "temp_block"},
        )

        body = _body_of(mock_create)
        assert "Рекомендация: <b>ЗАБЛОКИРОВАТЬ ВРЕМЕННО</b>" in body
        assert "Пользователь заблокирован" not in body

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_auto_block_is_reported_as_a_fact(self, mock_create):
        """На hard_block с автоблокировкой бан уже произошёл — это не совет."""
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, default=None: (
            True if key == "violation_auto_hard_block" else default
        )
        with patch("shared.config_service.config_service", cfg):
            await send_violation_notification(
                user_uuid="uuid-2",
                violation_score={"total": 97.0, "breakdown": {}, "recommended_action": "hard_block"},
            )

        body = _body_of(mock_create)
        assert "<b>⛔ Пользователь заблокирован</b>" in body
        assert "Рекомендация" not in body
        # факт — цитатой с пометкой, кто это сделал
        quote = next(blk for blk in _card_of(mock_create).to_blocks() if blk["type"] == "blockquote")
        assert "автоматически" in quote["credit"]

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_hard_block_without_autoblock_stays_advice(self, mock_create):
        cfg = MagicMock()
        cfg.get.side_effect = lambda key, default=None: (
            False if key == "violation_auto_hard_block" else default
        )
        with patch("shared.config_service.config_service", cfg):
            await send_violation_notification(
                user_uuid="uuid-3",
                violation_score={"total": 97.0, "breakdown": {}, "recommended_action": "hard_block"},
            )

        body = _body_of(mock_create)
        assert "Рекомендация: <b>ЗАБЛОКИРОВАТЬ</b>" in body
        assert "решение за администратором" in body

    def test_labels_cover_every_action(self):
        """Словарь и enum не должны разъезжаться — иначе в карточке всплывёт ключ."""
        from shared.analyzers.models import ACTION_LABELS, ViolationAction

        assert {a.value for a in ViolationAction} == set(ACTION_LABELS)

    def test_soft_block_no_longer_promises_a_missing_mechanism(self):
        """Ограничивать скорость проект не умеет — название не должно это обещать."""
        from shared.analyzers.models import ACTION_LABELS

        assert "блокировк" not in ACTION_LABELS["soft_block"]


# ── Кнопки белого списка в реально работающем уведомителе ─────


class TestWhitelistButtons:
    def test_partial_button_follows_the_analyzer_that_fired(self):
        from web.backend.core.violation_notifier import _violation_keyboard

        rows = _violation_keyboard("uuid-1", "hwid")["inline_keyboard"]
        last = rows[-1]
        assert [b["callback_data"] for b in last] == ["vact:wl:uuid-1", "vact:wlp_hwid:uuid-1"]
        assert "HWID" in last[1]["text"]

    def test_only_full_whitelist_when_no_analyzer_stands_out(self):
        from web.backend.core.violation_notifier import _violation_keyboard

        last = _violation_keyboard("uuid-1", None)["inline_keyboard"][-1]
        assert [b["callback_data"] for b in last] == ["vact:wl:uuid-1"]

    def test_torrent_card_has_no_whitelist_row(self):
        """Торрент ловится мимо анализаторов — белый список на него не влияет."""
        from web.backend.core.violation_notifier import _violation_keyboard

        rows = _violation_keyboard("uuid-1", with_whitelist=False)["inline_keyboard"]
        flat = [b["callback_data"] for row in rows for b in row]
        assert not any(cd.startswith("vact:wl") for cd in flat)

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_notification_carries_the_whitelist_buttons(self, mock_create):
        """Регрессия: кнопки жили в функции бота, которую никто не вызывает."""
        await send_violation_notification(
            user_uuid="uuid-9",
            violation_score={
                "total": 80.0,
                "breakdown": {"geo": {"score": 10.0}, "hwid": {"score": 70.0}},
                "recommended_action": "temp_block",
            },
        )

        # кнопки встроены в само rich-сообщение, клавиатура — только для фолбэка
        assert mock_create.call_args.kwargs.get("reply_markup") is None
        card = _card_of(mock_create)
        embedded = [btn["callback_data"] for blk in card.to_blocks() if blk["type"] == "buttons"
                    for btn in blk["buttons"]]
        assert "vact:wl:uuid-9" in embedded
        assert "vact:wlp_hwid:uuid-9" in embedded
        fallback = [btn["callback_data"] for row in card.keyboard()["inline_keyboard"] for btn in row]
        assert fallback == embedded

    def test_buttons_are_colored_by_consequence(self):
        from web.backend.core.violation_notifier import _violation_keyboard

        styles = {btn["callback_data"].split(":")[1]: btn.get("style")
                  for row in _violation_keyboard("u", "geo")["inline_keyboard"] for btn in row}
        assert styles["block"] == styles["kill"] == "danger"
        assert styles["dismiss"] == styles["wl"] == styles["wlp_geo"] == "success"
        assert styles["info"] == "primary"


class TestRichCard:
    def setup_method(self):
        _violation_notification_cache.clear()

    def teardown_method(self):
        _violation_notification_cache.clear()

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_connections_go_to_a_table(self, mock_create):
        conns = [SimpleNamespace(ip_address="10.0.0.2", node_uuid=None),
                 SimpleNamespace(ip_address="10.0.0.1", node_uuid=None)]
        meta = {"10.0.0.1": SimpleNamespace(asn_org="MTS PJSC", country_code="RU")}
        await send_violation_notification(
            user_uuid="uuid-t",
            violation_score={"total": 70.0, "breakdown": {}},
            user_info={"username": "alex", "hwidDeviceLimit": 1},
            active_connections=conns,
            ip_metadata=meta,
        )
        tables = [blk for blk in _card_of(mock_create).to_blocks() if blk["type"] == "table"]
        connections = next(t for t in tables if t["cells"][0][0]["text"] == "IP")
        assert [row[0]["text"] for row in connections["cells"][1:]] == [
            {"type": "code", "text": "10.0.0.1"}, {"type": "code", "text": "10.0.0.2"}]
        assert connections["cells"][1][1]["text"] == "MTS PJSC"
        assert connections["cells"][2][1]["text"] == "—"  # провайдер неизвестен

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_history_dates_are_shown_in_reader_timezone(self, mock_create):
        recap = {"days": 30, "total": 3, "annulled": 1,
                 "items": [(datetime(2026, 10, 1, 9, 0), True), (datetime(2026, 9, 20, 18, 30), False)]}
        with patch.object(vn, "_recap", AsyncMock(return_value=recap)):
            await send_violation_notification(
                user_uuid="uuid-h",
                violation_score={"total": 70.0, "breakdown": {}},
                user_info={"username": "alex", "hwidDeviceLimit": 1},
            )
        history = next(blk for blk in _card_of(mock_create).to_blocks() if blk["type"] == "details"
                       and "Нарушений за 30" in str(blk["summary"]))
        items = history["blocks"][0]["items"]
        first = items[0]["blocks"][0]["text"]
        assert first[0]["type"] == "date_time" and "аннулировано" in first[-1]

    @patch("web.backend.core.notification_service.create_notification", new_callable=AsyncMock)
    async def test_user_text_cannot_break_markup(self, mock_create):
        await send_violation_notification(
            user_uuid="uuid-x",
            violation_score={"total": 70.0, "breakdown": {}},
            user_info={"username": "<b>evil</b>", "description": "a & b", "hwidDeviceLimit": 1},
        )
        html = _body_of(mock_create)
        assert "<b>evil</b>" not in html and "&lt;b&gt;evil&lt;/b&gt;" in html
