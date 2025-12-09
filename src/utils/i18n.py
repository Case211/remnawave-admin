from pathlib import Path

from aiogram.utils.i18n import I18n, I18nMiddleware

from src.config import get_settings

BASE_LOCALES_PATH = Path(__file__).resolve().parent.parent.parent / "locales"


def get_i18n() -> I18n:
    settings = get_settings()
    return I18n(path=BASE_LOCALES_PATH, default_locale=settings.default_locale, domain="messages")


def get_i18n_middleware() -> I18nMiddleware:
    i18n = get_i18n()
    return I18nMiddleware(i18n=i18n)
