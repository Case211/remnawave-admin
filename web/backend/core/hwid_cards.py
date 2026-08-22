"""Карточки уведомлений про HWID: переезд устройства и чёрный список.

Текст собирается по тому же канону, что и карточка нарушения, потому что из
него бот строит rich-сообщение (``shared/tg_rich.py``): первая строка —
заголовок, строки с отступом в три пробела — элементы списка, пустая строка —
граница абзаца, ``<blockquote expandable>`` — сворачиваемая секция. Плоский
текст доезжает как плоский текст, поэтому важна именно эта разметка.
"""
from datetime import datetime
from html import escape
from typing import Any, Dict, List, Optional, Sequence

PLATFORM_NAMES = {
    "android": "Android", "ios": "iOS", "windows": "Windows",
    "macos": "macOS", "linux": "Linux",
}


def esc(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=False)


def fmt_dt(value: Any) -> str:
    """Дата человеку: «22.08.2026 12:50». Пустое — пустая строка."""
    if not value:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return esc(value)
    if isinstance(value, datetime):
        return value.strftime("%d.%m.%Y %H:%M")
    return esc(value)


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


def _subscription_note(user: Dict[str, Any]) -> str:
    """«Пробная, до 09.09.2026» / «Отключена» — состояние подписки одной строкой."""
    bits = []
    if user.get("is_trial"):
        bits.append("пробная")
    status = str(user.get("status") or "").upper()
    if status and status != "ACTIVE":
        bits.append({"DISABLED": "отключена", "EXPIRED": "истекла",
                     "LIMITED": "лимит"}.get(status, status.lower()))
    expire = fmt_dt(user.get("expire_at"))
    if expire:
        bits.append("до " + expire.split(" ")[0])
    return ", ".join(bits)


def user_lines(user: Dict[str, Any], *, mark_removed: bool = True) -> List[str]:
    """Пользователь как элементы списка: имя, телеграм, состояние, отвязка."""
    name = user.get("username") or str(user.get("uuid") or user.get("user_uuid") or "")[:8]
    lines = [f"   \U0001f464 <code>{esc(name)}</code>"]
    if user.get("telegram_id"):
        lines.append(f"   \U0001f4f1 TG ID: <code>{esc(user['telegram_id'])}</code>")
    if user.get("email"):
        lines.append(f"   \U0001f4e7 <code>{esc(user['email'])}</code>")
    note = _subscription_note(user)
    if note:
        lines.append(f"   \U0001f39f Подписка: {esc(note)}")
    if mark_removed and user.get("removed_at"):
        lines.append(f"   \U0001f513 Устройство отвязано: {esc(fmt_dt(user['removed_at']))}")
    conns = user.get("active_connections")
    if conns:
        lines.append(f"   \U0001f7e2 Подключений сейчас: <b>{int(conns)}</b>")
    return lines


def _header(icon: str, title: str, subtitle: str) -> List[str]:
    return [f"{icon} <b>{esc(title)}</b>", "", f"\U0001f4a1 {esc(subtitle)}", ""]


def _device_block(hwid: str, device: Optional[Dict[str, Any]]) -> List[str]:
    lines = ["\U0001f4bb <b>Устройство</b>", f"   \U0001f511 <code>{esc(hwid)}</code>"]
    info = device_line(device)
    if info:
        lines.append(f"   \U0001f4f2 {esc(info)}")
    return lines + [""]


def _others_block(icon: str, title: str, users: Sequence[Dict[str, Any]],
                  limit: int = 4) -> List[str]:
    """Список чужих подписок. Длинный хвост прячем в сворачиваемую секцию."""
    lines = [f"{icon} <b>{esc(title)} ({len(users)})</b>"]
    for index, user in enumerate(users[:limit]):
        if index:
            lines.append("")  # иначе соседние люди сливаются в один список
        lines.extend(user_lines(user))
    tail = users[limit:]
    if tail:
        names = ", ".join(
            esc(u.get("username") or str(u.get("uuid") or u.get("user_uuid") or "")[:8])
            for u in tail
        )
        lines.append(f"<blockquote expandable>И ещё {len(tail)}: {names}</blockquote>")
    return lines + [""]


def reuse_card(hwid: str, target: Dict[str, Any], repeat_trials: Sequence[Dict[str, Any]],
               strangers: Sequence[Dict[str, Any]], device: Optional[Dict[str, Any]] = None) -> str:
    """Устройство привязали к аккаунту, где его раньше не видели."""
    repeat = bool(repeat_trials)
    lines = _header(
        "\U0001f501",
        "Повторная пробная с того же устройства" if repeat else "HWID переехал на другой аккаунт",
        "Тот же человек снова взял пробную подписку на этом железе" if repeat
        else "Устройство уже видели на другом аккаунте",
    )
    lines += _device_block(hwid, device)
    lines.append("\U0001f3af <b>Куда привязали</b>")
    lines.extend(user_lines(target, mark_removed=False))
    lines.append("")
    if repeat_trials:
        lines += _others_block("\U0001f534", "Прежние пробные того же человека", repeat_trials)
    if strangers:
        lines += _others_block("\U0001f7e0", "Другие аккаунты на этом устройстве", strangers)
    return "\n".join(lines).rstrip()


def blacklist_card(hwid: str, entry: Dict[str, Any], affected: Sequence[Dict[str, Any]],
                   blocked: bool) -> str:
    """Совпадение с чёрным списком: кого нашли и что с ними сделали."""
    lines = _header(
        "\U0001f6ab" if blocked else "⚠️",
        "Чёрный список HWID: аккаунты отключены" if blocked
        else "Чёрный список HWID: найдено совпадение",
        "Устройство из списка, подписки погашены через панель" if blocked
        else "Устройство из списка, действие — только оповещение",
    )
    lines += _device_block(hwid, None)
    lines += _others_block("\U0001f465", "Отключены" if blocked else "Найдены", affected)
    reason = entry.get("reason")
    if reason:
        lines.append(f"\U0001f4dd Причина в списке: {esc(reason)}")
    added_by = entry.get("added_by_username")
    if added_by:
        lines.append(f"   \U0001f464 Внёс: {esc(added_by)} · {esc(fmt_dt(entry.get('created_at')))}")
    return "\n".join(lines).rstrip()


def revived_card(hwid: str, entry: Dict[str, Any], users: Sequence[Dict[str, Any]],
                 blocked: bool) -> str:
    """Подписка ожила уже после блокировки — сторож её погасил (или заметил)."""
    lines = _header(
        "♻️",
        "Подписка ожила и снова отключена" if blocked
        else "Живая подписка на устройстве из списка",
        "Устройство в чёрном списке, но подписка снова заработала" if blocked
        else "Действие записи — оповещение, подписку не трогаем",
    )
    lines += _device_block(hwid, None)
    lines += _others_block("\U0001f465", "Кого касается", users)
    reason = entry.get("reason")
    if reason:
        lines.append(f"\U0001f4dd Причина в списке: {esc(reason)}")
    return "\n".join(lines).rstrip()
