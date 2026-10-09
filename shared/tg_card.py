"""Карточки уведомлений Telegram: одна модель — rich-блоки и HTML-фолбэк.

Rich-сообщения (Bot API 10.1–10.3) умеют то, чего нет в обычном телеграм-HTML:
таблицы, сворачиваемые секции, цитаты с автором, чек-листы, подвал. Карточка
описывает уведомление один раз: ``to_blocks()`` отдаёт блоки для
sendRichMessage, ``to_html()`` — тот же смысл обычным HTML на случай, когда
rich выключен тумблером или Telegram его не принял.

Инлайны — дерево ``Span``. Пользовательские строки кладутся в него как есть:
rich-блокам экранирование не нужно, а HTML-рендер экранирует сам — поэтому
ник с ``<`` или ``_`` не ломает ни одну из версий.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape, unescape
from typing import Any, Iterable, Optional, Sequence, Union

from shared import timefmt

# Лимиты Telegram в обычном HTML: текстовое сообщение и подпись к фото
HTML_LIMIT = 4096
CAPTION_LIMIT = 1024

TITLE_SIZE = 3
SECTION_SIZE = 5


@dataclass(frozen=True)
class Span:
    """Инлайн-разметка: kind — тип RichText, attrs — его доп. поля."""

    kind: str
    content: "Inline"
    attrs: tuple = ()


Inline = Union[str, Span, Sequence["Inline"], None]


# ── Инлайны ──────────────────────────────────────────────────────

def b(x: Inline) -> Span:
    return Span("bold", x)


def i(x: Inline) -> Span:
    return Span("italic", x)


def u(x: Inline) -> Span:
    return Span("underline", x)


def s(x: Inline) -> Span:
    return Span("strikethrough", x)


def code(x: Inline) -> Span:
    return Span("code", x)


def mark(x: Inline) -> Span:
    """Маркер: в rich — подсветка, в обычном HTML её нет, там жирный."""
    return Span("marked", x)


def spoiler(x: Inline) -> Span:
    return Span("spoiler", x)


def link(text: Inline, url: str) -> Span:
    return Span("url", text, (("url", url),))


def tg_user(text: Inline, user_id: int | str) -> Span:
    """Ссылка на Telegram-аккаунт по числовому id — открывает профиль."""
    return link(text, f"tg://user?id={user_id}")


def when(moment: Any, fmt: str = "wDT", fallback: Optional[str] = None) -> Optional[Span]:
    """Момент времени, который Telegram покажет в часовом поясе читателя.

    fmt — формат tg-time: «r» — относительно («5 минут назад»), иначе
    w (день недели), d/D (дата), t/T (время). Запасной текст — в зоне
    панели: его видят клиенты, не знающие tg-time.
    """
    dt = timefmt.parse(moment)
    if dt is None:
        return None
    text = fallback or timefmt.fmt(dt, "%d.%m.%Y %H:%M")
    return Span("date_time", text, (("unix_time", int(dt.timestamp())), ("date_time_format", fmt)))


def join(*parts: Inline, sep: str = " · ") -> list:
    """Части через разделитель; пустые пропускаются."""
    out: list = []
    for part in parts:
        if blank(part):
            continue
        if out:
            out.append(sep)
        out.append(part)
    return out


def blank(x: Inline) -> bool:
    if x is None:
        return True
    if isinstance(x, str):
        return not x.strip()
    if isinstance(x, Span):
        return x.kind != "date_time" and blank(x.content)
    return all(blank(p) for p in x)


def rich(x: Inline) -> Any:
    """Инлайн → RichText Bot API: строка, список или объект."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, Span):
        node: dict = {"type": x.kind, "text": rich(x.content)}
        node.update(dict(x.attrs))
        return node
    parts: list = []
    for part in (rich(p) for p in x):
        if part == "":
            continue
        if parts and isinstance(parts[-1], str) and isinstance(part, str):
            parts[-1] += part
        else:
            parts.append(part)
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else parts


