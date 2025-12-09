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
                data = json.loads(json_path.read_text(encoding="utf-8"))
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

    return SimpleI18nMiddleware(i18n=i18n)
