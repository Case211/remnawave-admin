"""Карточки уведомлений про HWID: переезд устройства и чёрный список.

Собираются моделью shared.tg_card: люди идут таблицей «аккаунт — telegram —
подписка», длинный хвост сворачивается, время показывается в поясе читателя.
Здесь же общие куски для карточек про адреса (ip_guard, blocked_ip_cards):
там те же люди и тот же разговор о том, кого задело.
"""
from typing import Any, Dict, Optional, Sequence

from shared import timefmt
from shared.i18n import tr
from shared.tg_card import Card, code, i, join, section, tg_user, when

PLATFORM_NAMES = {
    "android": "Android", "ios": "iOS", "windows": "Windows",
    "macos": "macOS", "linux": "Linux",
}

# Сколько людей показывать таблицей; остальные — свёрнутым списком имён
PEOPLE_SHOWN = 5


def device_line(device: Optional[Dict[str, Any]]) -> str:
    """«Android 15 (Happ 3.25.1)» из записи устройства."""
    if not device:
        return ""
    platform = device.get("platform") or ""
    parts = [PLATFORM_NAMES.get(platform.lower(), platform) if platform else ""]
    if device.get("os_version"):
        parts.append(str(device["os_version"]))
    line = " ".join(p for p in parts if p)
    model = device.get("device_model")
    if model:
        line = f"{line} · {model}" if line else str(model)
    app = device.get("app_version")
    if app:
        line = f"{line} ({app})" if line else str(app)
    return line


def account_name(user: Dict[str, Any]) -> str:
    return user.get("username") or str(user.get("uuid") or user.get("user_uuid") or "")[:8]


def subscription_note(user: Dict[str, Any], *, mark_removed: bool = True) -> str:
    """«пробная, до 09.09.2026» / «отключена» — состояние подписки одной строкой."""
    bits = []
    if user.get("is_trial"):
        bits.append(tr("notify.people.trial"))
    status = str(user.get("status") or "").upper()
    if status and status != "ACTIVE":
        label = tr(f"notify.people.status.{status}")
        bits.append(status.lower() if label == f"notify.people.status.{status}" else label)
    if user.get("expire_at"):
        bits.append(tr("notify.people.until", date=timefmt.fmt_date(user["expire_at"])))
    if mark_removed and user.get("removed_at"):
        bits.append(tr("notify.people.removed", date=timefmt.fmt(user["removed_at"])))
    return ", ".join(bits)


def account_cell(user: Dict[str, Any]):
    """Имя аккаунта; есть Telegram — имя ведёт в профиль, отдельная колонка не нужна."""
    name = account_name(user)
    return tg_user(name, user["telegram_id"]) if user.get("telegram_id") else code(name)


def connections_cell(user: Dict[str, Any]):
    """«41 · 5 минут назад» — сколько подключений и когда было последнее."""
    return join(str(int(user.get("conns") or 0)), when(user.get("last_seen"), "r"))


def people_table(card, users: Sequence[Dict[str, Any]], *, extra: Sequence = (),
                 mark_removed: bool = True) -> None:
    """Люди таблицей: имя (ссылкой на Telegram), подписка и колонки ``extra``.

    ``extra`` — пары (заголовок, функция user → значение ячейки). Колонка
    Email появляется, только если хоть у кого-то он есть: таблица не должна
    расползаться шире экрана телефона. Больше PEOPLE_SHOWN человек — хвост
    сворачивается списком имён.
    """
    shown = list(users[:PEOPLE_SHOWN])
    columns = [(tr("notify.people.col.account"), account_cell)]
    if any(u.get("email") for u in shown):
        columns.append((tr("notify.people.col.email"), lambda u: code(u["email"]) if u.get("email") else None))
    columns.append((tr("notify.people.col.subscription"),
                    lambda u: subscription_note(u, mark_removed=mark_removed) or None))
    columns.extend(extra)
    card.table([[cell(u) for _, cell in columns] for u in shown], head=[title for title, _ in columns])

    tail = users[PEOPLE_SHOWN:]
    if tail:
        card.details(tr("notify.card.more", count=len(tail)),
                     section().text(join(*(account_name(u) for u in tail), sep=", ")))