_HTML_TAGS = {
    "bold": "b", "italic": "i", "underline": "u", "strikethrough": "s",
    "spoiler": "tg-spoiler", "code": "code", "marked": "b",
}


def html(x: Inline) -> str:
    """Инлайн → обычный телеграм-HTML с экранированием."""
    if x is None:
        return ""
    if isinstance(x, str):
        return escape(x, quote=False)
    if isinstance(x, Span):
        inner = html(x.content)
        attrs = dict(x.attrs)
        if x.kind == "url":
            return f'<a href="{escape(attrs["url"])}">{inner}</a>'
        if x.kind == "date_time":
            return (f'<tg-time unix="{attrs["unix_time"]}" '
                    f'format="{attrs["date_time_format"]}">{inner}</tg-time>')
        tag = _HTML_TAGS.get(x.kind)
        return f"<{tag}>{inner}</{tag}>" if tag else inner
    return "".join(html(p) for p in x)


def plain(x: Inline) -> str:
    """Инлайн → голый текст: для in-app уведомлений и пушей."""
    if x is None:
        return ""
    if isinstance(x, str):
        return x
    if isinstance(x, Span):
        return plain(x.content)
    return "".join(plain(p) for p in x)


def _paragraph(x: Inline) -> dict:
    return {"type": "paragraph", "text": rich(x)}


def _cell(x: Inline, *, header: bool = False, align: str = "left") -> dict:
    cell = {"text": rich(x) if not blank(x) else "—", "align": align, "valign": "top"}
    if header:
        cell["is_header"] = True
    return cell


# ── Блоки ────────────────────────────────────────────────────────
# Каждый блок умеет rich() — словарь Bot API, html() — обычный HTML
# (nested=True — внутри сворачиваемой секции, где цитату не вложить)
# и text() — голый текст.


@dataclass
class _Heading:
    content: Inline
    size: int

    def rich(self) -> dict:
        return {"type": "heading", "text": rich(self.content), "size": self.size}

    def html(self, nested: bool = False) -> str:
        return f"<b>{html(self.content)}</b>"

    def text(self) -> str:
        return plain(self.content)


@dataclass
class _Paragraph:
    content: Inline

    def rich(self) -> dict:
        return _paragraph(self.content)

    def html(self, nested: bool = False) -> str:
        return html(self.content)

    def text(self) -> str:
        return plain(self.content)


@dataclass
class _Fields:
    """Поля «название — значение»: в rich это компактная таблица."""

    rows: list

    def rich(self) -> dict:
        return {
            "type": "table",
            "is_compact": True,
            "cells": [[_cell(k, header=True), _cell(v)] for k, v in self.rows],
        }

    def html(self, nested: bool = False) -> str:
        return "\n".join(f"{html(k)}: {html(v) if not blank(v) else '—'}" for k, v in self.rows)

    def text(self) -> str:
        return "\n".join(f"{plain(k)}: {plain(v) or '—'}" for k, v in self.rows)


@dataclass
class _Table:
    head: Optional[list]
    rows: list
    align: Optional[list]
    caption: Inline
    striped: bool
    bordered: bool

    def _align(self, col: int) -> str:
        return self.align[col] if self.align and col < len(self.align) else "left"

    def rich(self) -> dict:
        cells = []
        if self.head:
            cells.append([_cell(h, header=True, align=self._align(n)) for n, h in enumerate(self.head)])
        for row in self.rows:
            cells.append([_cell(c, align=self._align(n)) for n, c in enumerate(row)])
        block: dict = {"type": "table", "cells": cells, "is_compact": True}
        if self.striped:
            block["is_striped"] = True
        if self.bordered:
            block["is_bordered"] = True
        if not blank(self.caption):
            block["caption"] = rich(self.caption)
        return block

    def html(self, nested: bool = False) -> str:
        # Таблиц в обычном HTML нет: строка таблицы — строка текста
        lines = [f"<b>{html(self.caption)}</b>"] if not blank(self.caption) else []
        if self.head:
            lines.append("<i>" + " · ".join(html(h) for h in self.head) + "</i>")
        lines.extend(" · ".join(html(c) if not blank(c) else "—" for c in row) for row in self.rows)
        return "\n".join(lines)

    def text(self) -> str:
        return "\n".join(" · ".join(plain(c) or "—" for c in row) for row in self.rows)


