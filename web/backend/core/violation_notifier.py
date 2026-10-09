"""Violation notification formatter and sender for web backend.

Uses notification_service.create_notification() for multi-channel dispatch
(Telegram, in-app, webhook, email) instead of aiogram Bot instance.

Карточки собираются моделью shared.tg_card: в Telegram уходят rich-блоки —
таблицы подключений и устройств, сворачиваемые детали и история, цветные
кнопки действий прямо в сообщении.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from shared.analyzers.models import ACTION_LABELS, dominant_analyzer
from shared.i18n import tr
from shared.tg_card import Button, Card, b, code, copy, i, join, section, tg_account, when

logger = logging.getLogger(__name__)

# Default cooldown (can be overridden via config_service)
VIOLATION_NOTIFICATION_COOLDOWN_MINUTES = 30

# Fallback in-memory cache when DB check fails
_violation_notification_cache: Dict[str, datetime] = {}


def _cleanup_cache() -> None:
    """Remove stale entries older than 1 hour from in-memory fallback cache."""
    now = datetime.utcnow()
    max_age = timedelta(hours=1)
    expired = [k for k, v in _violation_notification_cache.items() if now - v > max_age]
    for k in expired:
        del _violation_notification_cache[k]


def _short_provider(asn_org: Optional[str]) -> str:
    """Shorten ASN org name for display."""
    if not asn_org:
        return ""
    if len(asn_org) > 25:
        return asn_org[:22] + "..."
    return asn_org


def _tr_or(key: str, default: str, **kwargs) -> str:
    """Перевод или запасной текст, если ключа нет в локали."""
    text = tr(key, **kwargs)
    return default if text == key else text


# Причины детектора — русские строки; первая подошедшая метка задаёт заголовок
_REASON_RULES = (
    ("double_tunnel", ("двойной туннель", "ссылка в user-agent", "link_in_ua")),
    ("bot_library", ("http-библиотека", "bot_library", "go-http-client")),
    ("hwid", ("hwid", "device overlap")),
    ("torrent", ("torrent", "p2p")),
    ("geo", ("impossible travel", "geo")),
    ("simultaneous", ("simultaneous", "temporal")),
    ("asn", ("datacenter", "vpn", "proxy")),
    ("traffic", ("traffic", "bandwidth")),
)


def _detect_primary_reason(reasons: List[str], breakdown: dict) -> dict:
    """Determine primary violation reason for notification title and subtitle."""
    reasons_lower = " ".join(r.lower() for r in reasons)
    for key, markers in _REASON_RULES:
        if any(marker in reasons_lower for marker in markers):
            return {
                "title": tr(f"notify.violation.reason.{key}.title"),
                "subtitle": tr(f"notify.violation.reason.{key}.subtitle"),
            }

    if breakdown:
        # Fallback: use highest-scoring analyzer
        max_score = 0
        max_key = ""
        for key, val in breakdown.items():
            s = val.get("score", 0) if isinstance(val, dict) else getattr(val, "score", 0)
            if s > max_score:
                max_score = s
                max_key = key
        if max_key:
            title = _tr_or(f"notify.violation.reason.analyzer.{max_key}",
                           tr("notify.violation.reason.analyzer_other", analyzer=max_key))
            return {
                "title": title,
                "subtitle": tr("notify.violation.reason.analyzer_subtitle",
                               analyzer=max_key, score=f"{max_score:.0f}"),
            }

    return {
        "title": tr("notify.violation.reason.generic.title"),
        "subtitle": tr("notify.violation.reason.generic.subtitle"),
    }


def _action_label(action_key: str) -> str:
    return _tr_or(f"notify.violation.action.{action_key}", ACTION_LABELS.get(action_key, action_key))


def violation_buttons(
    user_uuid: str, analyzer: Optional[str] = None, with_whitelist: bool = True,
) -> List[List[Button]]:
    """Кнопки быстрых действий; цвет — по последствиям.

    Красные карают (блокировка, отключение), зелёные снимают подозрение
    (аннулировать, белые списки), синие помогают разобраться.

    Белых списка два: полный снимает с человека все проверки, частичный —
    только тот разрез, из-за которого пришло это уведомление. Второй кнопки
    нет, когда очков не набрал ни один анализатор: предлагать разрез наугад
    хуже, чем не предлагать вовсе.

    ``with_whitelist=False`` — для торрент-событий: они живут мимо
    анализаторов нарушений, и белый список на них не влияет, так что
    кнопка там обещала бы не то, что делает.
    """
    def button(key: str, action: str, style: Optional[str] = None, **kwargs) -> Button:
        return Button(tr(f"notify.violation.btn.{key}", **kwargs),
                      callback_data=f"vact:{action}:{user_uuid}", style=style)

    rows = [
        [button("info", "info", "primary"), button("block", "block", "danger")],
        [button("kill", "kill", "danger"), button("reset", "reset")],
        [button("annul", "dismiss", "success"), button("throttle", "thr", "primary")],
    ]
    if with_whitelist:
        row = [button("whitelist", "wl", "success")]
        if analyzer:
            label = _tr_or(f"notify.violation.analyzer.{analyzer}", analyzer)
            row.append(button("whitelist_partial", f"wlp_{analyzer}", "success", analyzer=label))
        rows.append(row)
    return rows


def _violation_keyboard(
    user_uuid: str, analyzer: Optional[str] = None, with_whitelist: bool = True,
) -> Dict:
    """Те же кнопки inline-клавиатурой — для уведомлений обычным HTML
    (автоматизации, монитор скорости трафика)."""
    rows = violation_buttons(user_uuid, analyzer, with_whitelist)
    return {"inline_keyboard": [[btn.to_dict() for btn in row] for row in rows]}


async def _recap(user_uuid: str) -> Optional[dict]:
    """Рецидив для карточки: сколько раз попадался и когда.

    Разговор «за что заблокировали» проще вести по датам, чем по памяти,
    поэтому в уведомление уходит и счёт, и последние отметки времени.
    Аннулированные показываем отдельно: это признанные ошибки детектора, и
    прятать их от администратора нечестно.
    """
    from shared.config_service import config_service
    from shared.database import db_service

    try:
        days = int(config_service.get("violation_recap_days", 30) or 30)
    except (TypeError, ValueError):
        days = 30
    try:
        recap = (await db_service.violations_recap([user_uuid], days=days)).get(user_uuid)
        history = await db_service.user_violation_history(user_uuid, days=days, limit=5)
    except Exception as e:
        logger.warning("Recap for notification failed: %s", e)
        return None

    if not recap or recap.get("total", 0) <= 1:
        return None
    return {
        "days": days,
        "total": recap["total"],
        "annulled": recap.get("annulled") or 0,
        "items": [(item["detected_at"], item.get("action_taken") == "annulled") for item in history],
    }


def _add_history(card: Card, recap: Optional[dict]) -> None:
    """История нарушений — свёрнутой секцией, даты в поясе читателя."""
    if not recap:
        return
    summary = tr("notify.violation.card.history", days=recap["days"], total=recap["total"])
    if recap["annulled"]:
        summary = join(summary, tr("notify.violation.card.history_annulled", count=recap["annulled"]), sep=", ")
    items = [join(when(at), tr("notify.violation.card.annulled") if annulled else None)
             for at, annulled in recap["items"]]
    card.details(summary, section().bullets(items))


def _user_fields(card: Card, user_uuid: str, info: dict, with_description: bool = True) -> None:
    """Кто это: всё копируется касанием — искать юзера потом по этим полям."""
    card.fields([
        (tr("notify.violation.card.field.username"), copy(info.get("username"))),
        (tr("notify.violation.card.field.email"), copy(info.get("email"))),
        (tr("notify.violation.card.field.uuid"), copy(user_uuid)),
        (tr("notify.violation.card.field.telegram"), tg_account(info.get("telegramId"))),
        (tr("notify.violation.card.field.description"),
         copy(info.get("description")) if with_description else None),
    ])


def _device_row(device: dict) -> list:
    platform = device.get("platform") or "unknown"
    app_version = device.get("app_version")
    return [
        _tr_or(f"notify.violation.platform.{platform.lower()}", platform),
        device.get("os_version") or None,
        f"v{app_version}" if app_version else None,
    ]


def _ua_devices(os_list: list, client_list: list) -> list:
    """Устройства по User-Agent, когда HWID нет."""
    if os_list and client_list and len(os_list) == len(client_list):
        return [f"{os_name} ({client})" if client else os_name for os_name, client in zip(os_list, client_list)]
    parts = []
    if os_list:
        parts.append(tr("notify.violation.os_list", list=", ".join(os_list)))
    if client_list:
        parts.append(tr("notify.violation.client_list", list=", ".join(client_list)))
    return parts


async def send_violation_notification(
    user_uuid: str,
    violation_score: dict,
    user_info: Optional[dict] = None,
    active_connections: Optional[list] = None,
    ip_metadata: Optional[dict] = None,
    force: bool = False,
) -> None:
    """Send violation notification via notification_service.

    Args:
        user_uuid: User UUID.
        violation_score: Dict with total, breakdown, recommended_action, confidence, reasons.
        user_info: Optional user info from DB.
        active_connections: List of ActiveConnection objects.
        ip_metadata: Dict of {ip: IPMetadata}.
        force: If True, bypass throttling.
    """
    now = datetime.utcnow()

    # Configurable cooldown via config_service
    try:
        from shared.config_service import config_service
        cooldown_minutes = config_service.get("violation_notification_cooldown_minutes", VIOLATION_NOTIFICATION_COOLDOWN_MINUTES)
    except Exception:
        cooldown_minutes = VIOLATION_NOTIFICATION_COOLDOWN_MINUTES

    # Throttling: check in-memory cache first (fast path), then DB (persistent)
    if not force:
        # In-memory check (covers current process session, also used in tests)
        if user_uuid in _violation_notification_cache:
            last = _violation_notification_cache[user_uuid]
            if now - last < timedelta(minutes=cooldown_minutes):
                logger.debug("Violation notification throttled for user %s (cooldown)", user_uuid)
                return

        # DB check (persistent across restarts)
        try:
            from shared.database import db_service
            last_notified = await db_service.get_user_last_violation_notification(user_uuid)
            if last_notified and now - last_notified < timedelta(minutes=cooldown_minutes):
                logger.debug("Violation notification throttled for user %s (DB cooldown)", user_uuid)
                _violation_notification_cache[user_uuid] = last_notified  # Sync to memory
                return
        except Exception:
            pass  # In-memory already checked above

    _cleanup_cache()

    try:
        # User info
        if not user_info:
            from shared.database import db_service
            user_info = await db_service.get_user_by_uuid(user_uuid)

        info = user_info if user_info else {}
        username = info.get("username", "n/a")
        device_limit = info.get("hwidDeviceLimit", 1)
        if device_limit == 0:
            device_limit = "∞"

        # Score data
        total_score = violation_score.get("total", violation_score.get("score", 0))
        breakdown = violation_score.get("breakdown", {})

        # IP count from temporal breakdown
        ip_count = 0
        if breakdown and "temporal" in breakdown:
            temporal_data = breakdown["temporal"]
            if isinstance(temporal_data, dict):
                ip_count = temporal_data.get("simultaneous_connections_count", 0)
            elif hasattr(temporal_data, "simultaneous_connections_count"):
                ip_count = temporal_data.simultaneous_connections_count

        if ip_count == 0 and active_connections:
            ip_count = len(set(str(c.ip_address) for c in active_connections))

        # Collect unique IPs and nodes
        unique_ips = set()
        node_uuids = set()
        if active_connections:
            for conn in active_connections:
                unique_ips.add(str(conn.ip_address))
                if hasattr(conn, "node_uuid") and conn.node_uuid:
                    node_uuids.add(str(conn.node_uuid))

        # Resolve node names (single batch query instead of N individual queries)
        nodes_used = set()
        if node_uuids:
            try:
                from shared.database import db_service
                nodes_map = await db_service.get_nodes_by_uuids(list(node_uuids))
                for n_uuid in node_uuids:
                    node_info = nodes_map.get(n_uuid)
                    if node_info and node_info.get("name"):
                        nodes_used.add(node_info.get("name"))
                    else:
                        nodes_used.add(str(n_uuid)[:8])
            except Exception:
                nodes_used = {str(u)[:8] for u in node_uuids}
        nodes_line = tr("notify.violation.card.nodes", nodes=", ".join(sorted(nodes_used))) if nodes_used else None

        # Device info from breakdown
        os_list = []
        client_list = []
        if breakdown and "device" in breakdown:
            device_data = breakdown["device"]
            if isinstance(device_data, dict):
                os_list = device_data.get("os_list") or []
                client_list = device_data.get("client_list") or []
            elif hasattr(device_data, "os_list"):
                os_list = device_data.os_list or []
                client_list = getattr(device_data, "client_list", None) or []

        reasons = violation_score.get("reasons", [])
        primary_reason = _detect_primary_reason(reasons, breakdown)
        title_text = primary_reason["title"]

        card = Card(title_text, emoji="🚨" if total_score >= 80 else "⚠️")
        card.text(i(primary_reason["subtitle"]))
        card.lead(
            b(info.get("email") or username),
            tr("notify.violation.card.lead_score", score=f"{total_score:.1f}"),
            tr("notify.violation.card.lead_ips", count=ip_count, limit=device_limit),
        )
        _user_fields(card, user_uuid, info)

        if unique_ips:
            rows = []
            for ip in sorted(unique_ips):
                meta = (ip_metadata or {}).get(ip)
                rows.append([copy(ip), _short_provider(getattr(meta, "asn_org", None)),
                             getattr(meta, "country_code", None)])
            card.section(tr("notify.violation.card.connections"))
            card.table(
                rows,
                head=[tr("notify.violation.card.col.ip"), tr("notify.violation.card.col.provider"),
                      tr("notify.violation.card.col.country")],
                caption=nodes_line,
            )
        else:
            card.text(nodes_line)

        # HWID devices
        hwid_devices = []
        try:
            from shared.database import db_service
            hwid_devices = await db_service.get_user_hwid_devices(user_uuid)
        except Exception:
            pass

        if hwid_devices:
            card.section(tr("notify.violation.card.devices", count=len(hwid_devices), limit=device_limit))
            card.table(
                [_device_row(device) for device in hwid_devices[:5]],
                head=[tr("notify.violation.card.col.platform"), tr("notify.violation.card.col.os"),
                      tr("notify.violation.card.col.app")],
            )
            if len(hwid_devices) > 5:
                card.text(i(tr("notify.card.more", count=len(hwid_devices) - 5)))
        elif os_list or client_list:
            card.section(tr("notify.violation.card.devices_ua"))
            card.bullets(_ua_devices(os_list, client_list))

        # Reasons (deduplicated) — as "Детали пересечения"
        unique_reasons = list(dict.fromkeys(reasons))
        if unique_reasons:
            details = section().bullets(unique_reasons[:8])
            if len(unique_reasons) > 8:
                details.text(i(tr("notify.card.more", count=len(unique_reasons) - 8)))
            card.details(tr("notify.violation.card.reasons", count=len(unique_reasons)), details)

        # Что делать дальше. Формулировки — глаголами и от лица админа:
        # «ДЕЙСТВИЕ: ВРЕМЕННАЯ БЛОКИРОВКА» читалось как уже случившийся бан,
        # хотя система сама блокирует только на пороге hard_block, да и то
        # если включена автоблокировка. Единственный случай, когда это факт,
        # а не совет, — цитатой с пометкой «автоматически».
        action = violation_score.get("recommended_action", "")
        action_key = action.value if hasattr(action, "value") else str(action)

        auto_blocked = False
        if action_key == "hard_block":
            try:
                from shared.config_service import config_service
                auto_blocked = bool(config_service.get("violation_auto_hard_block", True))
            except Exception:
                auto_blocked = True

        if auto_blocked:
            card.quote(b(tr("notify.violation.card.auto_blocked")),
                       credit=tr("notify.violation.card.auto_blocked_credit"))
        else:
            card.text([tr("notify.violation.card.recommendation"), ": ", b(_action_label(action_key).upper())])
            if action_key == "hard_block":
                card.text(i(tr("notify.violation.card.auto_off")))
        _add_history(card, await _recap(user_uuid))
        card.buttons(*violation_buttons(user_uuid, dominant_analyzer(breakdown)))
        card.stamp(now)

        # Send via notification_service
        from web.backend.core.notification_service import create_notification

        await create_notification(
            title=title_text,
            body=card.body_text(),
            type="violation",
            severity="warning" if total_score < 80 else "critical",
            source="collector",
            source_id=user_uuid,
            link=f"/users/{user_uuid}",
            group_key=f"violation:{user_uuid}",
            channels=["telegram", "in_app", "push"],
            topic_type="violations",
            telegram_card=card,
            event="violation.detected",
        )

        # Update throttling: persistent DB + in-memory fallback
        _violation_notification_cache[user_uuid] = datetime.utcnow()
        try:
            from shared.database import db_service
            await db_service.mark_user_violations_notified(user_uuid)
        except Exception as e:  # noqa: BLE001
            # кулдаун переживает рестарт только через БД: молчаливый провал =
            # дубли уведомлений после перезапуска
            logger.warning("Failed to persist violation cooldown for %s: %s", user_uuid, e)

        logger.info(
            "Violation notification sent: user_uuid=%s score=%.1f ip_count=%d",
            user_uuid, total_score, ip_count,
        )

    except Exception:
        logger.exception("Failed to send violation notification for user %s", user_uuid)


async def send_torrent_notification(
    user_uuid: str,
    user_info: Optional[dict] = None,
    torrent_events: Optional[list] = None,
    destinations: Optional[List[str]] = None,
    ips: Optional[List[str]] = None,
    node_name: Optional[str] = None,
    window: Optional[Dict] = None,
    action: str = "notify",
) -> None:
    """Send torrent-specific Telegram notification.

    ``node_name`` — нода, с которой пришёл батч: торрент видит агент на
    конкретной ноде, и админу важно знать, на какой.
    ``window`` — счёт за окно, по которому сработали пороги: events, peers,
    minutes, min_events, min_peers. ``action`` — что сделано: notify |
    blocked | block_failed.
    """
    now = datetime.utcnow()

    try:
        from shared.config_service import config_service
        cooldown_minutes = config_service.get("torrent_notification_cooldown_minutes", 30)
    except Exception:
        cooldown_minutes = 30

    # Throttle using shared cache
    if user_uuid in _violation_notification_cache:
        last = _violation_notification_cache[user_uuid]
        if now - last < timedelta(minutes=cooldown_minutes):
            logger.info("Torrent notification throttled for user %s (cooldown)", user_uuid)
            return

    _cleanup_cache()

    try:
        info = user_info if user_info else {}
        event_count = len(torrent_events) if torrent_events else 0
        destinations = destinations or []
        window = window or {}
        events = window.get("events", event_count)
        peers_total = max(len(destinations), int(window.get("peers") or 0))

        def counted(value, threshold_key: str):
            threshold = window.get(threshold_key)
            return join(b(str(value)), tr("notify.torrent.threshold", value=threshold) if threshold else None)

        card = Card(tr("notify.torrent.title"), emoji="🚨")
        card.lead(b(info.get("email") or info.get("username", "n/a")), code(node_name) if node_name else None)
        _user_fields(card, user_uuid, info, with_description=False)
        card.fields([
            (tr("notify.torrent.field.ips"), join(*(copy(ip) for ip in (ips or [])[:5]), sep=", ")),
            (tr("notify.torrent.field.window"),
             tr("notify.torrent.window_minutes", minutes=window["minutes"]) if window.get("minutes") else None),
            (tr("notify.torrent.field.events"), counted(events, "min_events")),
            (tr("notify.torrent.field.peers"), counted(peers_total, "min_peers") if peers_total else None),
        ])

        if destinations:
            shown = destinations[:10]
            body = section().bullets([copy(dest) for dest in shown])
            if peers_total > len(shown):
                body.text(i(tr("notify.card.more", count=peers_total - len(shown))))
            card.details(tr("notify.torrent.destinations", count=peers_total), body)

        # Действие — то, что реально сделано по настройке «Авто-действие при
        # торренте», а не рекомендация: раньше тут всегда стояла жёсткая блокировка
        if action in ("blocked", "block_failed"):
            card.quote(b(tr(f"notify.torrent.action.{action}")))
        else:
            card.text(tr("notify.torrent.action.notify"))
        _add_history(card, await _recap(user_uuid))
        # Торрент-событие ловится мимо анализаторов нарушений — белый
        # список нарушений на него не влияет, кнопки там не место.
        card.buttons(*violation_buttons(user_uuid, with_whitelist=False))
        card.stamp(now)

        from web.backend.core.notification_service import create_notification
        await create_notification(
            title=card.title_text(),
            body=card.body_text(),
            type="torrent",
            severity="critical",
            source="collector",
            source_id=user_uuid,
            link=f"/users/{user_uuid}",
            group_key=f"torrent:{user_uuid}",
            channels=["telegram", "in_app", "push"],
            topic_type="violations",
            telegram_card=card,
            event="violation.torrent",
        )

        _violation_notification_cache[user_uuid] = datetime.utcnow()
        try:
            from shared.database import db_service
            await db_service.mark_user_violations_notified(user_uuid)
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to persist torrent cooldown for %s: %s", user_uuid, e)

        logger.info("Torrent notification sent: user=%s events=%d", user_uuid, event_count)

    except Exception:
        logger.exception("Failed to send torrent notification for user %s", user_uuid)
