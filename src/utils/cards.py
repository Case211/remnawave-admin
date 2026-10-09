"""Отметки под карточками уведомлений.

Карточки уходят rich-сообщением (Bot API 10.1), которого aiogram 3.12 ещё
не знает: ни ``text``, ни ``caption`` у такого сообщения нет, а ``html_text``
собран из них же и отдаёт пустую строку. Правка пустым текстом стирала
карточку целиком, оставляя от неё одну отметку — поэтому когда текста не
видно, отметка уходит отдельным ответом, а на самой карточке меняются
только кнопки.

Если в нажатии пришли сами rich-блоки (aiogram их не разбирает, но хранит
в model_extra), карточка переписывается на месте: встроенные кнопки уходят,
отметка встаёт перед подвалом, новые кнопки встраиваются вместо старых.

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

    if await _rewrite_rich_card(message, note, keyboard):
        return

    try:
        await message.edit_reply_markup(reply_markup=keyboard)
    except Exception as e:
        logger.debug("Cannot update card keyboard: %s", e)
    try:
        await message.reply(note.strip(), parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to send card note: %s", e)


async def _rewrite_rich_card(message, note: str, keyboard: Optional[InlineKeyboardMarkup]) -> bool:
    """Дописать отметку в саму rich-карточку и заменить её встроенные кнопки.

    False — блоков в сообщении нет или Telegram правку не принял: тогда
    отметка уходит по-старому, отдельным ответом.
    """
    extra = getattr(message, "model_extra", None)
    rich_message = extra.get("rich_message") if isinstance(extra, dict) else None
    blocks = rich_message.get("blocks") if isinstance(rich_message, dict) else None
    if not isinstance(blocks, list) or not blocks:
        return False

    from shared import tg_rich

    kept = [blk for blk in blocks if blk.get("type") != "buttons"]
    added = [{"type": "paragraph", "text": tg_rich.inline(note.strip())}]
    if keyboard is not None:
        added += [{"type": "buttons", "buttons": [btn.model_dump(exclude_none=True) for btn in row]}
                  for row in keyboard.inline_keyboard]
    # подвал остаётся последним: отметка и новые кнопки встают перед ним
    footer_at = next((n for n, blk in enumerate(kept) if blk.get("type") == "footer"), len(kept))
    kept[footer_at:footer_at] = added
    return await tg_rich.edit_rich(message.bot.token, message.chat.id, message.message_id, kept)
