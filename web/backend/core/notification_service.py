"""Notification delivery service — sends via in-app, Telegram, Webhook, Email."""
import asyncio
import json
import logging
import smtplib
import ssl
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


def _get_global_telegram_config(topic_type: str = "service") -> tuple:
    """Return (bot_token, chat_id, topic_id) from global settings.

    ``topic_type`` selects the Telegram topic: "nodes", "service",
    "users", "errors", "violations", etc.  Falls back to the general
    NOTIFICATIONS_TOPIC_ID when a per-type topic is not configured.
    """
    try:
        from web.backend.core.config import get_web_settings
        settings = get_web_settings()
        bot_token = settings.telegram_bot_token or None
        chat_id = settings.notifications_chat_id or None
        topic_id = settings.get_topic_for(topic_type)
        return bot_token, chat_id, topic_id
    except Exception:
        return None, None, None


# ── Email (SMTP) ─────────────────────────────────────────────────

async def _get_smtp_config() -> Optional[Dict[str, Any]]:
    """Load SMTP config from DB."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM smtp_config WHERE is_enabled = true ORDER BY id LIMIT 1"
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to load SMTP config: %s", e)
        return None


def _build_html_email(title: str, body: str, severity: str = "info", link: Optional[str] = None) -> str:
    """Build HTML email template."""
    severity_colors = {
        "info": "#22d3ee",
        "warning": "#f59e0b",
        "critical": "#ef4444",
        "success": "#22c55e",
    }
    color = severity_colors.get(severity, "#22d3ee")

    link_html = ""
    if link:
        link_html = f'<p style="margin-top:16px"><a href="{link}" style="color:{color};text-decoration:underline">Open in panel</a></p>'

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0f1729;font-family:Arial,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#0f1729;padding:32px 16px">
<tr><td align="center">
<table width="560" cellpadding="0" cellspacing="0" style="background:#1a2332;border-radius:12px;border:1px solid #2a3a4a">
<tr><td style="padding:24px 32px;border-bottom:2px solid {color}">
    <h2 style="margin:0;color:#e2e8f0;font-size:18px">{title}</h2>
</td></tr>
<tr><td style="padding:24px 32px;color:#94a3b8;font-size:14px;line-height:1.6">
    <p style="margin:0">{body}</p>
    {link_html}
</td></tr>
<tr><td style="padding:16px 32px;border-top:1px solid #2a3a4a;color:#64748b;font-size:12px">
    Remnawave Admin &middot; {datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")}
</td></tr>
</table>
</td></tr>
</table>
</body>
</html>"""


async def send_email(
    to_email: str,
    title: str,
    body: str,
    severity: str = "info",
    link: Optional[str] = None,
) -> bool:
    """Send email via built-in mail server or SMTP relay.

    Tries the built-in mail server first (if an active outbound domain exists),
    then falls back to the configured SMTP relay.
    """
    # Try built-in mail server first
    try:
        from web.backend.core.mail.mail_service import mail_service
        domain = await mail_service.get_active_outbound_domain()
        if domain:
            html = _build_html_email(title, body, severity, link)
            queue_id = await mail_service.send_email(
                to_email=to_email,
                subject=f"[Remnawave] {title}",
                body_text=body,
                body_html=html,
                category="notification",
            )
            if queue_id:
                logger.info("Email queued via built-in mail server: id=%s to=%s", queue_id, to_email)
                return True
    except Exception as e:
        logger.debug("Built-in mail server unavailable, falling back to SMTP relay: %s", e)

    # Fallback to SMTP relay
    config = await _get_smtp_config()
    if not config:
        logger.warning("SMTP not configured or disabled, skipping email to %s", to_email)
        return False

    html = _build_html_email(title, body, severity, link)

    def _send():
        msg = MIMEMultipart("alternative")
        msg["Subject"] = title
        from_name = config.get("from_name")
        if from_name:
            msg["From"] = f"{from_name} <{config['from_email']}>"
        else:
            msg["From"] = config["from_email"]
        msg["To"] = to_email

        msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html, "html", "utf-8"))

        try:
            if config.get("use_ssl"):
                ctx = ssl.create_default_context()
                server = smtplib.SMTP_SSL(config["host"], config["port"], context=ctx, timeout=15)
            else:
                server = smtplib.SMTP(config["host"], config["port"], timeout=15)
                if config.get("use_tls"):
                    ctx = ssl.create_default_context()
                    server.starttls(context=ctx)

            if config.get("username") and config.get("password"):
                server.login(config["username"], config["password"])

            server.sendmail(config["from_email"], [to_email], msg.as_string())
            server.quit()
            return True
        except Exception as e:
            logger.error("SMTP send failed to %s: %s", to_email, e)
            return False

    try:
        return await asyncio.get_event_loop().run_in_executor(None, _send)
    except Exception as e:
        logger.error("Email send error: %s", e)
        return False


