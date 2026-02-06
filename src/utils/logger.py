import gzip
import logging
import os
import shutil
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional

from src.config import get_settings


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

# Формат для консоли (кратко)
_CONSOLE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s"
_CONSOLE_DATEFMT = "%H:%M:%S"

# Формат для файлов (подробно, с датой)
_FILE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Ротация: 50 MB, 5 файлов, с gzip-сжатием
_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
_BACKUP_COUNT = 5
_LOG_DIR = Path("/app/logs")


class CompressedRotatingFileHandler(RotatingFileHandler):
    """RotatingFileHandler с gzip-сжатием ротированных файлов."""

    def doRollover(self):
        """Ротация + сжатие старых файлов."""
        if self.stream:
            self.stream.close()
            self.stream = None

        # Сдвигаем существующие .gz файлы
        for i in range(self.backupCount - 1, 0, -1):
            sfn = self.rotation_filename(f"{self.baseFilename}.{i}.gz")
            dfn = self.rotation_filename(f"{self.baseFilename}.{i + 1}.gz")
            if os.path.exists(sfn):
                if os.path.exists(dfn):
                    os.remove(dfn)
                os.rename(sfn, dfn)

        # Сжимаем текущий лог в .1.gz
        dfn = self.rotation_filename(f"{self.baseFilename}.1.gz")
        if os.path.exists(dfn):
            os.remove(dfn)
        if os.path.exists(self.baseFilename):
            with open(self.baseFilename, "rb") as f_in:
                with gzip.open(dfn, "wb") as f_out:
                    shutil.copyfileobj(f_in, f_out)
            # Очищаем текущий файл
            with open(self.baseFilename, "w"):
                pass

        if not self.delay:
            self.stream = self._open()


class CleanFormatter(logging.Formatter):
    """Компактный форматтер с короткими именами логгеров."""

    def format(self, record: logging.LogRecord) -> str:
        # Сохраняем оригинальное имя и подставляем короткое
        original_name = record.name
        name = record.name
        for prefix, short in _LOGGER_NAME_MAP.items():
            if name == prefix or name.startswith(prefix + "."):
                record.name = short
                break
        else:
            if "." in name:
                record.name = name.rsplit(".", 1)[-1]

        result = super().format(record)
        record.name = original_name  # восстанавливаем для других хэндлеров
        return result


def _ensure_log_dir() -> Path:
    """Создаёт директорию для логов если не существует."""
    log_dir = _LOG_DIR
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def setup_logger() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)  # root ловит всё, фильтрация на хэндлерах

    # === Console handler: только WARNING+ (для docker compose logs) ===
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(CleanFormatter(fmt=_CONSOLE_FMT, datefmt=_CONSOLE_DATEFMT))
    root.addHandler(console)

    # === File handlers: подробные логи с ротацией ===
    try:
        log_dir = _ensure_log_dir()

        # INFO+ файл
        info_handler = CompressedRotatingFileHandler(
            filename=str(log_dir / "adminbot_INFO.log"),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(CleanFormatter(fmt=_FILE_FMT, datefmt=_FILE_DATEFMT))
        root.addHandler(info_handler)

        # WARNING+ файл
        warn_handler = CompressedRotatingFileHandler(
            filename=str(log_dir / "adminbot_WARNING.log"),
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
        warn_handler.setLevel(logging.WARNING)
        warn_handler.setFormatter(CleanFormatter(fmt=_FILE_FMT, datefmt=_FILE_DATEFMT))
        root.addHandler(warn_handler)

    except OSError as exc:
        # Если не удалось создать файлы (read-only FS и т.п.) — работаем только с консолью
        console.setLevel(level)  # fallback: показываем всё в консоли
        root.warning("⚠️ Cannot create log files (%s), logging to console only", exc)

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
