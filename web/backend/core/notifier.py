"""Lightweight Telegram notifier for the web backend.

Sends messages directly via Telegram Bot API using httpx,
without depending on the aiogram Bot instance from the main bot process.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from web.backend.core.config import get_web_settings

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org"


async def _send_telegram_message(text: str, topic_id: Optional[int] = None) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    settings = get_web_settings()
    bot_token = settings.telegram_bot_token

    # Get chat_id from settings (reads .env via pydantic_settings)
    chat_id = settings.notifications_chat_id
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return False

    # Get service topic from settings
    if topic_id is None:
        topic_id_str = settings.notifications_topic_service or settings.notifications_topic_id
        if topic_id_str:
            try:
                topic_id = int(topic_id_str)
            except (ValueError, TypeError):
                pass

    url = f"{_TELEGRAM_API}/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
    }
    if topic_id is not None:
        payload["message_thread_id"] = topic_id

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                logger.debug("Telegram notification sent successfully")
                return True
            else:
                logger.warning("Telegram API error %d: %s", resp.status_code, resp.text[:200])
                return False
    except Exception as e:
        logger.warning("Failed to send Telegram notification: %s", e)
        return False


def _esc(text: str) -> str:
    """Escape HTML special characters for Telegram."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _now_str() -> str:
    """Get current UTC time as a formatted string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


async def notify_login_failed(
    ip: str,
    username: str,
    auth_method: str,
    reason: str = "",
    failures_count: int = 0,
) -> None:
    """Send notification about a failed login attempt (fire-and-forget)."""
    lines = [
        "<b>Failed login attempt</b>",
        "",
        f"<b>IP:</b> <code>{_esc(ip)}</code>",
        f"<b>Username:</b> <code>{_esc(username)}</code>",
        f"<b>Method:</b> {_esc(auth_method)}",
    ]
    if reason:
        lines.append(f"<b>Reason:</b> {_esc(reason)}")
    if failures_count > 0:
        lines.append(f"<b>Consecutive failures:</b> {failures_count}")
    lines.append(f"<b>Time:</b> {_now_str()}")

    text = "\n".join(lines)
    asyncio.create_task(_send_telegram_message(text))


async def notify_login_success(
    ip: str,
    username: str,
    auth_method: str,
) -> None:
    """Send notification about a successful login."""
    lines = [
        "<b>Admin login</b>",
        "",
        f"<b>IP:</b> <code>{_esc(ip)}</code>",
        f"<b>Username:</b> <code>{_esc(username)}</code>",
        f"<b>Method:</b> {_esc(auth_method)}",
        f"<b>Time:</b> {_now_str()}",
    ]

    text = "\n".join(lines)
    asyncio.create_task(_send_telegram_message(text))


async def notify_ip_blocked(ip: str, lockout_seconds: int, failures: int) -> None:
    """Send notification when an IP is locked out due to brute-force."""
    lines = [
        "<b>IP locked out (brute-force)</b>",
        "",
        f"<b>IP:</b> <code>{_esc(ip)}</code>",
        f"<b>Failed attempts:</b> {failures}",
        f"<b>Lockout:</b> {lockout_seconds // 60} min",
        f"<b>Time:</b> {_now_str()}",
    ]

    text = "\n".join(lines)
    asyncio.create_task(_send_telegram_message(text))


async def notify_ip_rejected(ip: str, path: str) -> None:
    """Send notification when a request is rejected by IP whitelist."""
    lines = [
        "<b>Access denied (IP whitelist)</b>",
        "",
        f"<b>IP:</b> <code>{_esc(ip)}</code>",
        f"<b>Path:</b> <code>{_esc(path[:100])}</code>",
        f"<b>Time:</b> {_now_str()}",
    ]

    text = "\n".join(lines)
    asyncio.create_task(_send_telegram_message(text))
