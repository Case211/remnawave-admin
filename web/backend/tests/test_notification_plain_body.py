"""В карточку, пуш и WebSocket уходит текст, в Telegram — разметка.

Регрессия: источники отдавали телеграм-HTML одним полем, он ложился в базу
как есть, и в колокольчике торчали «<b>Нода:</b>».
"""
from web.backend.core.notification_service import _plain_text, _split_body


def test_markup_is_stripped_and_entities_unescaped():
    text = _plain_text("<b>Нода:</b> RU Route\n<b>Приём:</b> 4 Мбит/с &lt;5 тыс. пакетов/с\n   • <i>мелкие пакеты</i>")
    assert text == "Нода: RU Route\nПриём: 4 Мбит/с <5 тыс. пакетов/с\n   • мелкие пакеты"


def test_html_body_without_telegram_body_is_split():
    body, tg = _split_body("<b>Нода:</b> RU Route", None)
    assert body == "Нода: RU Route"
    assert tg == "<b>Нода:</b> RU Route"


def test_explicit_telegram_body_is_kept_as_is():
    body, tg = _split_body("Онлайн более 270", "<b>Онлайн</b> более 270")
    assert (body, tg) == ("Онлайн более 270", "<b>Онлайн</b> более 270")


def test_plain_text_with_comparison_sign_is_not_touched():
    body, tg = _split_body("score < 50 и > 10", None)
    assert (body, tg) == ("score < 50 и > 10", None)
