# Аннотации строками: у JsonI18n есть метод gettext, и в теле класса он
# затеняет одноимённый модуль — без этого `-> Dict[str, gettext.NullTranslations]`
# в сигнатуре find_locales падал бы AttributeError ещё на импорте.
from __future__ import annotations

import gettext
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Tuple

from aiogram.utils.i18n import I18n, I18nMiddleware

from src.config import get_settings

BASE_LOCALES_PATH = Path(__file__).resolve().parent.parent.parent / "locales"

# Cache for `tr()` lookup: locale -> {flat_key: value}. Invalidated when the
# bot's language changes (admin flips bot_language in DB / .env).
_locale_translations: Dict[str, Dict[str, str]] = {}
_locale_cache_lang: str | None = None


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

    def gettext(  # type: ignore[override]
        self,
        singular: str,
        plural: str | None = None,
        n: int = 1,
        locale: str | None = None,
        default: str | None = None,
    ) -> str:
        """Перевод с запасным текстом.

        Хендлеры зовут `_("user.disable_confirm", default="Отключить?")`,
        а базовый `I18n.gettext()` такого аргумента не знает — вызов падал
        с TypeError, и кнопки подтверждения в боте не отрисовывались
        (issue #274). Ключа в JSON может не быть: gettext в таком случае
        возвращает сам msgid, и пользователь увидел бы «user.disable_confirm»
        вместо текста, — поэтому запасной текст здесь и нужен.
        """
        text = super().gettext(singular, plural, n, locale)
        if default is not None and text in (singular, plural):
            return default
        return text

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


def _get_bot_language() -> str:
    """Get bot language from config_service (DB > .env > default)."""
    try:
        from shared.config_service import config_service
        if config_service._initialized:
            lang = config_service.get("bot_language")
            if lang:
                return lang
    except Exception:
        pass
    # Fallback to static settings
    return get_settings().default_locale


def get_i18n() -> I18n:
    settings = get_settings()
    return JsonI18n(path=BASE_LOCALES_PATH, default_locale=settings.default_locale, domain="messages")


def get_i18n_middleware() -> I18nMiddleware:
    i18n = get_i18n()

    class SimpleI18nMiddleware(I18nMiddleware):
        async def get_locale(self, event, data) -> str:  # type: ignore[override]
            # Динамически читаем язык из config_service (БД) при каждом запросе
            default_lang = _get_bot_language()

            user = getattr(event, "from_user", None)
            if user:
                lang = getattr(user, "language_code", None)
                if lang and lang in self.i18n.available_locales:
                    return lang
                if lang and "-" in lang:
                    base_lang = lang.split("-")[0]
                    if base_lang in self.i18n.available_locales:
                        return base_lang

            return default_lang

        async def __call__(self, handler, event, data):  # type: ignore[override]
            current_locale = await self.get_locale(event=event, data=data) or _get_bot_language()

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


def _load_translations_for(lang: str) -> Dict[str, str]:
    """Load and flatten locales/<lang>/messages.json. Cached per-process."""
    if lang in _locale_translations:
        return _locale_translations[lang]
    path = BASE_LOCALES_PATH / lang / "messages.json"
    try:
        raw = path.read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        flat = dict(_flatten_translations(data))
    except (FileNotFoundError, json.JSONDecodeError):
        flat = {}
    _locale_translations[lang] = flat
    return flat


def invalidate_locale_cache() -> None:
    """Drop the per-process translation cache (call when the bot's
    language is changed at runtime via config_service)."""
    _locale_translations.clear()
    _locale_cache_lang = None  # noqa: F841 — keep reference shape consistent


def tr(key: str, /, **kwargs: Any) -> str:
    """Translate a key using the current bot language.

    Intended for non-handler contexts (background tasks, health checks,
    webhook notifications) where there is no per-user `i18n.use_locale`
    context. Handler code should keep using `from aiogram.utils.i18n
    import gettext as _` so per-user locales still apply.

    Looks up the key in the locale currently configured for the bot
    (config_service → .env → default). Falls back to the key itself if
    missing. Format placeholders in `**kwargs` are applied via str.format.
    """
    try:
        lang = _get_bot_language()
        flat = _load_translations_for(lang)
        template = flat.get(key)
        if template is None and lang != get_settings().default_locale:
            # Fall back to default locale if the active one is missing the key
            flat = _load_translations_for(get_settings().default_locale)
            template = flat.get(key)
        if template is None:
            template = key
    except Exception:
        template = key

    if kwargs:
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return template
    return template
