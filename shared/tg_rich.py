"""Rich-уведомления Telegram (Bot API 10.1) без зависимости от aiogram.

Bot API 10.1 (июнь 2026) добавил sendRichMessage — «документные» сообщения
с настоящими заголовками, списками и сворачиваемыми секциями. aiogram у бота
старый (3.12), поэтому строим блоки чистыми dict'ами по схеме Bot API и шлём
raw-запросом; при любом отказе откатываемся на обычный sendMessage с HTML —
прод-уведомления не должны пропадать из-за нового формата.

Конвертер html_to_blocks() принимает наш же генерируемый телеграм-HTML
(карточки уведомлений) и раскладывает его в блоки:
- первая строка → заголовок (heading);
- строки с отступом «   » → элементы списка;
- <blockquote expandable> → сворачиваемая секция (details);
- пустая строка — граница параграфа; инлайн-теги → rich-инлайны.
"""
from __future__ import annotations

import re
from html import unescape
from html.parser import HTMLParser
from typing import Any, Optional

import httpx

from shared import tg_http
from shared.logger import logger

# Тумблер: возможность мгновенно выключить rich в проде без отката
RICH_SETTING_KEY = "notifications_rich_enabled"

_INLINE_TAG_MAP = {
    "b": "bold", "strong": "bold",
    "i": "italic", "em": "italic",
    "u": "underline", "ins": "underline",
    "s": "strikethrough", "strike": "strikethrough", "del": "strikethrough",
    "code": "code",
    "tg-spoiler": "spoiler", "span": "spoiler",
}


