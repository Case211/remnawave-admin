"""Уведомления о витрине плагинов: что считается новостью, а что нет.

Панель сравнивает очередной каталог лиц-сервера с предыдущим. Ошибиться
здесь дорого в обе стороны: молчание — и владелец не узнает о релизе,
лишний шум — и уведомления перестают читать.
"""
import pytest

from web.backend.core.plugin_announcer import announce, diff_catalog


def _card(pid: str, version: str = "1.0.0", *, purchasable: bool = True) -> dict:
    return {
        "id": pid,
        "name": {"ru": pid.title(), "en": pid},
        "summary": {"ru": "Описание"},
        "latest_version": version,
        "purchasable": purchasable,
    }


def _catalog(*cards: dict) -> dict:
    return {"catalog_version": 1, "plugins": list(cards)}


class TestDiffCatalog:
    def test_first_catalog_is_only_a_baseline(self):
        """Первый заход — точка отсчёта, а не «вышло два новых плагина»."""
        assert diff_catalog(None, _catalog(_card("block_radar"), _card("smart_support"))) == []

    def test_new_plugin_on_sale_is_announced(self):
        events = diff_catalog(_catalog(_card("smart_support")),
                              _catalog(_card("smart_support"), _card("block_radar")))
        assert [(k, c["id"]) for k, c, _ in events] == [("new", "block_radar")]

    def test_new_plugin_not_for_sale_stays_quiet(self):
        """Карточка без продаж — не реклама: покупать всё равно нечего."""
        events = diff_catalog(_catalog(_card("smart_support")),
                              _catalog(_card("smart_support"),
                                       _card("block_radar", purchasable=False)))
        assert events == []

    def test_version_bump_of_installed_plugin(self):
        events = diff_catalog(_catalog(_card("block_radar", "0.3.0")),
                              _catalog(_card("block_radar", "0.4.0")),
                              installed=["block_radar"])
        assert [(k, c["id"], old) for k, c, old in events] == [("update", "block_radar", "0.3.0")]

    def test_version_bump_of_foreign_plugin_is_silent(self):
        """Не установлен — значит это релиз-ноты чужого софта."""
        assert diff_catalog(_catalog(_card("block_radar", "0.3.0")),
                            _catalog(_card("block_radar", "0.4.0")),
                            installed=[]) == []

    def test_same_version_is_not_news(self):
        assert diff_catalog(_catalog(_card("block_radar", "0.3.0")),
                            _catalog(_card("block_radar", "0.3.0")),
                            installed=["block_radar"]) == []

    def test_rollback_is_not_announced_as_release(self):
        """Отзыв плохого релиза не должен читаться как «вышла новая версия»."""
        assert diff_catalog(_catalog(_card("block_radar", "0.4.0")),
                            _catalog(_card("block_radar", "0.3.0")),
                            installed=["block_radar"]) == []

    def test_numeric_order_not_lexicographic(self):
        """0.10.0 новее 0.9.0 — сравнение по числам, не по строкам."""
        events = diff_catalog(_catalog(_card("block_radar", "0.9.0")),
                              _catalog(_card("block_radar", "0.10.0")),
                              installed=["block_radar"])
        assert len(events) == 1

    def test_disappeared_plugin_is_not_an_event(self):
        assert diff_catalog(_catalog(_card("a"), _card("b")), _catalog(_card("a"))) == []

    def test_survives_broken_payload(self):
        assert diff_catalog({"plugins": "нет"}, {"plugins": None}) == []
        assert diff_catalog(_catalog(_card("a")), {}) == []


class TestAnnounce:
    @pytest.mark.asyncio
    async def test_sends_one_notification_per_event(self, monkeypatch):
        sent = []

        async def fake_create(**kwargs):
            sent.append(kwargs)
            return 1

        monkeypatch.setattr(
            "web.backend.core.notification_service.create_notification", fake_create
        )
        await announce([("new", _card("block_radar", "0.3.0"), ""),
                        ("update", _card("smart_support", "1.3.0"), "1.2.0")])

        assert len(sent) == 2
        assert "block_radar" in sent[0]["title"] or "Block_Radar" in sent[0]["title"]
        assert sent[0]["link"] == "/admin/plugins"
        # версия в ключе дедупа: следующий релиз того же плагина не будет съеден
        assert sent[1]["group_key"] == "plugin_update:smart_support:1.3.0"
        assert "1.2.0" in sent[1]["body"]

    @pytest.mark.asyncio
    async def test_delivery_failure_does_not_propagate(self, monkeypatch):
        """Упавшее уведомление не должно ронять heartbeat, который его вызвал."""
        async def boom(**kwargs):
            raise RuntimeError("telegram down")

        monkeypatch.setattr(
            "web.backend.core.notification_service.create_notification", boom
        )
        await announce([("new", _card("block_radar"), "")])
