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


class TestRichCardWithBlocks:
    """Блоки пришли в самом нажатии — карточка переписывается на месте."""

    BLOCKS = [
        {"type": "heading", "text": "Нарушение", "size": 3},
        {"type": "paragraph", "text": "alex · 87"},
        {"type": "buttons", "buttons": [{"text": "Заблокировать", "callback_data": "vact:block:u"}]},
        {"type": "footer", "text": "Remnawave Admin"},
    ]

    def _rich_callback(self):
        cb = _callback(html_text="")
        cb.message.model_extra = {"rich_message": {"blocks": [dict(b) for b in self.BLOCKS]}}
        cb.message.bot.token = "T"
        cb.message.chat.id = -100
        cb.message.message_id = 7
        return cb

    @pytest.mark.asyncio
    async def test_note_and_new_buttons_replace_old_ones_before_footer(self, monkeypatch):
        from shared import tg_rich
        edit = AsyncMock(return_value=True)
        monkeypatch.setattr(tg_rich, "edit_rich", edit)
        button = MagicMock()
        button.model_dump.return_value = {"text": "Снять", "callback_data": "vact:unthr:u", "style": "success"}
        keyboard = MagicMock()
        keyboard.inline_keyboard = [[button]]

        cb = self._rich_callback()
        await append_card_note(cb, chr(10) * 2 + "✅ <b>Заблокирован</b>", keyboard=keyboard)

        token, chat_id, message_id, blocks = edit.await_args.args
        assert (token, chat_id, message_id) == ("T", -100, 7)
        assert [b["type"] for b in blocks] == ["heading", "paragraph", "paragraph", "buttons", "footer"]
        assert blocks[2]["text"] == ["✅ ", {"type": "bold", "text": "Заблокирован"}]
        assert blocks[3]["buttons"] == [{"text": "Снять", "callback_data": "vact:unthr:u", "style": "success"}]
        cb.message.reply.assert_not_awaited()
        cb.message.edit_reply_markup.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_keyboard_removes_buttons(self, monkeypatch):
        from shared import tg_rich
        edit = AsyncMock(return_value=True)
        monkeypatch.setattr(tg_rich, "edit_rich", edit)
        await append_card_note(self._rich_callback(), "отметка")
        assert "buttons" not in [b["type"] for b in edit.await_args.args[3]]

    @pytest.mark.asyncio
    async def test_rejected_rewrite_falls_back_to_reply(self, monkeypatch):
        from shared import tg_rich
        monkeypatch.setattr(tg_rich, "edit_rich", AsyncMock(return_value=False))
        cb = self._rich_callback()
        await append_card_note(cb, "отметка")
        cb.message.reply.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_message_is_ignored():
    cb = MagicMock()
    cb.message = None
    await append_card_note(cb, "отметка")