@dataclass
class _List:
    items: list
    checks: Optional[list]

    def rich(self) -> dict:
        items = []
        for n, item in enumerate(self.items):
            entry: dict = {"blocks": [_paragraph(item)]}
            if self.checks is not None:
                entry["has_checkbox"] = True
                if self.checks[n]:
                    entry["is_checked"] = True
            items.append(entry)
        return {"type": "list", "items": items}

    def _marker(self, n: int) -> str:
        if self.checks is None:
            return "•"
        return "✅" if self.checks[n] else "⬜"

    def html(self, nested: bool = False) -> str:
        return "\n".join(f"{self._marker(n)} {html(item)}" for n, item in enumerate(self.items))

    def text(self) -> str:
        return "\n".join(f"{self._marker(n)} {plain(item)}" for n, item in enumerate(self.items))


@dataclass
class _Quote:
    lines: list
    credit: Inline

    def rich(self) -> dict:
        block: dict = {"type": "blockquote", "blocks": [_paragraph(ln) for ln in self.lines]}
        if not blank(self.credit):
            block["credit"] = rich(self.credit)
        return block

    def html(self, nested: bool = False) -> str:
        body = "\n".join(html(ln) for ln in self.lines)
        if not blank(self.credit):
            body += f"\n— <i>{html(self.credit)}</i>"
        if nested:
            return "\n".join(f"› {ln}" for ln in body.splitlines())
        return f"<blockquote>{body}</blockquote>"

    def text(self) -> str:
        return "\n".join(plain(ln) for ln in self.lines)


@dataclass
class _Code:
    content: str
    language: Optional[str]

    def rich(self) -> dict:
        block: dict = {"type": "pre", "text": self.content}
        if self.language:
            block["language"] = self.language
        return block

    def html(self, nested: bool = False) -> str:
        if nested:
            return "\n".join(f"<code>{escape(ln, quote=False)}</code>" for ln in self.content.splitlines())
        body = escape(self.content, quote=False)
        if self.language:
            return f'<pre><code class="language-{escape(self.language)}">{body}</code></pre>'
        return f"<pre>{body}</pre>"

    def text(self) -> str:
        return self.content


@dataclass
class _Details:
    summary: Inline
    body: "Blocks"
    is_open: bool

    def rich(self) -> dict:
        block: dict = {"type": "details", "summary": rich(self.summary), "blocks": self.body.to_blocks()}
        if self.is_open:
            block["is_open"] = True
        return block

    def html(self, nested: bool = False) -> str:
        inner = self.body.to_html(nested=True)
        if nested:
            return f"<b>{html(self.summary)}</b>\n{inner}"
        return f"<blockquote expandable><b>{html(self.summary)}</b>\n{inner}</blockquote>"

    def text(self) -> str:
        return f"{plain(self.summary)}\n{self.body.to_text()}"


@dataclass
class _Divider:
    def rich(self) -> dict:
        return {"type": "divider"}

    def html(self, nested: bool = False) -> str:
        return ""

    def text(self) -> str:
        return ""


@dataclass
class _Footer:
    content: Inline

    def rich(self) -> dict:
        return {"type": "footer", "text": rich(self.content)}

    def html(self, nested: bool = False) -> str:
        return f"<i>{html(self.content)}</i>"

    def text(self) -> str:
        return plain(self.content)


class _Html:
    """Готовый телеграм-HTML (от плагина): rich-блоки строит конвертер tg_rich."""

    def __init__(self, content: str) -> None:
        self.content = content

    def rich(self) -> list:
        from shared.tg_rich import html_to_blocks
        return html_to_blocks(self.content, title_first=False)

    def html(self, nested: bool = False) -> str:
        return self.content

    def text(self) -> str:
        return unescape(re.sub(r"<[^>]+>", "", self.content)).strip()


