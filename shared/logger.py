import gzip
import json
import logging
import os
import shutil
import sys
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

import structlog

from shared.config import get_shared_settings as get_settings


# Короткие имена для сторонних логгеров
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

# Ротация: 10 MB, 5 файлов, с gzip-сжатием
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5
_LOG_DIR = Path("/app/logs")


class CompressedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler с gzip-сжатием ротированных файлов."""

    def doRollover(self):
        """Ротация + сжатие старых файлов."""
        if self.stream:
            self.stream.close()
            self.stream = None

        for i in range(self.backupCount - 1, 0, -1):
            sfn = self.rotation_filename(f"{self.baseFilename}.{i}.gz")
            dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}.gz")
            if os.path.exists(sfn):
                if os.path.exists(dfn):
                    os.remove(dfn)
                os.rename(sfn, dfn)

        dfn = self.rotation_filename(f"{self.baseFilename}.1.gz")
        if os.path.exists(dfn):
            os.remove(dfn)
        if os.path.exists(self.baseFilename):
            with open(self.baseFilename, "rb") as f_in:
                with gzip.open(dfn, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            with open(self.baseFilename, "w"):
                pass

        if not self.delay:
            self.stream = self._open()


class ViolationLogFilter(logging.Filter):
    """Фильтр для выделения записей, связанных с нарушениями, в отдельный лог-файл."""

    _SOURCE_MODULES = (
        "violation_detector", "connection_monitor", "collector", "geoip",
        "violation_reports", "maxmind", "violation_notifier",
    )
    _KEYWORDS = (
        "violation detected", "violation for user", "violation saved",
        "violation score", "violation_score", "save_violation",
        "score=", "ip_metadata", "geoip",
        "temporal", "geo_score", "asn_score", "impossible_travel",
        "agent token", "ip lookup",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        name_lower = record.name.lower()
        for mod in self._SOURCE_MODULES:
            if mod in name_lower:
                return True
        msg_lower = str(record.getMessage()).lower()
        return any(kw in msg_lower for kw in self._KEYWORDS)


def _shorten_logger_name(logger: object, method_name: str, event_dict: dict) -> dict:
    """structlog processor: сокращает имена логгеров."""
    name = event_dict.get("logger", "")
    for prefix, short in _LOGGER_NAME_MAP.items():
        if name == prefix or name.startswith(prefix + "."):
            event_dict["logger"] = short
            return event_dict
    if "." in name:
        event_dict["logger"] = name.rsplit(".", 1)[-1]
    return event_dict


def _compact_kv(logger: object, method_name: str, event_dict: dict) -> dict:
    """structlog processor: компактный формат для api_call и api_error."""
    event = event_dict.get("event", "")
    if event == "api_call":
        method = event_dict.pop("method", "")
        endpoint = event_dict.pop("endpoint", "")
        status = event_dict.pop("status_code", "")
        duration = event_dict.pop("duration_ms", "")
        parts = []
        if method and endpoint:
            parts.append(f"{method} {endpoint}")
        if status:
            parts.append(f"→ {status}")
        if duration:
            parts.append(f"({duration}ms)")
        event_dict["event"] = " ".join(parts) if parts else event
    elif event == "api_error":
        method = event_dict.pop("method", "")
        endpoint = event_dict.pop("endpoint", "")
        status = event_dict.pop("status_code", "")
        error = event_dict.pop("error", "")
        parts = []
        if method and endpoint:
            parts.append(f"{method} {endpoint}")
        if status:
            parts.append(f"→ {status}")
        if error:
            parts.append(f"| {error}")
        event_dict["event"] = " ".join(parts) if parts else event
    return event_dict


# Цвета уровней логирования (ANSI)
_LEVEL_STYLES = {
    "critical": "\033[1;91m",   # bold bright red
    "exception": "\033[1;91m",  # bold bright red
    "error": "\033[91m",        # bright red
    "warn": "\033[93m",         # bright yellow
    "warning": "\033[93m",      # bright yellow
    "info": "\033[36m",         # cyan
    "debug": "\033[2;37m",      # dim white
    "notset": "\033[2m",        # dim
}


def _make_console_renderer() -> structlog.dev.ConsoleRenderer:
    """Создаёт ConsoleRenderer с красивым форматированием."""
    return structlog.dev.ConsoleRenderer(
        colors=True,
        force_colors=True,
        pad_event_to=40,
        level_styles=_LEVEL_STYLES,
    )


def _ensure_log_dir() -> Path:
    """Создаёт директорию для логов если не существует."""
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    return _LOG_DIR


def setup_logger() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    # === Общие structlog процессоры ===
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    # === Console handler (цветной вывод) ===
    console = logging.StreamHandler()
    console.setLevel(level)
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _shorten_logger_name,
            _compact_kv,
            _make_console_renderer(),
        ],
        foreign_pre_chain=shared_processors,
    )
    console.setFormatter(console_formatter)
    root.addHandler(console)

    # === File handlers ===
    try:
        log_dir = _ensure_log_dir()

        # JSON formatter для файлов
        json_formatter = structlog.stdlib.ProcessorFormatter(
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _shorten_logger_name,
                structlog.processors.JSONRenderer(),
            ],
            foreign_pre_chain=shared_processors,
        )

        # Единый файл bot.log (INFO+)
        bot_path = log_dir / "bot.log"
        bot_handler = CompressedRotatingFileHandler(
            filename=str(bot_path),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        bot_handler.setLevel(logging.INFO)
        bot_handler.setFormatter(json_formatter)
        root.addHandler(bot_handler)

        # Violations файл (фильтрует записи о нарушениях из всех источников)
        violations_path = log_dir / "violations.log"
        violations_handler = CompressedRotatingFileHandler(
            filename=str(violations_path),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        violations_handler.setLevel(logging.DEBUG)
        violations_handler.setFormatter(json_formatter)
        violations_handler.addFilter(ViolationLogFilter())
        root.addHandler(violations_handler)

        _verify_ok = bot_path.exists() and os.access(bot_path, os.W_OK)
        print(
            f"[LOGGING] File logging active: {log_dir} "
            f"(writable={_verify_ok})",
            file=sys.stderr,
            flush=True,
        )

    except OSError as exc:
        console.setLevel(level)
        root.warning("Cannot create log files (%s), logging to console only", exc)
        print(
            f"[LOGGING] File logging DISABLED: {exc}. "
            f"Check that the volume mount is correct (./logs:/app/logs, NOT .logs:/app/logs)",
            file=sys.stderr,
            flush=True,
        )

    # Подавляем шумные сторонние логгеры
    http_level = logging.DEBUG if level <= logging.DEBUG else logging.WARNING
    logging.getLogger("httpx").setLevel(http_level)
    logging.getLogger("httpcore").setLevel(http_level)
    logging.getLogger("asyncpg").setLevel(logging.WARNING)
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(level)

    # Конфигурируем structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    return logging.getLogger("remnawave-admin-bot")


logger = setup_logger()


def set_log_level(level_name: str) -> None:
    """Динамически изменяет уровень логирования для всех хэндлеров без перезапуска."""
    level = getattr(logging, level_name.upper(), logging.INFO)
    root = logging.getLogger()

    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, RotatingFileHandler):
            handler.setLevel(level)
        elif isinstance(handler, RotatingFileHandler):
            base = os.path.basename(handler.baseFilename)
            if "violations" not in base:
                handler.setLevel(level)

    http_level = logging.DEBUG if level <= logging.DEBUG else logging.WARNING
    logging.getLogger("httpx").setLevel(http_level)
    logging.getLogger("httpcore").setLevel(http_level)
    logging.getLogger("aiogram").setLevel(level)

    logger.info("Log level changed to %s", level_name.upper())


def set_rotation_params(max_bytes: int, backup_count: int) -> None:
    """Динамически обновляет параметры ротации для всех файловых хэндлеров."""
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, RotatingFileHandler):
            handler.maxBytes = max_bytes
            handler.backupCount = backup_count
    logger.info("Log rotation updated: max_bytes=%d, backup_count=%d", max_bytes, backup_count)


def log_user_action(
    action: str,
    user_id: Optional[int] = None,
    username: Optional[str] = None,
    details: Optional[dict[str, Any]] = None,
    level: int = logging.INFO,
) -> None:
    """Логирует действие пользователя в структурированном формате."""
    log = structlog.get_logger("bot.user")
    kwargs: dict[str, Any] = {"action": action}
    if user_id:
        kwargs["user_id"] = user_id
    if username:
        kwargs["username"] = username
    if details:
        kwargs.update(details)
    log.log(level, action, **kwargs)


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
    details: dict[str, Any] = {"cmd": command}
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
    details: dict[str, Any] = {"field": field}
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
    log = structlog.get_logger("bot.api")
    kwargs: dict[str, Any] = {"method": method, "endpoint": endpoint}
    if status_code:
        kwargs["status_code"] = status_code
    if duration_ms is not None:
        kwargs["duration_ms"] = round(duration_ms)
    log.info("api_call", **kwargs)


def log_api_error(method: str, endpoint: str, error: Exception, status_code: Optional[int] = None) -> None:
    """Логирует ошибку API."""
    log = structlog.get_logger("bot.api")
    kwargs: dict[str, Any] = {"method": method, "endpoint": endpoint, "error": f"{type(error).__name__}: {error}"}
    if status_code:
        kwargs["status_code"] = status_code
    log.error("api_error", **kwargs)
