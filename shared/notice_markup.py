"""Разметка текстов предупреждений: Telegram-HTML, письмо и простой текст.

Текст шаблона уходит в Telegram с ``parse_mode=HTML``, а Telegram понимает
только свой урезанный набор тегов и отвергает сообщение целиком на любой
лишней мелочи: незнакомом теге, незакрытом, голом «<» или «&». Поэтому текст
проверяем при сохранении шаблона, а не узнаём о проблеме от клиента, которому
ничего не пришло. Правила — core.telegram.org/bots/api#html-style.

Из того же текста собираются письмо (если своего HTML у шаблона нет) и простой
текст — для кабинета клиента и текстовой части письма.

Та же логика есть во фронте (``src/lib/telegramHtml.ts``): редактор подсвечивает
ошибки на лету, а предпросмотр письма должен совпадать с тем, что уйдёт.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Iterator, Optional

TELEGRAM_TAGS = frozenset({
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "a", "code", "pre", "blockquote", "tg-spoiler", "span", "tg-emoji",
})
_NAMED_ENTITIES = frozenset({"lt", "gt", "amp", "quot"})
# Переносы в Telegram — обычные переводы строк; эти теги путают чаще прочих
_LINE_BREAK_TAGS = frozenset({"br", "p", "div"})

_TAG_RE = re.compile(
    r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)"
    r"((?:\s+[a-zA-Z][a-zA-Z0-9-]*(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?)*)"
    r"\s*(/?)>"
)
_ATTR_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9-]*)(?:\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'>]+))?")
_ENTITY_RE = re.compile(r"&(#\d+|#[xX][0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]*);")

_RAW_ESCAPES = {"raw_lt": "&lt;", "raw_gt": "&gt;", "raw_amp": "&amp;"}

EMAIL_STYLE = "font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;font-size:15px;line-height:1.55;color:#1f2328"
_EMAIL_QUOTE_STYLE = "margin:0;padding-left:12px;border-left:3px solid #d0d7de;color:#57606a"


@dataclass
class MarkupIssue:
    """Ошибка разметки: код для перевода, позиция в тексте и подробности."""

    code: str
    start: int
    end: int
    params: dict = field(default_factory=dict)


@dataclass
class _Token:
    kind: str  # text | entity | raw | tag
    start: int
    end: int
    code: str = ""  # для raw: raw_lt | raw_gt | raw_amp | unknown_entity
    name: str = ""  # для tag
    closing: bool = False
    self_closing: bool = False
    attrs: str = ""


def _scan(text: str) -> Iterator[_Token]:
    """Разбор на куски текста, сущности, теги и одиночные спецсимволы."""
    i, n, text_start = 0, len(text), 0
    while i < n:
        ch = text[i]
        if ch not in "<&>":
            i += 1
            continue
        if i > text_start:
            yield _Token("text", text_start, i)
        if ch == "<":
            m = _TAG_RE.match(text, i)
            if m:
                yield _Token(
                    "tag", i, m.end(), name=m.group(2).lower(), closing=m.group(1) == "/",
                    self_closing=m.group(4) == "/", attrs=m.group(3),
                )
                i = m.end()
            else:
                yield _Token("raw", i, i + 1, code="raw_lt")
                i += 1
        elif ch == "&":
            m = _ENTITY_RE.match(text, i)
            if m and (m.group(1).startswith("#") or m.group(1) in _NAMED_ENTITIES):
                yield _Token("entity", i, m.end())
                i = m.end()
            elif m:
                yield _Token("raw", i, m.end(), code="unknown_entity")
                i = m.end()
            else:
                yield _Token("raw", i, i + 1, code="raw_amp")
                i += 1
        else:
            yield _Token("raw", i, i + 1, code="raw_gt")
            i += 1
        text_start = i
    if text_start < n:
        yield _Token("text", text_start, n)


def _attrs(raw: str) -> dict[str, Optional[str]]:
    result: dict[str, Optional[str]] = {}
    for m in _ATTR_RE.finditer(raw or ""):
        value = m.group(2)
        if value is not None and value[:1] in "\"'":
            value = value[1:-1]
        result[m.group(1).lower()] = value
    return result


def _open_tag_issues(tok: _Token, stack: list[_Token]) -> list[MarkupIssue]:
    """Что не так с открывающим тегом: атрибуты и вложенность."""
    issues: list[MarkupIssue] = []

    def issue(code: str, **params) -> None:
        issues.append(MarkupIssue(code, tok.start, tok.end, params))

    name = tok.name
    parent = stack[-1].name if stack else None
    if parent == "code" or (parent == "pre" and name != "code"):
        issue("inside_code", tag=name, parent=parent)
    if name == "a" and any(t.name == "a" for t in stack):
        issue("nested_link")
    if name == "blockquote" and any(t.name == "blockquote" for t in stack):
        issue("nested_quote")

    attrs = _attrs(tok.attrs)
    allowed: dict[str, set] = {
        "a": {"href"}, "span": {"class"}, "tg-emoji": {"emoji-id"},
        "code": {"class"} if parent == "pre" else set(), "blockquote": {"expandable"},
    }
    for attr in attrs:
        if attr not in allowed.get(name, set()):
            issue("bad_attr", tag=name, attr=attr)

    if name == "a" and not (attrs.get("href") or "").strip():
        issue("missing_attr", tag="a", attr="href")
    elif name == "span" and attrs.get("class") != "tg-spoiler":
        issue("missing_attr", tag="span", attr='class="tg-spoiler"')
    elif name == "tg-emoji" and not (attrs.get("emoji-id") or "").isdigit():
        issue("missing_attr", tag="tg-emoji", attr="emoji-id")
    elif name == "code" and "class" in attrs and not (attrs.get("class") or "").startswith("language-"):
        issue("bad_attr", tag="code", attr="class")
    return issues


def telegram_markup_issues(text: str) -> list[MarkupIssue]:
    """Всё, из-за чего Telegram не примет текст с ``parse_mode=HTML``."""
    issues: list[MarkupIssue] = []
    stack: list[_Token] = []
    for tok in _scan(text or ""):
        if tok.kind == "raw":
            params = {"entity": text[tok.start:tok.end]} if tok.code == "unknown_entity" else {}
            issues.append(MarkupIssue(tok.code, tok.start, tok.end, params))
            continue
        if tok.kind != "tag":
            continue
        if tok.name not in TELEGRAM_TAGS:
            code = "line_break" if tok.name in _LINE_BREAK_TAGS else "unknown_tag"
            issues.append(MarkupIssue(code, tok.start, tok.end, {"tag": tok.name}))
            continue
        if tok.closing:
            if stack and stack[-1].name == tok.name:
                stack.pop()
            elif any(t.name == tok.name for t in stack):
                # Закрыли внешний тег раньше внутреннего — снимаем незакрытые
                issues.append(MarkupIssue("mismatched", tok.start, tok.end, {"tag": tok.name, "expected": stack[-1].name}))
                while stack[-1].name != tok.name:
                    stack.pop()
                stack.pop()
            else:
                issues.append(MarkupIssue("unexpected_close", tok.start, tok.end, {"tag": tok.name}))
            continue
        if tok.self_closing:
            issues.append(MarkupIssue("self_closing", tok.start, tok.end, {"tag": tok.name}))
            continue
        issues.extend(_open_tag_issues(tok, stack))
        stack.append(tok)
    issues.extend(MarkupIssue("unclosed", t.start, t.end, {"tag": t.name}) for t in stack)
    issues.sort(key=lambda issue: issue.start)
    return issues


def describe_issue(text: str, issue: MarkupIssue) -> str:
    """Короткое описание для логов и ответа API: код, строка и столбец."""
    line = text.count("\n", 0, issue.start) + 1
    column = issue.start - (text.rfind("\n", 0, issue.start) + 1) + 1
    details = ", ".join(f"{key}={value}" for key, value in issue.params.items())
    return f"{issue.code} at {line}:{column}" + (f" ({details})" if details else "")


def _email_tag(tok: _Token, raw: str) -> str:
    """Тег Telegram → его HTML для письма; обычные теги остаются как есть."""
    if tok.name == "tg-emoji":
        return ""  # вместо кастомного эмодзи — запасной, он внутри тега
    if tok.name in ("tg-spoiler", "span"):
        return "</span>" if tok.closing else "<span>"
    if tok.name == "blockquote":
        return "</blockquote>" if tok.closing else f'<blockquote style="{_EMAIL_QUOTE_STYLE}">'
    return raw


def telegram_to_email_html(text: str) -> str:
    """Письмо из текста Telegram: переводы строк → <br>, свои теги Telegram → HTML."""
    parts: list[str] = []
    in_pre = 0
    for tok in _scan(text or ""):
        raw = text[tok.start:tok.end]
        if tok.kind == "text":
            parts.append(raw if in_pre else raw.replace("\n", "<br>\n"))
        elif tok.kind == "raw":
            parts.append(_RAW_ESCAPES.get(tok.code, raw))
        elif tok.kind == "tag":
            if tok.name == "pre":
                in_pre = max(in_pre + (-1 if tok.closing else 1), 0)
            parts.append(_email_tag(tok, raw))
        else:
            parts.append(raw)
    return f'<div style="{EMAIL_STYLE}">{"".join(parts)}</div>'


def telegram_to_text(text: Optional[str]) -> str:
    """Простой текст без тегов: для кабинета и текстовой части письма.

    Ссылка превращается в «текст (адрес)», чтобы адрес не потерялся.
    """
    if not text:
        return ""
    parts: list[str] = []
    links: list[tuple[str, int]] = []
    for tok in _scan(text):
        raw = text[tok.start:tok.end]
        if tok.kind == "text":
            parts.append(raw)
        elif tok.kind in ("entity", "raw"):
            parts.append(html.unescape(raw))
        elif tok.name == "a" and not tok.closing:
            links.append((html.unescape(_attrs(tok.attrs).get("href") or ""), len(parts)))
        elif tok.name == "a" and links:
            href, at = links.pop()
            if href and href != "".join(parts[at:]).strip():
                parts.append(f" ({href})")
    return "".join(parts)