MEDIA_KINDS = ("photo", "video", "document")


@dataclass
class _Media:
    """Фото, видео или файл, загружаемые вместе с сообщением (attach://<вид>)."""

    kind: str

    def rich(self) -> dict:
        return {"type": self.kind, self.kind: {"type": self.kind, "media": f"attach://{self.kind}"}}

    def html(self, nested: bool = False) -> str:
        return ""

    def text(self) -> str:
        return ""


BUTTON_STYLES = frozenset({"danger", "success", "primary"})


@dataclass(frozen=True)
class Button:
    """Кнопка карточки: callback или ссылка; style — цвет (danger, success, primary)."""

    text: str
    callback_data: Optional[str] = None
    url: Optional[str] = None
    style: Optional[str] = None

    def to_dict(self) -> dict:
        """Одна форма и для кнопки внутри rich-сообщения, и для inline-клавиатуры."""
        out: dict = {"text": self.text}
        if self.url:
            out["url"] = self.url
        else:
            out["callback_data"] = self.callback_data
        if self.style in BUTTON_STYLES:
            out["style"] = self.style
        return out


@dataclass
class _ButtonRow:
    """Ряд кнопок внутри rich-сообщения; в HTML их нет — там клавиатура."""

    buttons: list

    def rich(self) -> dict:
        return {"type": "buttons", "buttons": [btn.to_dict() for btn in self.buttons]}

    def html(self, nested: bool = False) -> str:
        return ""

    def text(self) -> str:
        return ""


class Blocks:
    """Последовательность блоков; методы возвращают self — их удобно цеплять.

    Пустые части молча пропускаются: карточке не нужны проверки
    «есть ли у юзера email» перед каждой строкой.
    """

    def __init__(self) -> None:
        self._items: list = []

    def __bool__(self) -> bool:
        return bool(self._items)

    def text(self, content: Inline) -> "Blocks":
        if not blank(content):
            self._items.append(_Paragraph(content))
        return self

    def lead(self, *parts: Inline, sep: str = " · ") -> "Blocks":
        """Строка-сводка под заголовком: главное через точку."""
        return self.text(join(*parts, sep=sep))

    def section(self, title: Inline) -> "Blocks":
        if not blank(title):
            self._items.append(_Heading(title, SECTION_SIZE))
        return self

    def fields(self, rows: Iterable[tuple]) -> "Blocks":
        """Пары (название, значение); пары с пустым значением выпадают."""
        kept = [(k, v) for k, v in rows if not blank(v)]
        if kept:
            self._items.append(_Fields(kept))
        return self

    def table(self, rows: Iterable[Sequence[Inline]], *, head: Optional[Sequence[Inline]] = None,
              align: Optional[Sequence[str]] = None, caption: Inline = None,
              striped: bool = True, bordered: bool = False) -> "Blocks":
        rows = [list(r) for r in rows]
        if rows:
            self._items.append(_Table(list(head) if head else None, rows,
                                      list(align) if align else None, caption, striped, bordered))
        return self

    def bullets(self, items: Iterable[Inline]) -> "Blocks":
        kept = [it for it in items if not blank(it)]
        if kept:
            self._items.append(_List(kept, None))
        return self

    def checklist(self, items: Iterable[tuple]) -> "Blocks":
        """Пары (пункт, выполнен ли) — галочки в rich, ✅/⬜ в HTML."""
        kept = [(it, bool(done)) for it, done in items if not blank(it)]
        if kept:
            self._items.append(_List([it for it, _ in kept], [done for _, done in kept]))
        return self

    def quote(self, content: Inline | Sequence[Inline], *, credit: Inline = None) -> "Blocks":
        """Цитата: чужие слова — сообщение тикета, письмо, причина."""
        if isinstance(content, str):
            lines = content.splitlines()
        elif content is None or isinstance(content, Span):
            lines = [content]
        else:
            lines = list(content)
        lines = [ln for ln in lines if not blank(ln)]
        if lines:
            self._items.append(_Quote(lines, credit))
        return self

    def details(self, summary: Inline, body: "Blocks", *, is_open: bool = False) -> "Blocks":
        """Сворачиваемая секция: второстепенное не должно занимать экран."""
        if body:
            self._items.append(_Details(summary, body, is_open))
        return self

    def code(self, content: str, language: Optional[str] = None) -> "Blocks":
        if content and content.strip():
            self._items.append(_Code(content, language))
        return self

    def divider(self) -> "Blocks":
        if self._items:
            self._items.append(_Divider())
        return self

    def html_block(self, content: str) -> "Blocks":
        """Чужой готовый телеграм-HTML — например, тело уведомления плагина."""
        if content and content.strip():
            self._items.append(_Html(content))
        return self

    def media(self, kind: str = "photo") -> "Blocks":
        """Фото, видео или файл, приложенные к отправке (tg_rich: ``media=``).

        Файл кладётся под именем своего вида — attach://photo и т. п., —
        поэтому в карточке одно вложение."""
        self._items.append(_Media(kind if kind in MEDIA_KINDS else "document"))
        return self

    def footer(self, *parts: Inline) -> "Blocks":
        content = join(*parts)
        if content:
            self._items.append(_Footer(content))
        return self

    def buttons(self, *rows: Sequence[Button]) -> "Blocks":
        """Ряды кнопок (до 8 в ряду) — встраиваются в само сообщение."""
        for row in rows:
            kept = [btn for btn in row if btn]
            if kept:
                self._items.append(_ButtonRow(kept[:8]))
        return self

    def keyboard(self) -> Optional[dict]:
        """Те же кнопки inline-клавиатурой — для HTML-фолбэка, где rich-кнопок нет."""
        rows = [[btn.to_dict() for btn in item.buttons] for item in self._items if isinstance(item, _ButtonRow)]
        return {"inline_keyboard": rows} if rows else None

    def to_blocks(self) -> list[dict]:
        out: list[dict] = []
        for item in self._items:
            block = item.rich()
            out.extend(block) if isinstance(block, list) else out.append(block)
        return out

    def to_html(self, *, nested: bool = False) -> str:
        return "\n\n".join(h for h in (item.html(nested) for item in self._items) if h)

    def to_text(self) -> str:
        return "\n\n".join(t for t in (item.text() for item in self._items) if t)


