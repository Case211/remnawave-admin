import logging
from typing import Any, Optional
from src.config import get_settings


def setup_logger() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Align aiogram logger level with our settings.
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
    """
    Логирует действие пользователя в структурированном формате.
    
    Args:
        action: Описание действия (например, "button_clicked", "command_executed", "input_received")
        user_id: ID пользователя Telegram
        username: Имя пользователя (если доступно)
        details: Дополнительные детали действия
        level: Уровень логирования (по умолчанию INFO)
    """
    parts = [f"👤 USER ACTION: {action}"]
    
    if user_id:
        parts.append(f"user_id={user_id}")
    if username:
        parts.append(f"username={username}")
    if details:
        detail_str = ", ".join(f"{k}={v}" for k, v in details.items())
        parts.append(f"details=[{detail_str}]")
    
    message = " | ".join(parts)
    logger.log(level, message)


def log_button_click(callback_data: str, user_id: Optional[int] = None, username: Optional[str] = None) -> None:
    """Логирует нажатие на кнопку."""
    log_user_action(
        "button_clicked",
        user_id=user_id,
        username=username,
        details={"callback_data": callback_data},
    )


def log_command(command: str, user_id: Optional[int] = None, username: Optional[str] = None, args: Optional[str] = None) -> None:
    """Логирует выполнение команды."""
    details = {"command": command}
    if args:
        details["args"] = args
    log_user_action(
        "command_executed",
        user_id=user_id,
        username=username,
        details=details,
    )


def log_user_input(field: str, user_id: Optional[int] = None, username: Optional[str] = None, preview: Optional[str] = None) -> None:
    """Логирует ввод данных пользователем."""
    details = {"field": field}
    if preview:
        # Показываем только первые 50 символов для безопасности
        details["preview"] = preview[:50] + "..." if len(preview) > 50 else preview
    log_user_action(
        "input_received",
        user_id=user_id,
        username=username,
        details=details,
    )


def log_api_call(method: str, endpoint: str, status_code: Optional[int] = None, duration_ms: Optional[float] = None) -> None:
    """Логирует вызов API."""
    parts = [f"🌐 API CALL: {method} {endpoint}"]
    if status_code:
        parts.append(f"status={status_code}")
    if duration_ms:
        parts.append(f"duration={duration_ms:.2f}ms")
    logger.info(" | ".join(parts))


def log_api_error(method: str, endpoint: str, error: Exception, status_code: Optional[int] = None) -> None:
    """Логирует ошибку API."""
    parts = [f"❌ API ERROR: {method} {endpoint}"]
    if status_code:
        parts.append(f"status={status_code}")
    parts.append(f"error={type(error).__name__}: {str(error)}")
    logger.error(" | ".join(parts))
