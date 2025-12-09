from pathlib import Path

from aiogram.utils.i18n import I18n, I18nMiddleware

from src.config import get_settings

BASE_LOCALES_PATH = Path(__file__).resolve().parent.parent.parent / "locales"


def get_i18n() -> I18n:
    settings = get_settings()
    return I18n(path=BASE_LOCALES_PATH, default_locale=settings.default_locale, domain="messages")


def get_i18n_middleware() -> I18nMiddleware:
    i18n = get_i18n()

    class SimpleI18nMiddleware(I18nMiddleware):
        async def get_locale(self, event, data) -> str:  # type: ignore[override]
            user = getattr(event, "from_user", None)
            if user:
                lang = getattr(user, "language_code", None)
                if lang and self.i18n.is_locale_available(lang):
                    return lang
                if lang and "-" in lang:
                    base_lang = lang.split("-")[0]
                    if self.i18n.is_locale_available(base_lang):
                        return base_lang
            return self.i18n.default_locale

    return SimpleI18nMiddleware(i18n=i18n)