class _InlineParser(HTMLParser):
    """Наш ограниченный телеграм-HTML → rich-инлайны (str | dict)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root: list = []
        self._stack: list[list] = [self.root]
        self._tags: list[dict] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag == "a":
            node = {"type": "url", "url": dict(attrs).get("href", ""), "text": []}
        elif tag in _INLINE_TAG_MAP:
            node = {"type": _INLINE_TAG_MAP[tag], "text": []}
        else:
            return  # незнакомый тег — содержимое пойдёт наружу как текст
        self._stack[-1].append(node)
        self._stack.append(node["text"])
        self._tags.append(node)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if self._tags and (_INLINE_TAG_MAP.get(tag) == self._tags[-1]["type"]
                           or (tag == "a" and self._tags[-1]["type"] == "url")):
            self._tags.pop()
            self._stack.pop()

    def handle_data(self, data: str) -> None:
        if data:
            self._stack[-1].append(data)


def _simplify(parts: list) -> Any:
    """Список инлайнов → компактный RichText (склейка строк, str для простого)."""
    out: list = []
    for p in parts:
        if isinstance(p, dict):
            p = {**p, "text": _simplify(p["text"])}
            out.append(p)
        elif out and isinstance(out[-1], str) and isinstance(p, str):
            out[-1] += p
        else:
            out.append(p)
    if not out:
        return ""
    if len(out) == 1 and isinstance(out[0], str):
        return out[0]
    return out


def inline(html_text: str) -> Any:
    """Инлайн-HTML → RichText (str или список str/dict)."""
    p = _InlineParser()
    p.feed(html_text or "")
    return _simplify(p.root)


def _paragraph(html_line: str) -> dict:
    return {"type": "paragraph", "text": inline(html_line)}


_EXPANDABLE_RE = re.compile(
    r"<blockquote expandable>(.*?)</blockquote>", re.DOTALL | re.IGNORECASE)
_QUOTE_RE = re.compile(r"<blockquote>(.*?)</blockquote>", re.DOTALL | re.IGNORECASE)
_PRE_RE = re.compile(r"<pre>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_INDENT_RE = re.compile(r"^\s{2,}")
_PLACEHOLDER = "\x00BLK{}\x00"


def html_to_blocks(html_text: str, *, title_first: bool = True) -> list[dict]:
    """Наш телеграм-HTML → список rich-блоков Bot API 10.1."""
    text = html_text or ""
    stash: list[dict] = []

    def _stash_block(block: dict) -> str:
        stash.append(block)
        return _PLACEHOLDER.format(len(stash) - 1)

    # Блочные конструкции прячем в плейсхолдеры до построчного разбора
    def _mk_details(m: re.Match) -> str:
        inner = m.group(1).strip()
        first, _, rest = inner.partition("\n")
        summary = inline(first) or "Подробнее"
        inner_blocks = ([_paragraph(ln) for ln in rest.splitlines() if ln.strip()]
                        or [_paragraph("")])
        return _stash_block({"type": "details", "summary": summary,
                             "blocks": inner_blocks, "is_open": False})

    text = _EXPANDABLE_RE.sub(_mk_details, text)
    text = _PRE_RE.sub(lambda m: _stash_block(
        {"type": "pre", "text": unescape(m.group(1))}), text)
    text = _QUOTE_RE.sub(lambda m: _stash_block(
        {"type": "blockquote",
         "blocks": [_paragraph(ln) for ln in m.group(1).splitlines() if ln.strip()]
         or [_paragraph("")]}), text)

    blocks: list[dict] = []
    list_items: list[dict] = []
    title_done = not title_first

    def _flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append({"type": "list", "items": list_items})
            list_items = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            _flush_list()
            continue

        ph = re.fullmatch(r"\x00BLK(\d+)\x00", stripped)
        if ph:
            _flush_list()
            blocks.append(stash[int(ph.group(1))])
            continue

        if not title_done:
            blocks.append({"type": "heading", "text": inline(stripped), "size": 2})
            title_done = True
            continue

        if _INDENT_RE.match(line):
            # строки с отступом — поля карточки, собираем в список
            list_items.append({"blocks": [_paragraph(stripped)]})
            continue

        _flush_list()
        blocks.append(_paragraph(stripped))

    _flush_list()
    return blocks


def _rich_enabled() -> bool:
    try:
        from shared.config_service import config_service
        return bool(config_service.get(RICH_SETTING_KEY, True))
    except Exception:
        return True


async def send_rich_or_html(
    token: str,
    chat_id: int | str,
    html_text: str,
    *,
    blocks: Optional[list[dict]] = None,
    message_thread_id: Optional[int] = None,
    reply_markup: Optional[dict] = None,
    disable_web_page_preview: bool = True,
) -> bool:
    """Отправить уведомление rich-сообщением с фолбэком на обычный HTML.

    blocks не передан — строится из html_text конвертером. Любая ошибка
    rich-пути (метод не принят, блоки не понравились) тихо уводит в старый
    sendMessage: уведомление доходит всегда.
    """
    api = f"{tg_http.api_root()}/bot{token}"
    async with httpx.AsyncClient(**tg_http.client_kwargs(15)) as client:
        if _rich_enabled():
            try:
                rich_blocks = blocks if blocks is not None else html_to_blocks(html_text)
                payload: dict[str, Any] = {
                    "chat_id": chat_id,
                    "rich_message": {"blocks": rich_blocks},
                }
                if message_thread_id:
                    payload["message_thread_id"] = int(message_thread_id)
                if reply_markup:
                    payload["reply_markup"] = reply_markup
                resp = await client.post(f"{api}/sendRichMessage", json=payload)
                if resp.status_code == 200:
                    logger.debug("sendRichMessage ok: chat_id=%s blocks=%d",
                                 chat_id, len(rich_blocks))
                    return True
                logger.warning("sendRichMessage rejected (%s): %s — fallback to HTML",
                               resp.status_code, resp.text[:200])
            except Exception as e:
                logger.warning("sendRichMessage error: %s — fallback to HTML", e)

        payload = {
            "chat_id": chat_id,
            "text": html_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": disable_web_page_preview,
        }
        if message_thread_id:
            payload["message_thread_id"] = int(message_thread_id)
        if reply_markup:
            payload["reply_markup"] = reply_markup
        resp = await client.post(f"{api}/sendMessage", json=payload)
        return resp.status_code == 200
