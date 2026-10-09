"""Карточки уведомлений (shared/tg_card): одна модель — rich-блоки и HTML-фолбэк."""
from datetime import datetime, timezone

from shared import i18n
from shared.tg_card import (
    Card, b, code, html, join, link, mark, plain, rich, s, section, spoiler, tg_user, when,
)


class TestInline:
    def test_user_text_stays_raw_in_rich_and_escaped_in_html(self):
        nick = "<script>_x_</script> & co"
        assert rich(nick) == nick
        assert html(nick) == "&lt;script&gt;_x_&lt;/script&gt; &amp; co"

    def test_nested_spans(self):
        x = ["Юзер ", b(code("alex")), " · ", mark("87")]
        assert rich(x) == [
            "Юзер ",
            {"type": "bold", "text": {"type": "code", "text": "alex"}},
            " · ",
            {"type": "marked", "text": "87"},
        ]
        # в обычном HTML маркера нет — там он жирный
        assert html(x) == "Юзер <b><code>alex</code></b> · <b>87</b>"
        assert plain(x) == "Юзер alex · 87"

    def test_adjacent_strings_are_merged(self):
        assert rich(["a", "b", None, "", ["c"]]) == "abc"

    def test_link_and_telegram_user(self):
        assert rich(link("открыть", "https://x.io/?a=1&b=2")) == {
            "type": "url", "text": "открыть", "url": "https://x.io/?a=1&b=2"}
        assert html(link("открыть", "https://x.io/?a=1&b=2")) == '<a href="https://x.io/?a=1&amp;b=2">открыть</a>'
        assert rich(tg_user("Вася", 42))["url"] == "tg://user?id=42"

    def test_spoiler_and_strike(self):
        assert html([s("было"), " → ", spoiler("секрет")]) == "<s>было</s> → <tg-spoiler>секрет</tg-spoiler>"

    def test_time_is_shown_in_reader_timezone(self):
        moment = datetime(2026, 10, 9, 12, 30, tzinfo=timezone.utc)
        span = when(moment, "r")
        node = rich(span)
        assert node["type"] == "date_time"
        assert node["unix_time"] == int(moment.timestamp())
        assert node["date_time_format"] == "r"
        assert node["text"]  # запасной текст для клиентов без tg-time
        assert html(span).startswith(f'<tg-time unix="{int(moment.timestamp())}" format="r">')

    def test_naive_time_is_utc_and_garbage_is_skipped(self):
        naive = datetime(2026, 10, 9, 12, 30)
        assert rich(when(naive))["unix_time"] == int(naive.replace(tzinfo=timezone.utc).timestamp())
        assert when(None) is None and when("not a date") is None

    def test_join_skips_empty_parts(self):
        assert plain(join("a", None, "", b("c"))) == "a · c"


