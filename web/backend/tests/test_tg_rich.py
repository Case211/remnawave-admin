"""Тесты rich-уведомлений (shared/tg_rich): конвертер HTML→блоки и фолбэк."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared import tg_rich
from shared.tg_rich import html_to_blocks, inline, send_rich_or_html


# ── inline: телеграм-HTML → rich-инлайны ─────────────────────


class TestInline:
    def test_plain(self):
        assert inline("просто текст") == "просто текст"

    def test_bold_code(self):
        """<code> в обычном HTML копируется касанием — в rich это кнопка copy_text."""
        parts = inline("👤 <code>vasya</code> — <b>ACTIVE</b>")
        assert parts[0] == "👤 "
        assert parts[1] == {"type": "button", "button": {"text": "vasya", "copy_text": {"text": "vasya"}}}
        assert parts[2] == " — "
        assert parts[3] == {"type": "bold", "text": "ACTIVE"}

    def test_code_that_cannot_be_copied_stays_code(self):
        long = "x" * 300  # copy_text — до 256 символов, обрезок в буфер не кладём
        assert inline(f"<code>{long}</code>") == [{"type": "code", "text": long}]
        assert inline("<code><b>a</b></code>")[0]["type"] == "code"  # с разметкой внутри — не кнопка

    def test_link(self):
        parts = inline('<a href="https://x.io">открыть</a>')
        assert parts[0]["type"] == "url"
        assert parts[0]["url"] == "https://x.io"
        assert parts[0]["text"] == "открыть"

    def test_nested(self):
        parts = inline("<b>жирный <code>код</code></b>")
        assert parts[0]["type"] == "bold"
        inner = parts[0]["text"]
        assert inner[0] == "жирный "
        assert inner[1] == {"type": "button", "button": {"text": "код", "copy_text": {"text": "код"}}}

    def test_entities_unescaped(self):
        assert inline("a &lt; b &amp; c") == "a < b & c"

    def test_spoiler_and_strike(self):
        parts = inline("<tg-spoiler>секрет</tg-spoiler> <s>зачёркнуто</s>")
        assert parts[0] == {"type": "spoiler", "text": "секрет"}
        assert parts[2] == {"type": "strikethrough", "text": "зачёркнуто"}


# ── html_to_blocks ───────────────────────────────────────────


CARD = (
    "🟢 <b>Пользователь создан</b>\n"
    "\n"
    "👤 <code>vasya</code>  <code>ab12cd34</code>\n"
    "\n"
    "📊 Лимиты:\n"
    "   Лимит: <code>100 GB</code>\n"
    "   Истекает: <code>2026-08-01</code>\n"
)


class TestHtmlToBlocks:
    def test_first_line_is_heading(self):
        blocks = html_to_blocks(CARD)
        assert blocks[0]["type"] == "heading"
        assert blocks[0]["size"] == 2
        # инлайны заголовка сохранены (эмодзи + bold)
        assert any(isinstance(p, dict) and p["type"] == "bold"
                   for p in blocks[0]["text"])

    def test_indented_lines_become_list(self):
        blocks = html_to_blocks(CARD)
        lists = [b for b in blocks if b["type"] == "list"]
        assert len(lists) == 1
        assert len(lists[0]["items"]) == 2
        first_item = lists[0]["items"][0]["blocks"][0]
        assert first_item["type"] == "paragraph"

    def test_plain_lines_are_paragraphs(self):
        blocks = html_to_blocks(CARD)
        types = [b["type"] for b in blocks]
        assert types[0] == "heading"
        assert "paragraph" in types

    def test_expandable_becomes_details(self):
        html = ("Заголовок\n\n"
                "<blockquote expandable><b>Подробности</b>\nстрока 1\nстрока 2</blockquote>")
        blocks = html_to_blocks(html)
        details = [b for b in blocks if b["type"] == "details"]
        assert len(details) == 1
        assert details[0]["is_open"] is False
        assert len(details[0]["blocks"]) == 2

    def test_pre_block(self):
        blocks = html_to_blocks("Титул\n\n<pre>a &lt; b</pre>")
        pre = [b for b in blocks if b["type"] == "pre"]
        assert pre and pre[0]["text"] == "a < b"

    def test_no_title_mode(self):
        blocks = html_to_blocks("строка", title_first=False)
        assert blocks[0]["type"] == "paragraph"

    def test_empty(self):
        assert html_to_blocks("") == []


# ── send_rich_or_html: rich с фолбэком ───────────────────────


def _client_mock(rich_status=200, plain_status=200):
    """Фейковый httpx.AsyncClient: считает вызовы по методам API."""
    calls = []

    class _Resp:
        def __init__(self, code):
            self.status_code = code
            self.text = "resp"

    class _Client:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, json=None):
            calls.append((url, json))
            if url.endswith("/sendRichMessage"):
                return _Resp(rich_status)
            return _Resp(plain_status)

    return _Client, calls


class TestSendRichOrHtml:
    @pytest.mark.asyncio
    async def test_rich_success_no_fallback(self):
        client_cls, calls = _client_mock(rich_status=200)
        with patch.object(tg_rich.httpx, "AsyncClient", client_cls), \
             patch.object(tg_rich, "_rich_enabled", lambda: True):
            ok = await send_rich_or_html("TOKEN", 1, "<b>Титул</b>\n\nтело")
        assert ok is True
        assert len(calls) == 1
        assert calls[0][0].endswith("/sendRichMessage")
        assert calls[0][1]["rich_message"]["blocks"][0]["type"] == "heading"

    @pytest.mark.asyncio
    async def test_fallback_on_rich_reject(self):
        client_cls, calls = _client_mock(rich_status=400)
        with patch.object(tg_rich.httpx, "AsyncClient", client_cls), \
             patch.object(tg_rich, "_rich_enabled", lambda: True):
            ok = await send_rich_or_html("TOKEN", 1, "<b>Титул</b>",
                                         message_thread_id=7)
        assert ok is True
        assert calls[0][0].endswith("/sendRichMessage")
        assert calls[1][0].endswith("/sendMessage")
        assert calls[1][1]["parse_mode"] == "HTML"
        assert calls[1][1]["message_thread_id"] == 7

    @pytest.mark.asyncio
    async def test_toggle_off_goes_straight_html(self):
        client_cls, calls = _client_mock()
        with patch.object(tg_rich.httpx, "AsyncClient", client_cls), \
             patch.object(tg_rich, "_rich_enabled", lambda: False):
            ok = await send_rich_or_html("TOKEN", 1, "текст")
        assert ok is True
        assert len(calls) == 1
        assert calls[0][0].endswith("/sendMessage")

    @pytest.mark.asyncio
    async def test_reply_markup_passed_to_both(self):
        markup = {"inline_keyboard": [[{"text": "x", "url": "https://x.io"}]]}
        client_cls, calls = _client_mock(rich_status=500)
        with patch.object(tg_rich.httpx, "AsyncClient", client_cls), \
             patch.object(tg_rich, "_rich_enabled", lambda: True):
            await send_rich_or_html("TOKEN", 1, "т", reply_markup=markup)
        assert calls[0][1]["reply_markup"] == markup
        assert calls[1][1]["reply_markup"] == markup
