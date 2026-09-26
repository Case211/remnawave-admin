"""Разметка предупреждений: что пропустит Telegram, каким выйдет письмо и текст для кабинета.

Telegram отвергает сообщение целиком из-за одной мелочи, и клиент не получает
ничего — поэтому проверка при сохранении шаблона должна ловить ровно то, на
чём спотыкается Telegram, и не мешать тому, что он принимает.
"""
from web.backend.core.notice_markup import (
    EMAIL_STYLE,
    describe_issue,
    telegram_markup_issues,
    telegram_to_email_html,
    telegram_to_text,
)


def codes(text):
    return [issue.code for issue in telegram_markup_issues(text)]


# ── Что Telegram примет ──


def test_everything_telegram_supports_passes():
    text = (
        "<b>жирный</b> <strong>жирный</strong> <i>курсив</i> <em>курсив</em> "
        "<u>подчёркнутый</u> <ins>подчёркнутый</ins> <s>зачёркнутый</s> <strike>x</strike> <del>x</del>\n"
        '<tg-spoiler>спойлер</tg-spoiler> <span class="tg-spoiler">спойлер</span>\n'
        '<a href="https://stijoin.com/rules">правила</a> <code>код</code>\n'
        '<pre><code class="language-python">print(1)</code></pre>\n'
        "<blockquote expandable>цитата</blockquote>\n"
        '<tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>\n'
        "&lt; &gt; &amp; &quot; &#169; &#x1F600;"
    )

    assert codes(text) == []


def test_formatting_nests_inside_formatting():
    assert codes("<b>жирный <i>и курсив <u>и подчёркнутый</u></i></b>") == []


# ── На чём Telegram спотыкается ──


def test_bare_special_characters_must_be_escaped():
    assert codes("Скидка 50% & бонус") == ["raw_amp"]
    assert codes("если a < b") == ["raw_lt"]
    assert codes("стрелка ->") == ["raw_gt"]


def test_only_four_named_entities_exist_for_telegram():
    issues = telegram_markup_issues("пробел&nbsp;тут")

    assert [i.code for i in issues] == ["unknown_entity"]
    assert issues[0].params == {"entity": "&nbsp;"}


def test_line_breaks_are_newlines_not_tags():
    """<br> и <p> Telegram не понимает — перенос это просто Enter."""
    assert codes("строка<br>строка") == ["line_break"]
    assert codes("<p>абзац</p>") == ["line_break", "line_break"]
    assert codes("<h1>заголовок</h1>") == ["unknown_tag", "unknown_tag"]


def test_unclosed_and_mismatched_tags():
    assert codes("<b>жирный без конца") == ["unclosed"]
    assert codes("лишний </b>") == ["unexpected_close"]
    assert codes("<b><i>крест</b></i>") == ["mismatched", "unexpected_close"]


def test_attribute_rules():
    assert codes("<a>без адреса</a>") == ["missing_attr"]
    assert codes('<b class="x">жирный</b>') == ["bad_attr"]
    assert codes("<span>просто span</span>") == ["missing_attr"]
    assert codes('<code class="language-python">вне pre</code>') == ["bad_attr"]
    assert codes('<tg-emoji emoji-id="abc">👍</tg-emoji>') == ["missing_attr"]


def test_nesting_rules():
    assert codes('<a href="https://a.io"><a href="https://b.io">x</a></a>') == ["nested_link"]
    assert codes("<blockquote><blockquote>x</blockquote></blockquote>") == ["nested_quote"]
    assert codes("<code><b>x</b></code>") == ["inside_code"]
    assert codes("<pre><i>x</i></pre>") == ["inside_code"]


def test_self_closing_tags_are_not_supported():
    assert codes("<b/>") == ["self_closing"]


def test_issue_points_at_the_exact_place():
    """Редактор подсвечивает место ошибки — позиция должна быть точной."""
    text = "первая строка\nвторая & третья"
    issue = telegram_markup_issues(text)[0]

    assert text[issue.start:issue.end] == "&"
    assert describe_issue(text, issue) == "raw_amp at 2:8"


# ── Письмо из текста Telegram ──


def _letter(inner: str) -> str:
    return f'<div style="{EMAIL_STYLE}">{inner}</div>'


def test_letter_keeps_line_breaks_and_formatting():
    text = "Здравствуйте!\n<b>Важно</b>: <tg-spoiler>тайна</tg-spoiler>"

    assert telegram_to_email_html(text) == _letter("Здравствуйте!<br>\n<b>Важно</b>: <span>тайна</span>")


def test_letter_keeps_preformatted_text_as_is():
    assert telegram_to_email_html("<pre>a\nb</pre>") == _letter("<pre>a\nb</pre>")


def test_letter_translates_telegram_only_tags():
    html = telegram_to_email_html(
        '<blockquote expandable>цитата</blockquote><tg-emoji emoji-id="1">👍</tg-emoji>'
    )

    assert "<blockquote style=" in html and "expandable" not in html
    assert "tg-emoji" not in html and "👍" in html


def test_letter_escapes_stray_special_characters():
    """Старый текст с голым «&» не должен ломать вёрстку письма."""
    assert telegram_to_email_html("A & B < C") == _letter("A &amp; B &lt; C")


# ── Простой текст для кабинета и текстовой части письма ──


def test_plain_text_drops_tags_and_decodes_entities():
    text = '<b>Внимание</b>: см. <a href="https://stijoin.com/rules">правила</a> &amp; &lt;FAQ&gt;'

    assert telegram_to_text(text) == "Внимание: см. правила (https://stijoin.com/rules) & <FAQ>"


def test_plain_text_does_not_repeat_link_that_is_its_own_label():
    assert telegram_to_text('<a href="https://stijoin.com">https://stijoin.com</a>') == "https://stijoin.com"


def test_plain_text_of_nothing_is_empty():
    assert telegram_to_text(None) == ""
    assert telegram_to_text("") == ""
