"""Кнопка «Открыть панель» (Telegram Mini App) в главном меню бота.

WebApp-кнопки Telegram принимает только в приватных чатах — в группе она
уронила бы всё сообщение с меню. Плюс URL обязан быть https, иначе Telegram
откажется открывать мини-приложение.
"""
import os
from unittest.mock import patch

import pytest

from src.utils.chat_context import set_current_chat_type
from src.utils.panel_link import panel_web_app_url


@pytest.fixture(autouse=True)
def _private_chat():
    set_current_chat_type("private")
    yield
    set_current_chat_type(None)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    monkeypatch.delenv("WEB_SECRET_PATH", raising=False)


class TestPanelWebAppUrl:
    def test_none_when_not_configured(self):
        assert panel_web_app_url() is None

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com/")
        assert panel_web_app_url() == "https://panel.example.com"

    def test_http_rejected(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "http://panel.example.com")
        assert panel_web_app_url() is None

    def test_setting_wins_over_env(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "https://from-env.example.com")

        def fake_get(key, default=None):
            if key == "web_panel_public_url":
                return "https://from-setting.example.com"
            return default

        with patch("shared.config_service.config_service") as cs:
            cs._initialized = True
            cs.get.side_effect = fake_get
            assert panel_web_app_url() == "https://from-setting.example.com"

    def test_secret_path_from_env(self, monkeypatch):
        """WEB_SECRET_PATH — та же переменная, из которой префикс берёт фронт."""
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com")
        monkeypatch.setenv("WEB_SECRET_PATH", "/s3cret/")
        assert panel_web_app_url() == "https://panel.example.com/s3cret"

    def test_secret_path_from_config_when_env_empty(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com")

        def fake_get(key, default=None):
            if key == "secret_path":
                return "s3cret"
            return default

        with patch("shared.config_service.config_service") as cs:
            cs._initialized = True
            cs.get.side_effect = fake_get
            assert panel_web_app_url() == "https://panel.example.com/s3cret"

    def test_no_secret_path(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com")
        assert panel_web_app_url() == "https://panel.example.com"


class TestPanelWebAppButton:
    """aiogram в тестах бота замокан целиком, поэтому смотрим на вызовы
    WebAppInfo/InlineKeyboardButton, а не на поля готовых объектов."""

    def test_button_built_in_private_chat(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com")
        from src.keyboards import main_menu

        with patch.object(main_menu, "WebAppInfo") as web_app:
            assert main_menu.panel_web_app_button() is not None
            web_app.assert_called_once_with(url="https://panel.example.com")

    def test_no_button_outside_private_chat(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com")
        from src.keyboards import main_menu

        set_current_chat_type("supergroup")
        with patch.object(main_menu, "WebAppInfo") as web_app:
            assert main_menu.panel_web_app_button() is None
            web_app.assert_not_called()

    def test_no_button_without_url(self):
        from src.keyboards import main_menu

        with patch.object(main_menu, "WebAppInfo") as web_app:
            assert main_menu.panel_web_app_button() is None
            web_app.assert_not_called()

    def test_main_menu_keeps_working_in_group(self, monkeypatch):
        """Меню в группе строится без WebApp-кнопки, а не падает."""
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com")
        from src.keyboards import main_menu

        set_current_chat_type("supergroup")
        with patch.object(main_menu, "InlineKeyboardMarkup") as markup, \
                patch.object(main_menu, "WebAppInfo") as web_app:
            main_menu.main_menu_keyboard()
            rows = markup.call_args.kwargs["inline_keyboard"]
            assert rows, "меню не должно быть пустым"
            web_app.assert_not_called()

    def test_main_menu_has_button_in_private_chat(self, monkeypatch):
        monkeypatch.setenv("APP_PUBLIC_URL", "https://panel.example.com")
        from src.keyboards import main_menu

        with patch.object(main_menu, "InlineKeyboardMarkup") as markup, \
                patch.object(main_menu, "WebAppInfo") as web_app:
            main_menu.main_menu_keyboard()
            rows = markup.call_args.kwargs["inline_keyboard"]
            assert rows
            web_app.assert_called_once_with(url="https://panel.example.com")

