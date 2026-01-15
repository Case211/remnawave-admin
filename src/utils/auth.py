from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.i18n import gettext as _

from src.config import get_settings
from src.utils.i18n import get_i18n
from src.utils.logger import log_button_click, log_command, log_user_input, logger


def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором.
    
    Если список администраторов пустой, возвращает False (никто не является администратором).
    Если список не пустой, проверяет наличие user_id в списке.
    """
    settings = get_settings()
    allowed_admins = settings.allowed_admins
    # Если список администраторов пустой, никто не является администратором
    if not allowed_admins:
        return False
    # Проверяем, есть ли пользователь в списке администраторов
    return user_id in allowed_admins


class AdminMiddleware(BaseMiddleware):
    """Middleware для проверки прав администратора.
    
    Блокирует все сообщения и callback-запросы от пользователей, 
    которые не находятся в списке администраторов.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        """Проверяет права администратора перед обработкой события."""
        user_id = None
        
        # Извлекаем user_id из события
        if isinstance(event, (Message, CallbackQuery)):
            user_id = event.from_user.id if event.from_user else None
        
        # Если user_id не найден, пропускаем событие (может быть системное)
        if user_id is None:
            return await handler(event, data)
        
        # Проверяем, является ли пользователь администратором
        if not is_admin(user_id):
            settings = get_settings()
            logger.warning(
                "🚫 Unauthorized access attempt user_id=%s event_type=%s allowed_admins=%s",
                user_id,
                type(event).__name__,
                settings.allowed_admins,
            )
            # Для CallbackQuery отправляем ответ с ошибкой
            if isinstance(event, CallbackQuery):
                try:
                    # Используем локализацию для сообщения об ошибке
                    i18n = get_i18n()
                    with i18n.use_locale(i18n.default_locale):
                        error_text = _("errors.unauthorized")
                    await event.answer(error_text, show_alert=True)
                except Exception:
                    # Если локализация не работает, используем хардкод
                    try:
                        await event.answer("⛔️ Доступ запрещен. Вы не являетесь администратором.", show_alert=True)
                    except Exception:
                        pass  # Игнорируем ошибки при отправке ответа
            # Для Message отправляем сообщение об ошибке
            elif isinstance(event, Message):
                try:
                    # Используем локализацию для сообщения об ошибке
                    i18n = get_i18n()
                    with i18n.use_locale(i18n.default_locale):
                        error_text = _("errors.unauthorized")
                    await event.answer(error_text)
                except Exception:
                    # Если локализация не работает, используем хардкод
                    try:
                        await event.answer("⛔️ Доступ запрещен. Вы не являетесь администратором.")
                    except Exception:
                        pass  # Игнорируем ошибки при отправке ответа
            # Не вызываем handler, чтобы заблокировать обработку
            return
        
        # Логируем действия пользователя
        if isinstance(event, CallbackQuery):
            username = event.from_user.username if event.from_user else None
            log_button_click(
                callback_data=event.data or "unknown",
                user_id=user_id,
                username=username,
            )
        elif isinstance(event, Message):
            username = event.from_user.username if event.from_user else None
            if event.text and event.text.startswith("/"):
                # Это команда
                command_parts = event.text.split(maxsplit=1)
                command = command_parts[0]
                args = command_parts[1] if len(command_parts) > 1 else None
                log_command(
                    command=command,
                    user_id=user_id,
                    username=username,
                    args=args,
                )
            elif event.text:
                # Это текстовый ввод
                log_user_input(
                    field="text_input",
                    user_id=user_id,
                    username=username,
                    preview=event.text,
                )
        
        # Если пользователь администратор, продолжаем обработку
        return await handler(event, data)
