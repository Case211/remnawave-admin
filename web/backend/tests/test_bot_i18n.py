"""Тесты JsonI18n — перевода бота.

Живут в backend-тестах намеренно: conftest бота подменяет весь aiogram
моками, а тут нужен настоящий I18n — переопределённый gettext вызывает
базовый.
"""
import pytest

from src.utils.i18n import JsonI18n, BASE_LOCALES_PATH


@pytest.fixture
def i18n():
    return JsonI18n(path=BASE_LOCALES_PATH, default_locale="ru", domain="messages")


class TestGettextDefault:
    """Регрессия #274: `_("ключ", default="текст")` ронял хендлеры бота
    с TypeError, и кнопки подтверждения не отрисовывались."""

    def test_default_kwarg_accepted(self, i18n):
        assert i18n.gettext("user.disable_confirm", default="Отключить?", locale="ru")

    def test_translation_wins_over_default(self, i18n):
        assert i18n.gettext("common.cancel", default="ЗАПАСНОЙ", locale="ru") != "ЗАПАСНОЙ"

    def test_default_used_when_key_missing(self, i18n):
        assert i18n.gettext("nope.missing.key", default="Запасной", locale="ru") == "Запасной"

    def test_key_returned_when_no_default(self, i18n):
        """Без запасного текста поведение прежнее — gettext отдаёт сам msgid."""
        assert i18n.gettext("nope.missing.key", locale="ru") == "nope.missing.key"


class TestConfirmationKeys:
    """Тексты подтверждений должны быть в обеих локалях: иначе английский
    интерфейс показывал бы русские запасные строки."""

    @pytest.mark.parametrize("key", [
        "common.confirm",
        "common.cancel",
        "bulk.confirm_warning",
        "node.restart_confirm",
        "node.restart_warning",
        "node.reset_confirm",
        "user.disable_confirm",
        "user.disable_confirm_button",
    ])
    @pytest.mark.parametrize("locale", ["ru", "en"])
    def test_key_translated(self, i18n, key, locale):
        assert i18n.gettext(key, locale=locale) != key
