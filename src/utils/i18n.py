import gettext
import json
from pathlib import Path
from typing import Dict, Iterable, Tuple

from aiogram.utils.i18n import I18n, I18nMiddleware

from src.config import get_settings

BASE_LOCALES_PATH = Path(__file__).resolve().parent.parent.parent / "locales"


def _flatten_translations(data: dict, prefix: str = "") -> Iterable[Tuple[str, str]]:
    """Flatten nested dict into dot-separated keys."""
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten_translations(value, full_key)
        else:
            yield full_key, str(value)


class JsonTranslations(gettext.NullTranslations):
    """Minimal gettext-compatible translations backed by JSON files."""

    def __init__(self, messages: Dict[str, str]) -> None:
        super().__init__()
        self._messages = messages

    def gettext(self, message: str) -> str:  # type: ignore[override]
        return self._messages.get(message, message)

    def ngettext(self, singular: str, plural: str, n: int) -> str:  # type: ignore[override]
        msgid = singular if n == 1 else plural
        return self._messages.get(msgid, msgid)


class JsonI18n(I18n):
    """I18n loader that reads locales/<lang>/messages.json (nested keys allowed)."""

    def find_locales(self) -> Dict[str, gettext.NullTranslations]:  # type: ignore[override]
        translations: Dict[str, gettext.NullTranslations] = {}
        base_path = Path(self.path)

        for locale_dir in base_path.iterdir():
            if not locale_dir.is_dir():
                continue
            json_path = locale_dir / f"{self.domain}.json"
            if not json_path.is_file():
                continue
            try:
                # messages.json are stored with UTF-8 BOM, use utf-8-sig to strip it
                data = json.loads(json_path.read_text(encoding="utf-8-sig"))
                flat = dict(_flatten_translations(data))
                translations[locale_dir.name] = JsonTranslations(flat)
            except json.JSONDecodeError:
                continue

        return translations


def get_i18n() -> I18n:
    settings = get_settings()
    return JsonI18n(path=BASE_LOCALES_PATH, default_locale=settings.default_locale, domain="messages")


def get_i18n_middleware() -> I18nMiddleware:
    i18n = get_i18n()

    class SimpleI18nMiddleware(I18nMiddleware):
        async def get_locale(self, event, data) -> str:  # type: ignore[override]
            user = getattr(event, "from_user", None)
            if user:
                lang = getattr(user, "language_code", None)
                if lang and lang in self.i18n.available_locales:
                    return lang
                if lang and "-" in lang:
                    base_lang = lang.split("-")[0]
                    if base_lang in self.i18n.available_locales:
                        return base_lang
            return self.i18n.default_locale

        async def __call__(self, handler, event, data):  # type: ignore[override]
            current_locale = await self.get_locale(event=event, data=data) or self.i18n.default_locale

            if self.i18n_key:
                data[self.i18n_key] = self.i18n
            if self.middleware_key:
                data[self.middleware_key] = self

            base_token = I18n.set_current(self.i18n)
            self_token = self.i18n.set_current(self.i18n)
            try:
                with self.i18n.use_locale(current_locale):
                    return await handler(event, data)
            finally:
                self.i18n.reset_current(self_token)
                I18n.reset_current(base_token)

    return SimpleI18nMiddleware(i18n=i18n)
