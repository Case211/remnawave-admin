"""Общие утилиты для всех обработчиков."""
import asyncio

from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.state import ADMIN_COMMAND_DELETE_DELAY, LAST_BOT_MESSAGES
from src.utils.auth import is_admin
from src.utils.logger import logger


async def _cleanup_message(message: Message, delay: float = 0.0) -> None:
    """Удаляет сообщение с задержкой."""
    if not isinstance(message, Message):
        return
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await message.delete()
    except Exception as exc:
        logger.warning(
            "🧹 Failed to delete message chat_id=%s message_id=%s err=%s",
            message.chat.id,
            getattr(message, "message_id", None),
            exc,
        )


async def _send_clean_message(
    target: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message:
    """Отправляет или редактирует сообщение, заменяя предыдущее в чате."""
    msg = target.message if isinstance(target, CallbackQuery) else target
    bot = msg.bot
    chat_id = msg.chat.id

    prev_id = LAST_BOT_MESSAGES.get(chat_id)
    if prev_id:
        try:
            edited = await bot.edit_message_text(
                chat_id=chat_id, message_id=prev_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode
            )
            return edited
        except Exception:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=prev_id)
            except Exception:
                pass

    sent = await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    LAST_BOT_MESSAGES[chat_id] = sent.message_id
    return sent


async def _not_admin(message: Message | CallbackQuery) -> bool:
    """Проверяет, является ли пользователь администратором. Удаляет команды автоматически."""
    user_id = message.from_user.id if hasattr(message, "from_user") else None
    if user_id is None or not is_admin(user_id):
        text = _("errors.unauthorized")
        if isinstance(message, CallbackQuery):
            await message.answer(text, show_alert=True)
        else:
            await _send_clean_message(message, text)
        return True
    if isinstance(message, Message):
        is_command = bool(getattr(message, "text", "") and message.text.startswith("/"))
        delay = ADMIN_COMMAND_DELETE_DELAY if is_command else 0.0
        asyncio.create_task(_cleanup_message(message, delay=delay))
    return False


def _get_target_user_id(target: Message | CallbackQuery) -> int | None:
    """Извлекает user_id из Message или CallbackQuery."""
    if isinstance(target, CallbackQuery):
        return target.from_user.id
    return target.from_user.id if getattr(target, "from_user", None) else None


def _clear_user_state(user_id: int | None, keep_search: bool = False, keep_subs: bool = False) -> None:
    """Очищает состояние пользователя."""
    from src.handlers.state import (
        PENDING_INPUT,
        SUBS_PAGE_BY_USER,
        USER_DETAIL_BACK_TARGET,
        USER_SEARCH_CONTEXT,
    )

    if user_id is None:
        return
    PENDING_INPUT.pop(user_id, None)
    if not keep_search:
        USER_SEARCH_CONTEXT.pop(user_id, None)
        USER_DETAIL_BACK_TARGET.pop(user_id, None)
        if not keep_subs:
            SUBS_PAGE_BY_USER.pop(user_id, None)


async def _edit_text_safe(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None, parse_mode: str | None = None
) -> None:
    """Безопасно редактирует текст сообщения, обрабатывая ошибки."""
    from aiogram.exceptions import TelegramBadRequest

    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            # Сообщение не изменилось - это нормально, просто игнорируем
            return
        # Другие ошибки - пробуем отправить новое сообщение
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        # Любая другая ошибка - пробуем отправить новое сообщение
        try:
            await message.delete()
        except Exception:
            pass
        await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

