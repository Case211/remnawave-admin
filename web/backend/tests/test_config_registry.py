"""Инварианты реестра настроек shared/config_service.DEFAULT_CONFIG_DEFINITIONS.

Регрессия 2026-07-17: финансовый модуль добавил ключи с category='finance',
но 'finance' не был в enum ConfigCategory → на старте _create_config падал
'finance' is not a valid ConfigCategory для каждого ключа. Ловим заранее.
"""
from shared.config_service import ConfigCategory, DEFAULT_CONFIG_DEFINITIONS


def test_all_categories_are_valid_enum_members():
    valid = {e.value for e in ConfigCategory}
    used = {c.get("category", "general") for c in DEFAULT_CONFIG_DEFINITIONS}
    bad = used - valid
    assert not bad, f"categories not in ConfigCategory enum: {bad}"


def test_every_config_constructs_category():
    # ровно то, что делает _create_config на старте
    for c in DEFAULT_CONFIG_DEFINITIONS:
        ConfigCategory(c.get("category", "general"))


def test_config_keys_unique():
    keys = [c["key"] for c in DEFAULT_CONFIG_DEFINITIONS]
    dupes = {k for k in keys if keys.count(k) > 1}
    assert not dupes, f"duplicate config keys: {dupes}"


def test_all_telegram_notification_types_have_topic_and_toggle():
    keys = {c["key"] for c in DEFAULT_CONFIG_DEFINITIONS}
    for notification_type in (
        "users",
        "nodes",
        "service",
        "hwid",
        "crm",
        "errors",
        "violations",
        "finance",
    ):
        assert f"notifications_topic_{notification_type}" in keys
        assert f"notifications_{notification_type}_enabled" in keys
