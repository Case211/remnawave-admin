"""Отметки под карточками уведомлений.

Карточки уходят rich-сообщением, которого aiogram не разбирает: у него нет
ни text, ни caption. Правка такого сообщения стирала карточку целиком —
здесь проверяется, что вместо этого отметка уходит отдельным ответом.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.utils.cards import append_card_note


def _callback(html_text="карточка нарушения"):
    cb = MagicMock()
    cb.message = MagicMock()
    if isinstance(html_text, Exception):
        type(cb.message).html_text = property(lambda self: (_ for _ in ()).throw(html_text))
    else:
        cb.message.html_text = html_text
    cb.message.edit_text = AsyncMock()
    cb.message.edit_reply_markup = AsyncMock()
    cb.message.reply = AsyncMock()
    return cb


class TestPlainCard:
    @pytest.mark.asyncio
    async def test_note_is_appended_to_text(self):
        cb = _callback()
        await append_card_note(cb, (chr(10) * 2 + "<i>отметка</i>"))
        cb.message.edit_text.assert_awaited_once()
        assert cb.message.edit_text.await_args.args[0].startswith("карточка нарушения")
        cb.message.reply.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_keyboard_replaces_buttons(self):
        cb = _callback()
        keyboard = MagicMock()
        await append_card_note(cb, "отметка", keyboard=keyboard)
        assert cb.message.edit_text.await_args.kwargs["reply_markup"] is keyboard

    @pytest.mark.asyncio
    async def test_failed_edit_does_not_raise(self):
        cb = _callback()
        cb.message.edit_text = AsyncMock(side_effect=Exception("too old"))
        await append_card_note(cb, "отметка")


class TestRichCard:
    """У rich-сообщения текста не видно: карточку править нельзя."""

    @pytest.mark.asyncio
    async def test_note_goes_as_reply(self):
        cb = _callback(html_text="")
        await append_card_note(cb, (chr(10) * 2 + "<i>отметка</i>"))
        cb.message.edit_text.assert_not_awaited()
        cb.message.reply.assert_awaited_once()
        assert cb.message.reply.await_args.args[0] == "<i>отметка</i>"

    @pytest.mark.asyncio
    async def test_buttons_are_updated_on_the_card(self):
        cb = _callback(html_text="")
        keyboard = MagicMock()
        await append_card_note(cb, "отметка", keyboard=keyboard)
        cb.message.edit_reply_markup.assert_awaited_once_with(reply_markup=keyboard)

    @pytest.mark.asyncio
    async def test_unreadable_message_falls_back_to_reply(self):
        """У недоступного сообщения html_text бросает — это не повод падать."""
        cb = _callback(html_text=TypeError("no text"))
        await append_card_note(cb, "отметка")
        cb.message.reply.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_keyboard_failure_does_not_block_the_note(self):
        cb = _callback(html_text="")
        cb.message.edit_reply_markup = AsyncMock(side_effect=Exception("no buttons"))
        await append_card_note(cb, "отметка")
        cb.message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_message_is_ignored():
    cb = MagicMock()
    cb.message = None
    await append_card_note(cb, "отметка")
