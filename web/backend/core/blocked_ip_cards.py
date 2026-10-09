"""Карточка уведомления о блокировке адреса.

Блокировка адреса — мера широкая: на ноде ставится DROP на весь трафик с него,
а не только на VPN-порты, и по подсети под неё попадают все, кто за ней сидит.
Поэтому в карточке главное не сам факт, а кого это задело — это таблица.
"""
from typing import Any, Dict, Sequence

from shared.i18n import tr
from shared.tg_card import Card, b, code, i, join, when
from web.backend.core.hwid_cards import connections_cell, people_table


def _is_subnet(ip_cidr: str) -> bool:
    """Одиночный адрес или подсеть — от этого зависит цена ошибки."""
    return "/" in ip_cidr and not ip_cidr.endswith("/32")


def blocked_ip_card(
    row: Dict[str, Any],
    users: Sequence[Dict[str, Any]],
    *,
    pushed_nodes: int = 0,
    admin_username: str = "",
) -> Card:
    ip_cidr = str(row.get("ip_cidr") or "")
    provider = row.get("asn_org")
    expires = row.get("expires_at")

    card = Card(tr("notify.blocked_ip.title"), emoji="🚫")
    card.text(i(tr("notify.blocked_ip.subtitle")))
    card.fields([
        (tr("notify.ip_trial.field.ip"), code(ip_cidr)),
        (tr("notify.ip_trial.field.provider"), join(provider, row.get("country_code")) if provider else None),
        (tr("notify.blocked_ip.field.expires"),
         when(expires) if expires else tr("notify.blocked_ip.forever")),
        (tr("notify.blocked_ip.field.nodes"),
         b(str(pushed_nodes)) if pushed_nodes else tr("notify.blocked_ip.no_agents")),
    ])
    if _is_subnet(ip_cidr):
        card.text(["⚠️ ", b(tr("notify.blocked_ip.subnet"))])

    if users:
        trials = sum(1 for u in users if u.get("is_trial"))
        active = sum(1 for u in users if u.get("is_active"))
        card.section(tr("notify.blocked_ip.affected", count=len(users)))
        card.lead(tr("notify.blocked_ip.summary.trials", count=trials) if trials else None,
                  tr("notify.blocked_ip.summary.active", count=active) if active else None)
        people_table(card, users, extra=[(tr("notify.people.col.conns"), connections_cell)])
    else:
        card.text(i(tr("notify.blocked_ip.nobody")))

    # причина — слова админа, поэтому цитатой с его именем
    reason = row.get("reason")
    if reason:
        card.quote(reason, credit=admin_username or None)
    elif admin_username:
        card.fields([(tr("notify.blocked_ip.field.admin"), admin_username)])
    return card.stamp()
