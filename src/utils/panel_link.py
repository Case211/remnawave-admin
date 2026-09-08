"""Публичный адрес веб-панели для кнопки Telegram Mini App.

Источник — настройка ``web_panel_public_url`` (bot_config, редактируется в
веб-панели), с откатом на переменную окружения ``APP_PUBLIC_URL`` — ту же,
из которой веб-панель строит ссылки в письмах.

Secret path берётся из ``WEB_SECRET_PATH``: именно эту переменную читает
docker-entrypoint фронта, когда прячет панель за префиксом. Ключа
``secret_path`` в bot_config нет, но он опрошен запасным вариантом — на
случай, если настройка появится позже.

Telegram открывает Mini App только по HTTPS, поэтому любой другой адрес
считается ненастроенным и кнопка просто не показывается.
"""
import os


def _from_config(key: str) -> str:
    """Значение настройки из bot_config; пустая строка, если её нет."""
    try:
        from shared.config_service import config_service

        if config_service._initialized:
            return (config_service.get(key, "") or "").strip()
    except Exception:
        pass
    return ""


def panel_web_app_url() -> str | None:
    """https-URL панели для WebAppInfo или None, если он не настроен."""
    base = _from_config("web_panel_public_url")
    if not base:
        base = (os.getenv("APP_PUBLIC_URL", "") or "").strip()

    base = base.rstrip("/")
    if not base.startswith("https://"):
        return None

    secret_path = (os.getenv("WEB_SECRET_PATH", "") or "").strip()
    if not secret_path:
        secret_path = _from_config("secret_path")

    secret_path = secret_path.strip("/")
    if secret_path:
        base = f"{base}/{secret_path}"

    return base
