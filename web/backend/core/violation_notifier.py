"""Violation notification formatter and sender for web backend.

Uses notification_service.create_notification() for multi-channel dispatch
(Telegram, in-app, webhook, email) instead of aiogram Bot instance.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

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


def _esc(text: str) -> str:
    """Escape HTML for Telegram."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _short_provider(asn_org: Optional[str]) -> str:
    """Shorten ASN org name for display."""
    if not asn_org:
        return ""
    if len(asn_org) > 25:
        return asn_org[:22] + "..."
    return asn_org


def _detect_primary_reason(reasons: List[str], breakdown: dict) -> dict:
    """Determine primary violation reason for notification title and subtitle."""
    reasons_lower = " ".join(r.lower() for r in reasons)

    if "двойной туннель" in reasons_lower or "ссылка в user-agent" in reasons_lower or "link_in_ua" in reasons_lower:
        return {
            "title": "Двойной туннель: подписка вставлена в чужой клиент",
            "subtitle": "В User-Agent обнаружена подписочная ссылка (vless://, https://)",
        }
    if "http-библиотека" in reasons_lower or "bot_library" in reasons_lower or "go-http-client" in reasons_lower:
        return {
            "title": "Бот/скрипт в User-Agent",
            "subtitle": "Подписка запрашивается curl/Go-http-client/python-requests — возможно автоматизация",
        }
    if "hwid" in reasons_lower or "device overlap" in reasons_lower:
        return {
            "title": "Коллизия аккаунтов: общие устройства (device overlap)",
            "subtitle": "Несколько аккаунтов используют одни и те же HWID",
        }
    if "torrent" in reasons_lower or "p2p" in reasons_lower:
        return {
            "title": "Обнаружен торрент-трафик (P2P)",
            "subtitle": "Пользователь использует торрент через VPN",
        }
    if "impossible travel" in reasons_lower or "geo" in reasons_lower:
        return {
            "title": "Невозможное перемещение (geo anomaly)",
            "subtitle": "Подключения из географически несовместимых локаций",
        }
    if "simultaneous" in reasons_lower or "temporal" in reasons_lower:
        return {
            "title": "Превышение лимита подключений (simultaneous)",
            "subtitle": "Слишком много одновременных подключений с разных IP",
        }
    if "datacenter" in reasons_lower or "vpn" in reasons_lower or "proxy" in reasons_lower:
        return {
            "title": "Подозрительный провайдер (ASN anomaly)",
            "subtitle": "Подключение через VPN/прокси/датацентр",
        }
    if "traffic" in reasons_lower or "bandwidth" in reasons_lower:
        return {
            "title": "Чрезмерное потребление трафика",
            "subtitle": "Пользователь превысил порог скорости потребления",
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
        labels = {
            "temporal": "Временная аномалия подключений",
            "geo": "Географическая аномалия",
            "asn": "Аномалия провайдера",
            "profile": "Отклонение профиля поведения",
            "device": "Аномалия устройств",
            "user_agent": "Подозрительный User-Agent клиента",
        }
        if max_key:
            return {
                "title": labels.get(max_key, f"Нарушение ({max_key})"),
                "subtitle": f"Анализатор {max_key} обнаружил аномалию (скор: {max_score:.0f})",
            }

    return {
        "title": "Обнаружено нарушение",
        "subtitle": "Система обнаружила подозрительную активность",
    }


def _violation_keyboard(user_uuid: str) -> Dict:
    """Build inline keyboard with quick actions for violation notifications."""
    return {
        "inline_keyboard": [
            [
                {"text": "👤 Подробнее", "callback_data": f"vact:info:{user_uuid}"},
                {"text": "🔒 Заблокировать", "callback_data": f"vact:block:{user_uuid}"},
            ],
            [
                {"text": "⛔ Откл + разорвать", "callback_data": f"vact:kill:{user_uuid}"},
                {"text": "🔄 Сбросить трафик", "callback_data": f"vact:reset:{user_uuid}"},
            ],
            [
                {"text": "🚫 Аннулировать", "callback_data": f"vact:dismiss:{user_uuid}"},
            ],
        ]
    }


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
                logger.info("Violation notification throttled for user %s (cooldown)", user_uuid)
                return

        # DB check (persistent across restarts)
        try:
            from shared.database import db_service
            last_notified = await db_service.get_user_last_violation_notification(user_uuid)
            if last_notified and now - last_notified < timedelta(minutes=cooldown_minutes):
                logger.info("Violation notification throttled for user %s (DB cooldown)", user_uuid)
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
        email = info.get("email", "")
        telegram_id = info.get("telegramId")
        description = info.get("description", "")
        device_limit = info.get("hwidDeviceLimit", 1)
        if device_limit == 0:
            device_limit = "\u221e"

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

        # Moscow time (UTC+3)
        moscow_time = now + timedelta(hours=3)
        moscow_time_str = moscow_time.strftime("%d.%m.%Y %H:%M:%S")

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

        # Build message — determine primary violation reason for title
        reasons = violation_score.get("reasons", [])
        primary_reason = _detect_primary_reason(reasons, breakdown)
        title_text = primary_reason["title"]
        subtitle_text = primary_reason["subtitle"]

        lines = [
            f"\u26a0\ufe0f <b>{_esc(title_text)}</b>",
            "",
            f"\U0001f4a1 {_esc(subtitle_text)}",
            "",
        ]

        if email:
            lines.append(f"\U0001f4e7 Email: <code>{_esc(email)}</code>")
        else:
            lines.append(f"\U0001f4e7 Username: <code>{_esc(username)}</code>")

        if telegram_id is not None:
            lines.append(f"\U0001f4f1 TG ID: <code>{telegram_id}</code>")

        if description:
            lines.append(f"\U0001f4dd Описание: <code>{_esc(description[:100])}</code>")

        lines.append("")
        lines.append(f"\U0001f310 IP адресов: <b>{ip_count} из {device_limit}</b>")

        if unique_ips:
            lines.append("\U0001f4cd IP (провайдеры):")
            for ip in sorted(unique_ips):
                provider_info = ""
                country_code = ""
                if ip_metadata and ip in ip_metadata:
                    meta = ip_metadata[ip]
                    if hasattr(meta, "asn_org") and meta.asn_org:
                        provider_info = _short_provider(meta.asn_org)
                    if hasattr(meta, "country_code") and meta.country_code:
                        country_code = meta.country_code

                suffix = ""
                if provider_info:
                    suffix = f" — {_esc(provider_info)}"
                if country_code:
                    suffix += f" ({country_code})"
                lines.append(f"   <code>{ip}</code>{suffix}")

        if nodes_used:
            nodes_str = ", ".join(sorted(nodes_used))
            lines.append(f"\U0001f5a5 Ноды: <code>{_esc(nodes_str)}</code>")

        lines.append("")

        # HWID devices
        hwid_devices = []
        try:
            from shared.database import db_service
            hwid_devices = await db_service.get_user_hwid_devices(user_uuid)
        except Exception:
            pass

        if hwid_devices:
            hwid_count = len(hwid_devices)
            device_parts = []
            platform_names = {
                "android": "Android", "ios": "iOS", "windows": "Windows",
                "macos": "macOS", "linux": "Linux",
            }
            for device in hwid_devices[:5]:
                platform = device.get("platform", "unknown")
                os_version = device.get("os_version", "")
                app_version = device.get("app_version", "")
                platform_display = platform_names.get(platform.lower(), platform) if platform else "Unknown"
                device_str = platform_display
                if os_version:
                    device_str += f" {os_version}"
                if app_version:
                    device_str += f" (v{app_version})"
                device_parts.append(device_str)
            if hwid_count > 5:
                device_parts.append(f"... и ещё {hwid_count - 5}")
            lines.append(f"\U0001f4f2 Всего устройств в аккаунте: <b>{hwid_count} из {device_limit}</b>")
            lines.append(f"(перечисление: {', '.join(_esc(p) for p in device_parts)})")
        elif os_list or client_list:
            device_parts = []
            if os_list and client_list and len(os_list) == len(client_list):
                for i, os_name in enumerate(os_list):
                    client_name = client_list[i] if i < len(client_list) else ""
                    if client_name:
                        device_parts.append(f"{os_name} ({client_name})")
                    else:
                        device_parts.append(os_name)
            else:
                if os_list:
                    device_parts.append(f"ОС: {', '.join(os_list)}")
                if client_list:
                    device_parts.append(f"Клиенты: {', '.join(client_list)}")
            if device_parts:
                lines.append(f"\U0001f4f2 Устройства (по UA): {'; '.join(device_parts)}")
            else:
                lines.append("\U0001f4f2 Устройства: \u2014")
        else:
            lines.append("\U0001f4f2 Устройства: \u2014")

        # Reasons (deduplicated) — as "Детали пересечения"
        if reasons:
            seen = set()
            unique_reasons = []
            for r in reasons:
                if r not in seen:
                    seen.add(r)
                    unique_reasons.append(r)
            lines.append("")
            lines.append("\U0001f50e Детали пересечения:")
            for r in unique_reasons[:8]:
                lines.append(f"   \u2022 {_esc(r)}")
            if len(unique_reasons) > 8:
                lines.append(f"   ... и ещё {len(unique_reasons) - 8}")

        # Recommended action
        action = violation_score.get("recommended_action", "")
        action_labels = {
            "no_action": "без действий",
            "monitor": "мониторинг",
            "warn": "предупреждение",
            "soft_block": "мягкая блокировка",
            "temp_block": "временная блокировка",
            "hard_block": "жёсткая блокировка",
        }
        action_key = action.value if hasattr(action, "value") else str(action)
        action_label = action_labels.get(action_key, action_key)
        lines.append("")
        lines.append(f"\U0001f3af Действие: <b>{action_label.upper()}</b> ({action_label})")
        lines.append(f"\U0001f4ca Скор: <b>{total_score:.1f}</b> / 100")
        lines.append(f"\U0001f550 Время (МСК): {moscow_time_str}")

        body = "\n".join(lines)

        # Plain text body for in-app notifications (strip HTML tags)
        import re
        plain_body = re.sub(r'<[^>]+>', '', body)

        # Send via notification_service
        from web.backend.core.notification_service import create_notification

        await create_notification(
            title=title_text,
            body=plain_body,
            type="violation",
            severity="warning" if total_score < 80 else "critical",
            source="collector",
            source_id=user_uuid,
            group_key=f"violation:{user_uuid}",
            channels=["telegram", "in_app", "push"],
            topic_type="violations",
            telegram_body=body,
            reply_markup=_violation_keyboard(user_uuid),
        )

        # Update throttling: persistent DB + in-memory fallback
        _violation_notification_cache[user_uuid] = datetime.utcnow()
        try:
            from shared.database import db_service
            await db_service.mark_user_violations_notified(user_uuid)
        except Exception:
            pass  # In-memory cache is already updated

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
) -> None:
    """Send torrent-specific Telegram notification."""
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
        username = info.get("username", "n/a")
        email = info.get("email", "")
        telegram_id = info.get("telegramId")

        moscow_time = now + timedelta(hours=3)
        moscow_time_str = moscow_time.strftime("%d.%m.%Y %H:%M:%S")

        event_count = len(torrent_events) if torrent_events else 0

        lines = [
            "\U0001f6a8 <b>\u0422\u041e\u0420\u0420\u0415\u041d\u0422 \u0422\u0420\u0410\u0424\u0418\u041a \u041e\u0411\u041d\u0410\u0420\u0423\u0416\u0415\u041d</b>",
            "",
        ]

        if email:
            lines.append(f"\U0001f4e7 Email: <code>{_esc(email)}</code>")
        else:
            lines.append(f"\U0001f4e7 Username: <code>{_esc(username)}</code>")

        if telegram_id is not None:
            lines.append(f"\U0001f4f1 TG ID: <code>{telegram_id}</code>")

        lines.append("")
        lines.append(f"\U0001f4ca \u0421\u043e\u0431\u044b\u0442\u0438\u0439: <b>{event_count}</b>")

        if destinations:
            lines.append(f"\U0001f310 \u041d\u0430\u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f:")
            for dest in destinations[:10]:
                lines.append(f"   <code>{_esc(dest)}</code>")
            if len(destinations) > 10:
                lines.append(f"   ... \u0438 \u0435\u0449\u0451 {len(destinations) - 10}")

        if ips:
            lines.append(f"\U0001f4cd IP: {', '.join(f'<code>{ip}</code>' for ip in ips[:5])}")

        lines.append("")
        lines.append(f"\U0001f6d1 \u0414\u0435\u0439\u0441\u0442\u0432\u0438\u0435: <b>\u0416\u0451\u0441\u0442\u043a\u0430\u044f \u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u043a\u0430</b>")
        lines.append(f"\U0001f550 \u0412\u0440\u0435\u043c\u044f (\u041c\u0421\u041a): <code>{moscow_time_str}</code>")

        body = "\n".join(lines)

        import re
        plain_body = re.sub(r'<[^>]+>', '', body)

        from web.backend.core.notification_service import create_notification
        await create_notification(
            title="Торрент трафик обнаружен",
            body=plain_body,
            type="torrent",
            severity="critical",
            source="collector",
            source_id=user_uuid,
            group_key=f"torrent:{user_uuid}",
            channels=["telegram", "in_app", "push"],
            topic_type="violations",
            telegram_body=body,
            reply_markup=_violation_keyboard(user_uuid),
        )

        _violation_notification_cache[user_uuid] = datetime.utcnow()
        try:
            from shared.database import db_service
            await db_service.mark_user_violations_notified(user_uuid)
        except Exception:
            pass

        logger.info("Torrent notification sent: user=%s events=%d", user_uuid, event_count)

    except Exception:
        logger.exception("Failed to send torrent notification for user %s", user_uuid)
