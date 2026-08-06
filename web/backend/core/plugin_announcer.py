"""Заметить изменения витрины плагинов и сказать о них владельцу панели.

Отдельный канал новостей для этого не нужен: панель и так тянет каталог
лиц-сервера, а в нём видно и появление плагина в продаже, и свежую
версию. Сравниваем очередной каталог с предыдущим и шлём уведомление —
in-app плюс Telegram, как остальные алерты панели.

Два события и разные адресаты:
  * новый плагин — только если он **доступен для покупки**; карточка,
    снятая с продажи, рекламой быть не должна;
  * новая версия — только для установленных плагинов, иначе владелец
    получал бы релиз-ноты чужого софта, который у него не стоит.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# Событие: ("new" | "update", карточка каталога, прежняя версия или "")
CatalogEvent = tuple[str, dict[str, Any], str]


def _version_tuple(raw: str) -> tuple[int, ...]:
    """«1.10.2» → (1, 10, 2). Нечисловой хвост обрывает разбор."""
    parts: list[int] = []
    for chunk in str(raw).split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            break
    return tuple(parts) if parts else (0,)


def _is_newer(candidate: str, known: str) -> bool:
    """Строго новее известной. Равные и откаты событием не считаем.

    Откат версии — обычное дело при отзыве плохого релиза, и сообщать
    «вышла новая версия 0.2.0» после 0.3.0 было бы враньём.
    """
    if not candidate or not known:
        return False
    return _version_tuple(candidate) > _version_tuple(known)


def _by_id(catalog: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    plugins = (catalog or {}).get("plugins")
    if not isinstance(plugins, list):
        return {}
    return {p["id"]: p for p in plugins if isinstance(p, dict) and p.get("id")}


def diff_catalog(
    previous: Optional[dict[str, Any]],
    current: dict[str, Any],
    installed: Iterable[str] = (),
) -> list[CatalogEvent]:
    """Что изменилось в витрине с прошлого раза.

    ``previous is None`` — панель видит каталог впервые (свежая установка
    либо первый запуск после обновления). Тут вся витрина формально
    «новая», поэтому событий не отдаём: иначе панель отрапортовала бы обо
    всём каталоге разом. Этот проход — точка отсчёта.
    """
    if previous is None:
        return []

    was = _by_id(previous)
    now = _by_id(current)
    installed = set(installed)
    events: list[CatalogEvent] = []

    for plugin_id, card in now.items():
        old = was.get(plugin_id)
        version = str(card.get("latest_version") or "")
        if old is None:
            # purchasable отсутствует у сервера постарше — там продаётся всё.
            if card.get("purchasable", True):
                events.append(("new", card, ""))
            continue
        if plugin_id not in installed:
            continue
        old_version = str(old.get("latest_version") or "")
        if _is_newer(version, old_version):
            events.append(("update", card, old_version))

    return events


def _title(card: dict[str, Any]) -> str:
    """Имя плагина по-русски, с откатом на английское и на id."""
    name = card.get("name")
    if isinstance(name, dict):
        for key in ("ru", "en"):
            if name.get(key):
                return str(name[key])
    return str(card.get("id", "плагин"))


def _summary(card: dict[str, Any]) -> str:
    text = card.get("summary")
    if isinstance(text, dict):
        for key in ("ru", "en"):
            if text.get(key):
                return str(text[key])
    return ""


async def announce(events: list[CatalogEvent]) -> None:
    """Разослать уведомления по событиям витрины.

    Сбой доставки не должен ронять heartbeat, поэтому исключения гасим:
    следующий каталог всё равно сравнивается с предыдущим, и пропущенное
    событие не повторится — зато панель продолжит жить.
    """
    if not events:
        return
    try:
        from web.backend.core.notification_service import create_notification
    except Exception:  # noqa: BLE001 — импорт падает только при кривой сборке
        logger.warning("plugin_announcer: notification service unavailable")
        return

    for kind, card, old_version in events:
        name = _title(card)
        version = str(card.get("latest_version") or "")
        if kind == "new":
            title = f"Новый плагин: {name}"
            body = _summary(card) or "Плагин доступен для покупки в разделе «Плагины»."
        else:
            title = f"Обновление плагина: {name} {version}"
            body = f"Установлена версия {old_version}. Обновить можно на карточке плагина."
        try:
            await create_notification(
                title=title,
                body=body,
                type="info",
                severity="info",
                channels=["in_app", "telegram"],
                topic_type="service",
                source="plugins",
                source_id=str(card.get("id") or ""),
                link="/admin/plugins",
                # Версия в ключе: дедуп гасит повтор одного события, но не
                # мешает сообщить о следующем релизе того же плагина.
                group_key=f"plugin_{kind}:{card.get('id')}:{version}",
            )
        except Exception:
            logger.warning("plugin_announcer: notify failed", exc_info=True)


async def announce_catalog_change(
    previous: Optional[dict[str, Any]], current: dict[str, Any]
) -> None:
    """Точка входа: сравнить каталоги и разослать, что нашлось."""
    try:
        from web.backend.core.plugins import loaded_plugins

        installed = [m.id for m in loaded_plugins()]
    except Exception:  # noqa: BLE001
        installed = []
    await announce(diff_catalog(previous, current, installed))
