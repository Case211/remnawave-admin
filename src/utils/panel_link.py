"""Публичный адрес веб-панели для кнопки Telegram Mini App.

Источник — настройка ``web_panel_public_url`` (bot_config, редактируется в
веб-панели), с откатом на переменную окружения ``APP_PUBLIC_URL`` — ту же,
из которой веб-панель строит ссылки в письмах. Если задан secret_path,
он подставляется в путь, как это делает бэкенд для ссылок сброса пароля.

Telegram открывает Mini App только по HTTPS, поэтому любой другой адрес
считается ненастроенным и кнопка просто не показывается.
"""
import os


def panel_web_app_url() -> str | None:
    """https-URL панели для WebAppInfo или None, если он не настроен."""
    base = ""
    try:
        from shared.config_service import config_service

        if config_service._initialized:
            base = (config_service.get("web_panel_public_url", "") or "").strip()
    except Exception:
        base = ""

    if not base:
        base = (os.getenv("APP_PUBLIC_URL", "") or "").strip()

    base = base.rstrip("/")
    if not base.startswith("https://"):
        return None

    secret_path = ""
    try:
        from shared.config_service import config_service

        if config_service._initialized:
            secret_path = (config_service.get("secret_path", "") or "").strip()
    except Exception:
        secret_path = ""

    if secret_path:
        base = f"{base}/{secret_path.strip('/')}"

    return base
