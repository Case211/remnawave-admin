"""Кнопки плагинов под телеграм-уведомлением: сборка callback_data."""
from web.backend.core.plugin_api import plugin_actions_markup


def _action(**kw):
    base = {"text": "✅ Блок был", "action": "fb_yes", "ref": "42"}
    base.update(kw)
    return base


def test_markup_carries_plugin_and_action():
    markup = plugin_actions_markup("block_radar", [_action()])
    assert markup == {
        "inline_keyboard": [[{"text": "✅ Блок был", "callback_data": "pact:block_radar:fb_yes:42"}]]
    }


def test_no_plugin_no_buttons():
    """Без plugin_id нажатие некому адресовать — кнопки не рисуем."""
    assert plugin_actions_markup(None, [_action()]) is None
    assert plugin_actions_markup("block_radar", []) is None
    assert plugin_actions_markup("block_radar", None) is None


def test_colon_in_parts_is_rejected():
    """Двоеточие — разделитель callback_data: с ним бот разберёт кнопку не так."""
    assert plugin_actions_markup("block:radar", [_action()]) is None
    assert plugin_actions_markup("block_radar", [_action(action="fb:yes")]) is None
    assert plugin_actions_markup("block_radar", [_action(ref="4:2")]) is None


def test_too_long_callback_is_dropped():
    """Telegram режет callback_data на 64 байтах, и кнопка утащила бы за
    собой всё сообщение — лучше остаться без неё."""
    assert plugin_actions_markup("block_radar", [_action(ref="9" * 100)]) is None

    markup = plugin_actions_markup("block_radar", [_action(), _action(ref="9" * 100)])
    assert len(markup["inline_keyboard"][0]) == 1  # длинная выпала, обычная осталась


def test_empty_text_or_action_skipped():
    assert plugin_actions_markup("block_radar", [_action(text="  ")]) is None
    assert plugin_actions_markup("block_radar", [_action(action="")]) is None


def test_ref_is_optional():
    """Кнопке может быть нечего уточнять — хвост тогда пустой, но формат тот же."""
    markup = plugin_actions_markup("block_radar", [_action(ref="")])
    assert markup["inline_keyboard"][0][0]["callback_data"] == "pact:block_radar:fb_yes:"