def section(title: Inline = None) -> Blocks:
    """Тело сворачиваемой секции; заголовок — опционально."""
    return Blocks().section(title)


class Card(Blocks):
    """Уведомление: заголовок с эмодзи и блоки под ним."""

    def __init__(self, title: Inline, *, emoji: str = "") -> None:
        super().__init__()
        self.title = title
        self.emoji = emoji

    def heading(self) -> list:
        return [f"{self.emoji} ", self.title] if self.emoji else [self.title]

    def to_blocks(self) -> list[dict]:
        return [_Heading(self.heading(), TITLE_SIZE).rich(), *super().to_blocks()]

    def to_html(self, *, nested: bool = False, limit: int = HTML_LIMIT) -> str:
        """Обычный HTML; не влезает в лимит — хвост отбрасывается целыми блоками."""
        head = f"<b>{html(self.heading())}</b>"
        parts = [head, *(h for h in (item.html(nested) for item in self._items) if h)]
        text = "\n\n".join(parts)
        while len(text) > limit and len(parts) > 1:
            parts.pop()
            text = "\n\n".join(parts) + "\n\n…"
        return text if len(text) <= limit else text[: limit - 1] + "…"

    def stamp(self, moment: Any = None) -> "Card":
        """Подвал: подпись админки и время события в поясе читателя."""
        from shared.i18n import tr
        return self.footer(tr("notify.card.brand"), when(moment or datetime.now(timezone.utc)))

    def title_text(self) -> str:
        return plain(self.title)

    def body_text(self) -> str:
        """Голый текст без заголовка — тело in-app уведомления и пуша."""
        return super().to_text()