class TestBlocks:
    def test_card_title_with_emoji_is_heading(self):
        blocks = Card("Нода упала", emoji="🔴").to_blocks()
        assert blocks == [{"type": "heading", "text": "🔴 Нода упала", "size": 3}]

    def test_fields_become_compact_table_and_drop_empty_values(self):
        card = Card("t").fields([("Юзер", code("alex")), ("Email", None), ("Скор", "87")])
        table = card.to_blocks()[1]
        assert table["type"] == "table" and table["is_compact"] is True
        assert len(table["cells"]) == 2
        key, value = table["cells"][0]
        assert key == {"text": "Юзер", "align": "left", "valign": "top", "is_header": True}
        assert value == {"text": {"type": "code", "text": "alex"}, "align": "left", "valign": "top"}
        assert "Юзер: <code>alex</code>\nСкор: 87" in card.to_html()

    def test_table_cells_carry_required_alignment(self):
        card = Card("t").table([["1.2.3.4", "MTS", "3"]], head=["IP", "Провайдер", "Сессий"],
                               align=["left", "left", "right"], caption="Адреса")
        table = card.to_blocks()[1]
        head, row = table["cells"]
        assert all(c["is_header"] for c in head)
        assert [c["align"] for c in row] == ["left", "left", "right"]
        assert all(c["valign"] == "top" for c in head + row)
        assert table["caption"] == "Адреса" and table["is_striped"] is True
        # в HTML таблиц нет: строка таблицы — строка текста
        assert "<b>Адреса</b>\n<i>IP · Провайдер · Сессий</i>\n1.2.3.4 · MTS · 3" in card.to_html()

    def test_empty_cell_is_dash_not_invisible(self):
        cell = Card("t").table([["a", None]]).to_blocks()[1]["cells"][0][1]
        assert cell["text"] == "—"

    def test_checklist(self):
        card = Card("t").checklist([("Отключён", True), ("Уведомлён", False)])
        items = card.to_blocks()[1]["items"]
        assert items[0]["has_checkbox"] and items[0]["is_checked"]
        assert items[1]["has_checkbox"] and "is_checked" not in items[1]
        assert "✅ Отключён\n⬜ Уведомлён" in card.to_html()

    def test_quote_with_credit(self):
        card = Card("t").quote("Не работает\nпомогите", credit="alex")
        quote = card.to_blocks()[1]
        assert quote["type"] == "blockquote" and quote["credit"] == "alex"
        assert [blk["text"] for blk in quote["blocks"]] == ["Не работает", "помогите"]
        assert "<blockquote>Не работает\nпомогите\n— <i>alex</i></blockquote>" in card.to_html()

    def test_details_fold_secondary_and_never_nest_quotes_in_html(self):
        inner = section().quote("цитата").bullets(["a", "b"])
        card = Card("t").details(join("История", "3"), inner)
        det = card.to_blocks()[1]
        assert det["type"] == "details" and det["summary"] == "История · 3"
        assert [blk["type"] for blk in det["blocks"]] == ["blockquote", "list"]
        fallback = card.to_html()
        assert fallback.count("<blockquote") == 1  # вложенных цитат Telegram не примет
        assert "<blockquote expandable><b>История · 3</b>\n› цитата" in fallback

    def test_empty_details_is_skipped(self):
        assert len(Card("t").details("пусто", section()).to_blocks()) == 1

    def test_code_with_language(self):
        card = Card("t").code('{"a": 1}', "json")
        assert card.to_blocks()[1] == {"type": "pre", "text": '{"a": 1}', "language": "json"}
        assert '<pre><code class="language-json">{"a": 1}</code></pre>' in card.to_html()

    def test_footer_and_divider(self):
        card = Card("t").text("x").divider().footer("Remnawave Admin", "коллектор")
        assert [blk["type"] for blk in card.to_blocks()] == ["heading", "paragraph", "divider", "footer"]
        assert card.to_html().endswith("<i>Remnawave Admin · коллектор</i>")

    def test_body_text_for_in_app(self):
        card = Card("Нарушение").lead("alex", b("87")).fields([("IP", "1.2.3.4")])
        assert card.title_text() == "Нарушение"
        assert card.body_text() == "alex · 87\n\nIP: 1.2.3.4"


class TestHtmlLimit:
    def test_tail_blocks_are_dropped_whole(self):
        card = Card("t").text("начало")
        for n in range(40):
            card.text(f"строка {n} " + "x" * 200)
        out = card.to_html(limit=1000)
        assert len(out) <= 1000
        assert out.startswith("<b>t</b>\n\nначало") and out.endswith("…")
        assert out.count("<b>") == out.count("</b>")


class TestSharedI18n:
    def test_reads_bot_locales_with_fallback(self, monkeypatch):
        monkeypatch.setattr(i18n, "language", lambda: "en")
        assert i18n.tr("notify.card.brand") == "Remnawave Admin"
        # ключа нет нигде — возвращается сам ключ
        assert i18n.tr("notify.__nope__") == "notify.__nope__"

    def test_format_errors_do_not_raise(self, monkeypatch):
        monkeypatch.setattr(i18n, "language", lambda: "ru")
        monkeypatch.setattr(i18n, "_messages", lambda lang: {"k": "Привет, {name}"})
        assert i18n.tr("k", name="Вася") == "Привет, Вася"
        assert i18n.tr("k", other=1) == "Привет, {name}"
