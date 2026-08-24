"""Отметки под карточками уведомлений.

Карточки уходят rich-сообщением (Bot API 10.1), которого aiogram 3.12 ещё
не знает: ни ``text``, ни ``caption`` у такого сообщения нет, а ``html_text``
собран из них же и отдаёт пустую строку. Правка пустым текстом стирала
карточку целиком, оставляя от неё одну отметку — поэтому когда текста не
видно, отметка уходит отдельным ответом, а на самой карточке меняются
только кнопки.

Общий модуль, потому что дописывают отметки все, кто раздаёт кнопки под
уведомлениями: действия по нарушениям и ответы на инциденты плагинов.
"""
import logging
from typing import Optional

from aiogram.types import CallbackQuery, InlineKeyboardMarkup

logger = logging.getLogger(__name__)


async def append_card_note(
    callback: CallbackQuery,
    note: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Дописать отметку под карточкой; ``keyboard`` заменяет её кнопки.

    Пустой ``keyboard`` снимает кнопки: следующий читатель должен видеть,
    что ответ уже дан, и не жать по второму разу.
    """
    message = callback.message
    if message is None:
        return

    try:
        old_text = message.html_text
    except (AttributeError, TypeError):
        old_text = ""

    if old_text:
        try:
            await message.edit_text(old_text + note, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.warning("Failed to append card note: %s", e)
        return

    try:
        await message.edit_reply_markup(reply_markup=keyboard)
    except Exception as e:
        logger.debug("Cannot update card keyboard: %s", e)
    try:
        await message.reply(note.strip(), parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to send card note: %s", e)
