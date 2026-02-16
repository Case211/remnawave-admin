"""Tests for notification delivery service — multi-channel dispatch."""
import json

import pytest
from unittest.mock import patch, AsyncMock, MagicMock

from web.backend.core.notification_service import (
    _get_global_telegram_config,
    _build_html_email,
)


class TestGetGlobalTelegramConfig:
    """Tests for _get_global_telegram_config."""

    @patch("web.backend.core.config.get_web_settings")
    def test_returns_config_tuple(self, mock_settings):
        s = MagicMock()
        s.telegram_bot_token = "123:ABC"
        s.notifications_chat_id = "12345"
        s.get_topic_for = MagicMock(return_value=99)
        mock_settings.return_value = s

        bot_token, chat_id, topic_id = _get_global_telegram_config("service")
        assert bot_token == "123:ABC"
        assert chat_id == "12345"
        assert topic_id == 99

    @patch("web.backend.core.config.get_web_settings")
    def test_no_chat_id(self, mock_settings):
        s = MagicMock()
        s.telegram_bot_token = "123:ABC"
        s.notifications_chat_id = None
        s.get_topic_for = MagicMock(return_value=None)
        mock_settings.return_value = s

        bot_token, chat_id, topic_id = _get_global_telegram_config()
        assert chat_id is None

    @patch("web.backend.core.config.get_web_settings", side_effect=Exception("no settings"))
    def test_exception_returns_nones(self, mock_settings):
        result = _get_global_telegram_config()
        assert result == (None, None, None)


class TestBuildHtmlEmail:
    """Tests for _build_html_email template builder."""

    def test_basic_email(self):
        html = _build_html_email("Test Title", "Test body text")
        assert "Test Title" in html
        assert "Test body text" in html
        assert "<!DOCTYPE html>" in html

    def test_severity_color_warning(self):
        html = _build_html_email("Alert", "body", severity="warning")
        assert "#f59e0b" in html

    def test_severity_color_critical(self):
        html = _build_html_email("Alert", "body", severity="critical")
        assert "#ef4444" in html

    def test_severity_color_success(self):
        html = _build_html_email("Alert", "body", severity="success")
        assert "#22c55e" in html

    def test_default_severity_info(self):
        html = _build_html_email("Alert", "body", severity="info")
        assert "#22d3ee" in html

    def test_link_included(self):
        html = _build_html_email("Title", "body", link="https://panel.example.com/users")
        assert "https://panel.example.com/users" in html
        assert "Open in panel" in html

    def test_no_link(self):
        html = _build_html_email("Title", "body")
        assert "Open in panel" not in html

    def test_unknown_severity_uses_default_color(self):
        html = _build_html_email("Title", "body", severity="custom")
        assert "#22d3ee" in html  # default info color
