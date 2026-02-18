from aiogram.types.error_event import ErrorEvent
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _get_error_message
from shared.api_client import (
    ApiClientError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    UnauthorizedError,
    ValidationError,
)
from shared.logger import logger


def _get_error_code(exc: Exception) -> str:
    """Извлекает код ошибки из исключения."""
    if isinstance(exc, ApiClientError):
        return getattr(exc, "code", "ERR_UNK_001")
    
    # Для других типов ошибок генерируем код на основе типа
    exc_type = type(exc).__name__
    return f"ERR_{exc_type.upper()[:6]}_001"


async def errors_handler(event: ErrorEvent) -> None:
    """Глобальный обработчик ошибок с информативными сообщениями."""
    update = event.update
    exc = event.exception

    user_id = None
    payload = None
    error_code = _get_error_code(exc)
    
    # Определяем сообщение об ошибке на основе типа исключения
    if isinstance(exc, (ApiClientError, NetworkError, TimeoutError, 
                        RateLimitError, ServerError, ValidationError,
                        NotFoundError, UnauthorizedError)):
        # Используем улучшенную функцию для API ошибок
        error_message = _get_error_message(exc, include_code=True, include_hint=True)
    else:
        # Для неизвестных ошибок показываем общее сообщение с кодом
        # Используем try-except для случая, когда i18n контекст не установлен
        try:
            error_message = _("errors.generic") + f"\n🔢 Код: `{error_code}`"
        except LookupError:
            # Fallback если i18n контекст не установлен
            error_message = f"⚠️ Что-то пошло не так. Повтори чуть позже.\n🔢 Код: `{error_code}`"
    
    try:
        if update.message:
            user_id = update.message.from_user.id if update.message.from_user else None
            payload = update.message.text
            await update.message.answer(error_message, parse_mode="Markdown")
        elif update.callback_query:
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
            payload = update.callback_query.data
            # Для callback query показываем короткое сообщение (лимит 200 символов)
            short_message = _get_error_message(exc, include_code=True, include_hint=False)
            # Обрезаем до 200 символов, если нужно
            if len(short_message) > 200:
                short_message = short_message[:197] + "..."
            await update.callback_query.answer(short_message, show_alert=True)
    except Exception as reply_exc:
        # If replying fails, log but don't raise
        logger.warning(
            "Failed to send error message to user",
            extra={"user_id": user_id, "error": str(reply_exc)},
        )

    safe_update = {}
    try:
        safe_update = update.model_dump(mode="json", exclude_none=True)
    except Exception:
        safe_update = {"repr": repr(update)}

    # Логируем с кодом ошибки для облегчения отладки
    logger.exception(
        "Unhandled error while processing update",
        extra={
            "user_id": user_id,
            "payload": payload,
            "update": safe_update,
            "error_code": error_code,
            "error_type": type(exc).__name__,
        },
        exc_info=exc,
    )
