import logging
from typing import Any, Optional
from src.config import get_settings


# Короткие имена для сторонних логгеров, чтобы вывод был единообразным
_LOGGER_NAME_MAP = {
    "remnawave-admin-bot": "bot",
    "uvicorn.error": "uvicorn",
    "uvicorn.access": "uvicorn",
    "aiogram.event": "aiogram",
    "aiogram.dispatcher": "aiogram",
    "aiogram.middlewares": "aiogram",
    "aiogram.webhook": "aiogram",
    "web.backend.api.deps": "web",
    "web.backend.core.api_helper": "web",
    "httpx": "http",
    "httpcore": "http",
    "asyncpg": "db",
    "alembic": "migration",
    "sqlalchemy": "db",
}


class CleanFormatter(logging.Formatter):
    """Компактный форматтер с короткими именами логгеров."""

    def format(self, record: logging.LogRecord) -> str:
        # Сокращаем имя логгера
        name = record.name
        for prefix, short in _LOGGER_NAME_MAP.items():
            if name == prefix or name.startswith(prefix + "."):
                record.name = short
                break
        else:
            # Для неизвестных — берём последнюю часть имени
            if "." in name:
                record.name = name.rsplit(".", 1)[-1]

        return super().format(record)


def setup_logger() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    # Удаляем стандартные обработчики
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setLevel(level)
    formatter = CleanFormatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s",
        datefmt="%H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)

    # Подавляем шумные сторонние логгеры
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(level)

    return logging.getLogger("remnawave-admin-bot")


logger = setup_logger()


def log_user_action(
    action: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    level: int = logging.INFO,
) -> None:
    """Логирует действие пользователя в структурированном формате."""
    parts = [f"👤 {action}"]

    if user_id:
        parts.append(f"id={user_id}")
    if username:
        parts.append(f"@{username}")
    if details:
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
        parts.append(detail_str)

    logger.log(level, " | ".join(parts))


def log_button_click(callback_data: str, user_id: Optional[int] = None, username: Optional[str] = None) -> None:
    """Логирует нажатие на кнопку."""
    log_user_action(
        "button_click",
        user_id=user_id,
        username=username,
        details={"callback": callback_data},
    )


def log_command(command: str, user_id: Optional[int] = None, username: Optional[str] = None, args: Optional[str] = None) -> None:
    """Логирует выполнение команды."""
    details = {"cmd": command}
    if args:
        details["args"] = args
    log_user_action(
        "command",
        user_id=user_id,
        username=username,
        details=details,
    )


def log_user_input(field: str, user_id: Optional[int] = None, username: Optional[str] = None, preview: Optional[str] = None) -> None:
    """Логирует ввод данных пользователем."""
    details = {"field": field}
    if preview:
        details["preview"] = preview[:50] + ("..." if len(preview) > 50 else "")
    log_user_action(
        "input",
        user_id=user_id,
        username=username,
        details=details,
    )


def log_api_call(method: str, endpoint: str, status_code: Optional[int] = None, duration_ms: Optional[float] = None) -> None:
    """Логирует вызов API."""
    parts = [f"🌐 {method} {endpoint}"]
    if status_code:
        parts.append(f"status={status_code}")
    if duration_ms is not None:
        parts.append(f"{duration_ms:.0f}ms")
    logger.info(" | ".join(parts))


def log_api_error(method: str, endpoint: str, error: Exception, status_code: Optional[int] = None) -> None:
    """Логирует ошибку API."""
    parts = [f"❌ {method} {endpoint}"]
    if status_code:
        parts.append(f"status={status_code}")
    parts.append(f"{type(error).__name__}: {error}")
    logger.error(" | ".join(parts))
