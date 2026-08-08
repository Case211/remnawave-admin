"""Гейт версии панели перед установкой плагина."""
from web.backend.api.v2.admin_plugins import panel_too_old


def test_older_panel_blocks_install():
    assert panel_too_old("4.2.0", current="4.1.0")
    assert panel_too_old("4.2.0", current="3.9.9")
    assert panel_too_old("5.0", current="4.9.9")


def test_equal_and_newer_panel_pass():
    assert not panel_too_old("4.2.0", current="4.2.0")
    assert not panel_too_old("4.2.0", current="4.3.0")
    assert not panel_too_old("4.2.0", current="5.0.0")


def test_versions_of_different_length_align():
    """«4.2» и «4.2.0» — одна и та же версия, а не старше и новее."""
    assert not panel_too_old("4.2", current="4.2.0")
    assert not panel_too_old("4.2.0", current="4.2")
    assert panel_too_old("4.2.1", current="4.2")


def test_unknown_or_empty_never_blocks():
    """Гейт предупреждает, а не строит стену там, где данных нет."""
    assert not panel_too_old("", current="4.1.0")
    assert not panel_too_old("4.2.0", current="unknown")
    assert not panel_too_old("4.2.0", current="")
