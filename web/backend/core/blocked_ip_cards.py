"""Карточка уведомления о блокировке адреса.

Тот же канон, что у HWID-карточек (``shared/tg_rich`` строит из него настоящее
rich-сообщение): первая строка — заголовок, строки с отступом в три пробела —
элементы списка, пустая строка — граница абзаца.

Блокировка адреса — мера широкая: на ноде ставится DROP на весь трафик с него,
а не только на VPN-порты, и по подсети под неё попадают все, кто за ней сидит.
Поэтому в карточке главное не сам факт, а кого это задело.
"""
from typing import Any, Dict, Sequence

from web.backend.core.hwid_cards import esc, fmt_dt


def _target_note(row: Dict[str, Any]) -> str:
    """Одиночный адрес или подсеть — от этого зависит цена ошибки."""
    ip_cidr = str(row.get("ip_cidr") or "")
    if ip_cidr.endswith("/32") or "/" not in ip_cidr:
        return ""
    return "подсеть — под блокировку попадут все адреса диапазона"


def blocked_ip_card(
    row: Dict[str, Any],
    users: Sequence[Dict[str, Any]],
    *,
    pushed_nodes: int = 0,
    admin_username: str = "",
) -> str:
    ip_cidr = str(row.get("ip_cidr") or "")
    trials = [u for u in users if u.get("is_trial")]
    active = [u for u in users if u.get("is_active")]

    lines = [
        "\U0001f6ab <b>Адрес заблокирован</b>",
        "",
        "\U0001f4a1 %s" % esc(
            "Трафик с адреса отбрасывается на нодах — целиком, не только VPN"
        ),
        "",
        "\U0001f4cd <b>Адрес</b>",
        f"   \U0001f5a7 <code>{esc(ip_cidr)}</code>",
    ]
    provider = row.get("asn_org")
    if provider:
        country = row.get("country_code")
        lines.append("   \U0001f3e2 %s%s" % (esc(provider), f" ({esc(country)})" if country else ""))
    note = _target_note(row)
    if note:
        lines.append(f"   ⚠️ {esc(note)}")
    expires = fmt_dt(row.get("expires_at"))
    lines.append(f"   \U0001f552 {esc('До ' + expires) if expires else 'Бессрочно'}")
    lines.append("")

    if users:
        lines.append(
            "\U0001f465 <b>Кого задевает ({0})</b>".format(len(users))
        )
        summary = []
        if trials:
            summary.append(f"пробных: {len(trials)}")
        if active:
            summary.append(f"с живой подпиской: {len(active)}")
        if summary:
            lines.append(f"   \U0001f4ca {esc(', '.join(summary))}")
        for index, user in enumerate(users[:5]):
            if index:
                lines.append("")
            name = user.get("username") or str(user.get("user_uuid") or "")[:8]
            lines.append(f"   \U0001f464 <code>{esc(name)}</code>")
            if user.get("telegram_id"):
                lines.append(f"   \U0001f4f1 TG ID: <code>{esc(user['telegram_id'])}</code>")
            lines.append(
                "   \U0001f50c Подключений: <b>%d</b>, последнее %s"
                % (int(user.get("conns") or 0), esc(fmt_dt(user.get("last_seen"))))
            )
        tail = users[5:]
        if tail:
            names = ", ".join(
                esc(u.get("username") or str(u.get("user_uuid") or "")[:8]) for u in tail
            )
            lines.append(f"<blockquote expandable>И ещё {len(tail)}: {names}</blockquote>")
    else:
        lines.append("\U0001f465 <b>Кого задевает</b>")
        lines.append("   За последний месяц подключений с этого адреса не было")
    lines.append("")

    reason = row.get("reason")
    if reason:
        lines.append(f"\U0001f4dd Причина: {esc(reason)}")
    if admin_username:
        lines.append(f"   \U0001f464 Внёс: {esc(admin_username)}")
    lines.append(
        "   \U0001f4e1 %s"
        % esc(f"Применено на нодах: {pushed_nodes}" if pushed_nodes else "Подключённых агентов нет — правило не применено")
    )
    return "\n".join(lines).rstrip()
