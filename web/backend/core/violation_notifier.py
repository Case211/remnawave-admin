"""Violation notification formatter and sender for web backend.

Uses notification_service.create_notification() for multi-channel dispatch
(Telegram, in-app, webhook, email) instead of aiogram Bot instance.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Fallback in-memory cache when DB check fails
_violation_notification_cache: Dict[str, datetime] = {}


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
    from shared.config_service import config_service
    cooldown_minutes = config_service.get("violation_notification_cooldown_minutes", 30)

    # Throttling: DB-based (persistent across restarts), in-memory fallback
    if not force:
        try:
            from shared.database import db_service
            last_notified = await db_service.get_user_last_violation_notification(user_uuid)
            if last_notified and now - last_notified < timedelta(minutes=cooldown_minutes):
                logger.debug("Violation notification throttled for user %s (DB: last=%s)", user_uuid, last_notified)
                return
        except Exception:
            # Fallback to in-memory cache
            if user_uuid in _violation_notification_cache:
                last = _violation_notification_cache[user_uuid]
                if now - last < timedelta(minutes=cooldown_minutes):
                    logger.debug("Violation notification throttled for user %s (memory)", user_uuid)
                    return

    try:
        # User info
        if not user_info:
            from shared.database import db_service
            user_info = await db_service.get_user_by_uuid(user_uuid)

        info = user_info.get("response", user_info) if user_info else {}
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
                    node_uuids.add(conn.node_uuid)

        # Resolve node names
        nodes_used = set()
        if node_uuids:
            try:
                from shared.database import db_service
                for node_uuid in node_uuids:
                    node_info = await db_service.get_node_by_uuid(node_uuid)
                    if node_info and node_info.get("name"):
                        nodes_used.add(node_info.get("name"))
                    else:
                        nodes_used.add(node_uuid[:8])
            except Exception:
                nodes_used = {uuid[:8] for uuid in node_uuids}

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

        # Build message
        lines = [
            "\U0001f6a8 <b>НАРУШИТЕЛЬ ЛИМИТА</b>",
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
        lines.append(f"\U0001f310 IP адресов: <b>{ip_count}/{device_limit}</b>")

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

                if provider_info or country_code:
                    suffix = ""
                    if provider_info:
                        suffix = f" - {_esc(provider_info)}"
                    if country_code:
                        suffix += f" ({country_code})"
                    lines.append(f"   <code>{ip}</code>{suffix}")
                else:
                    lines.append(f"   <code>{ip}</code>")

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
            lines.append(f"\U0001f4f2 Устройства ({hwid_count}/{device_limit}):")
            for part in device_parts:
                lines.append(f"   {_esc(part)}")
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

        lines.append(f"\U0001f4ca Скор: <code>{total_score:.1f}/100</code>")
        lines.append(f"\U0001f550 Время (МСК): <code>{moscow_time_str}</code>")

        body = "\n".join(lines)

        # Send via notification_service
        from web.backend.core.notification_service import create_notification

        await create_notification(
            title="Нарушение лимита устройств",
            body=body,
            type="violation",
            severity="warning" if total_score < 80 else "critical",
            source="collector",
            source_id=user_uuid,
            group_key=f"violation:{user_uuid}",
            channels=["telegram", "in_app"],
            topic_type="violations",
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