async def test_smtp(to_email: str) -> Dict[str, Any]:
    """Send a test email to verify SMTP settings."""
    ok = await send_email(
        to_email=to_email,
        title="SMTP Test",
        body="This is a test email from Remnawave Admin. If you see this, SMTP is configured correctly.",
        severity="info",
    )
    return {"success": ok, "to": to_email}


# ── Telegram ─────────────────────────────────────────────────────

async def send_telegram(
    chat_id: str,
    title: str,
    body: str,
    topic_id: Optional[str] = None,
    bot_token: Optional[str] = None,
) -> bool:
    """Send notification to Telegram chat/group.

    Uses the provided bot_token, or falls back to the global BOT_TOKEN from settings.
    """
    try:
        if not bot_token:
            from web.backend.core.config import get_web_settings
            settings = get_web_settings()
            bot_token = settings.telegram_bot_token
        if not bot_token:
            logger.warning("No Telegram bot token configured, skipping send to %s", chat_id)
            return False

        text = f"<b>{title}</b>\n\n{body}"
        payload: Dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if topic_id and str(topic_id) != "0":
            payload["message_thread_id"] = int(topic_id)

        logger.debug("Sending Telegram notification to chat_id=%s", chat_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload,
            )
            if resp.status_code == 200:
                logger.info("Telegram notification sent to chat_id=%s", chat_id)
                return True
            logger.error("Telegram send failed (chat_id=%s): %s %s", chat_id, resp.status_code, resp.text)
            return False
    except Exception as e:
        logger.error("Telegram notification error (chat_id=%s): %s", chat_id, e)
        return False


# ── Webhook ──────────────────────────────────────────────────────