def active_now(user: Dict[str, Any]) -> Optional[str]:
    conns = user.get("active_connections")
    return str(int(conns)) if conns else None


def _device_fields(card: Card, hwid: str, device: Optional[Dict[str, Any]]) -> None:
    card.section(tr("notify.hwid_card.device"))
    card.fields([
        (tr("notify.hwid_card.field.hwid"), code(hwid)),
        (tr("notify.hwid_card.field.device"), device_line(device) or None),
    ])


def _entry_fields(card: Card, entry: Dict[str, Any]) -> None:
    """Запись чёрного списка: за что и кто внёс."""
    added_by = entry.get("added_by_username")
    card.fields([
        (tr("notify.hwid_card.field.reason"), entry.get("reason")),
        (tr("notify.hwid_card.field.added_by"),
         join(added_by, when(entry.get("created_at"))) if added_by else None),
    ])


def _now_column():
    return (tr("notify.people.col.now"), active_now)


def reuse_card(hwid: str, target: Dict[str, Any], repeat_trials: Sequence[Dict[str, Any]],
               strangers: Sequence[Dict[str, Any]], device: Optional[Dict[str, Any]] = None) -> Card:
    """Устройство привязали к аккаунту, где его раньше не видели."""
    kind = "repeat" if repeat_trials else "moved"
    card = Card(tr(f"notify.hwid_card.reuse.{kind}.title"), emoji="🔁")
    card.text(i(tr(f"notify.hwid_card.reuse.{kind}.subtitle")))
    _device_fields(card, hwid, device)
    card.section(tr("notify.hwid_card.reuse.target"))
    people_table(card, [target], extra=[_now_column()], mark_removed=False)
    if repeat_trials:
        card.section(tr("notify.hwid_card.reuse.repeat_trials", count=len(repeat_trials)))
        people_table(card, repeat_trials, extra=[_now_column()])
    if strangers:
        card.section(tr("notify.hwid_card.reuse.strangers", count=len(strangers)))
        people_table(card, strangers, extra=[_now_column()])
    return card.stamp()


def blacklist_card(hwid: str, entry: Dict[str, Any], affected: Sequence[Dict[str, Any]],
                   blocked: bool) -> Card:
    """Совпадение с чёрным списком: кого нашли и что с ними сделали."""
    kind = "blocked" if blocked else "found"
    card = Card(tr(f"notify.hwid_card.blacklist.{kind}.title"), emoji="🚫" if blocked else "⚠️")
    card.text(i(tr(f"notify.hwid_card.blacklist.{kind}.subtitle")))
    _device_fields(card, hwid, None)
    card.section(tr("notify.hwid_card.blacklist.disabled_users" if blocked
                    else "notify.hwid_card.blacklist.found_users", count=len(affected)))
    people_table(card, affected, extra=[_now_column()])
    _entry_fields(card, entry)
    return card.stamp()


def revived_card(hwid: str, entry: Dict[str, Any], users: Sequence[Dict[str, Any]],
                 blocked: bool) -> Card:
    """Подписка ожила уже после блокировки — сторож её погасил (или заметил)."""
    kind = "blocked" if blocked else "alive"
    card = Card(tr(f"notify.hwid_card.revived.{kind}.title"), emoji="♻️")
    card.text(i(tr(f"notify.hwid_card.revived.{kind}.subtitle")))
    _device_fields(card, hwid, None)
    card.section(tr("notify.hwid_card.revived.users", count=len(users)))
    people_table(card, users, extra=[_now_column()])
    _entry_fields(card, entry)
    return card.stamp()