async def send_webhook(
    url: str,
    title: str,
    body: str,
    severity: str = "info",
    extra: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send notification to a webhook URL (Discord, Slack compatible)."""
    payload = {
        "title": title,
        "body": body,
        "severity": severity,
        "timestamp": datetime.utcnow().isoformat(),
        "source": "remnawave-admin",
        **(extra or {}),
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Try to detect Discord webhook
            if "discord.com/api/webhooks" in url:
                discord_payload = {
                    "embeds": [{
                        "title": title,
                        "description": body,
                        "color": {"info": 0x22d3ee, "warning": 0xf59e0b, "critical": 0xef4444}.get(severity, 0x22d3ee),
                        "timestamp": datetime.utcnow().isoformat(),
                        "footer": {"text": "Remnawave Admin"},
                    }]
                }
                resp = await client.post(url, json=discord_payload)
            # Slack webhook
            elif "hooks.slack.com" in url:
                slack_payload = {
                    "text": f"*{title}*\n{body}",
                    "attachments": [{
                        "color": {"info": "#22d3ee", "warning": "#f59e0b", "critical": "#ef4444"}.get(severity, "#22d3ee"),
                        "text": body,
                    }]
                }
                resp = await client.post(url, json=slack_payload)
            else:
                resp = await client.post(url, json=payload)

            if resp.status_code < 300:
                return True
            logger.error("Webhook send failed: %s %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        logger.error("Webhook notification error: %s", e)
        return False


# ── Unified dispatch ─────────────────────────────────────────────

async def create_notification(
    title: str,
    body: str,
    type: str = "info",
    severity: str = "info",
    admin_id: Optional[int] = None,
    link: Optional[str] = None,
    source: Optional[str] = None,
    source_id: Optional[str] = None,
    group_key: Optional[str] = None,
    channels: Optional[List[str]] = None,
    topic_type: str = "service",
) -> Optional[int]:
    """Create in-app notification and dispatch to configured channels.

    If admin_id is None, creates notification for all admins.
    ``topic_type`` controls which Telegram topic the global fallback
    message is sent to ("nodes", "service", "users", "errors", …).
    Returns the notification ID.
    """
    channels = channels or ["in_app"]
    notification_id = None

    try:
        from src.services.database import db_service

        if admin_id is not None:
            # Single admin
            async with db_service.acquire() as conn:
                # Deduplication: skip if same group_key exists within last 5 min
                if group_key:
                    existing = await conn.fetchval(
                        "SELECT id FROM notifications WHERE admin_id = $1 AND group_key = $2 "
                        "AND created_at > NOW() - INTERVAL '5 minutes'",
                        admin_id, group_key,
                    )
                    if existing:
                        logger.debug("Skipping duplicate notification (group_key=%s)", group_key)
                        return existing

                notification_id = await conn.fetchval(
                    "INSERT INTO notifications (admin_id, type, severity, title, body, link, source, source_id, group_key) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
                    admin_id, type, severity, title, body, link, source, source_id, group_key,
                )
        else:
            # Broadcast to all admins
            async with db_service.acquire() as conn:
                admin_ids = await conn.fetch("SELECT id FROM admin_accounts WHERE is_active = true")
                for row in admin_ids:
                    aid = row["id"]
                    nid = await conn.fetchval(
                        "INSERT INTO notifications (admin_id, type, severity, title, body, link, source, source_id, group_key) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
                        aid, type, severity, title, body, link, source, source_id, group_key,
                    )
                    if notification_id is None:
                        notification_id = nid

        # Broadcast via WebSocket
        try:
            from web.backend.api.v2.websocket import manager
            await manager.broadcast({
                "type": "notification",
                "data": {
                    "id": notification_id,
                    "title": title,
                    "body": body,
                    "severity": severity,
                    "notification_type": type,
                    "admin_id": admin_id,
                    "link": link,
                },
                "timestamp": datetime.utcnow().isoformat(),
            })
        except Exception as e:
            logger.warning("WebSocket broadcast failed: %s", e)

        # Dispatch to external channels (per-admin configured channels)
        if admin_id is not None:
            asyncio.create_task(_dispatch_external(admin_id, title, body, severity, link, channels))
            # We can't easily track what was dispatched in the async task,
            # but we still send to global fallback below for broadcast safety
        else:
            # For broadcasts, dispatch to all admins' external channels
            try:
                async with db_service.acquire() as conn:
                    admin_ids_rows = await conn.fetch("SELECT id FROM admin_accounts WHERE is_active = true")

                if admin_ids_rows:
                    logger.debug("Broadcasting external channels to %d admin accounts", len(admin_ids_rows))
                    for row in admin_ids_rows:
                        asyncio.create_task(
                            _dispatch_external(row["id"], title, body, severity, link, channels)
                        )
                else:
                    logger.debug("No admin_accounts found for external dispatch")
            except Exception as e:
                logger.error("Failed to dispatch to admin channels: %s", e)

        # Global channel fallback: send to NOTIFICATIONS_CHAT_ID for Telegram
        # This ensures alerts reach the configured Telegram chat even if
        # no per-admin Telegram channel is set up.
        # topic_type routes the message to the correct Telegram topic
        # (e.g. "nodes" → NOTIFICATIONS_TOPIC_NODES)
        if "telegram" in channels or "all" in channels:
            asyncio.create_task(
                _send_to_global_telegram(title, body, severity, topic_type)
            )

    except Exception as e:
        logger.error("Failed to create notification: %s", e)

    return notification_id


async def _send_to_global_telegram(title: str, body: str, severity: str, topic_type: str = "service"):
    """Send notification to the global NOTIFICATIONS_CHAT_ID.

    ``topic_type`` selects the Telegram topic ("nodes", "service", etc.).
    """
    try:
        bot_token, chat_id, topic_id = _get_global_telegram_config(topic_type)
        if not chat_id or not bot_token:
            logger.debug("No global NOTIFICATIONS_CHAT_ID configured, skipping global Telegram dispatch")
            return

        severity_emoji = {"info": "\u2139\ufe0f", "warning": "\u26a0\ufe0f", "critical": "\ud83d\udea8", "success": "\u2705"}.get(severity, "")
        full_title = f"{severity_emoji} {title}" if severity_emoji else title

        ok = await send_telegram(chat_id, full_title, body, topic_id, bot_token)
        if ok:
            logger.info("Global Telegram notification sent to chat_id=%s", chat_id)
        else:
            logger.warning("Global Telegram notification failed for chat_id=%s", chat_id)
    except Exception as e:
        logger.error("Global Telegram dispatch error: %s", e)


async def _dispatch_external(
    admin_id: int,
    title: str,
    body: str,
    severity: str,
    link: Optional[str],
    requested_channels: List[str],
):
    """Dispatch notification to external channels based on admin's channel config."""
    try:
        from src.services.database import db_service
        async with db_service.acquire() as conn:
            channels = await conn.fetch(
                "SELECT channel_type, config FROM notification_channels "
                "WHERE admin_id = $1 AND is_enabled = true",
                admin_id,
            )

        if not channels:
            logger.debug(
                "No enabled notification_channels found for admin_id=%s (requested: %s)",
                admin_id, requested_channels,
            )
            return

        for ch in channels:
            ch_type = ch["channel_type"]
            config = ch["config"] if isinstance(ch["config"], dict) else json.loads(ch["config"] or "{}")

            # Skip channels not in the requested list
            if ch_type not in requested_channels and "all" not in requested_channels:
                logger.debug("Skipping channel %s for admin %s (not in requested: %s)", ch_type, admin_id, requested_channels)
                continue

            try:
                if ch_type == "telegram":
                    chat_id = config.get("chat_id")
                    topic_id = config.get("topic_id")
                    bot_token_override = config.get("bot_token")
                    if chat_id:
                        logger.info("Dispatching Telegram to chat_id=%s for admin_id=%s", chat_id, admin_id)
                        await send_telegram(chat_id, title, body, topic_id, bot_token_override)
                    else:
                        logger.warning("Telegram channel for admin %s has no chat_id in config: %s", admin_id, config)

                elif ch_type == "webhook":
                    url = config.get("url")
                    if url:
                        logger.info("Dispatching webhook to %s for admin_id=%s", url[:60], admin_id)
                        await send_webhook(url, title, body, severity)
                    else:
                        logger.warning("Webhook channel for admin %s has no url in config", admin_id)

                elif ch_type == "email":
                    email = config.get("email")
                    if email:
                        logger.info("Dispatching email to %s for admin_id=%s", email, admin_id)
                        await send_email(email, title, body, severity, link)
                    else:
                        logger.warning("Email channel for admin %s has no email in config", admin_id)
            except Exception as e:
                logger.error("Channel dispatch error (%s, admin=%s): %s", ch_type, admin_id, e)

    except Exception as e:
        logger.error("External dispatch failed for admin %s: %s", admin_id, e)
