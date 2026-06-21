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

from shared.metrics import NOTIFICATIONS_FAILED, NOTIFICATIONS_SENT
from shared.db_schema import (
    ADMIN_TABLE,
    SMTP_CONFIG_TABLE,
    NOTIFICATIONS_TABLE,
    NOTIFICATION_CHANNELS_TABLE,
    NOTIFICATION_CHANNEL_CONFIGS_TABLE,
)
from shared.db_query import select_sql, insert_sql

logger = logging.getLogger(__name__)

# Предупреждаем об отсутствии глобального Telegram-чата один раз за процесс (иначе спам в debug).
_warned_no_global_chat = False


def _get_global_telegram_config(topic_type: str = "service") -> tuple:
    """Return (bot_token, chat_id, topic_id) from global settings.

    ``topic_type`` selects the Telegram topic: "nodes", "service",
    "users", "errors", "violations", etc.  Falls back to the general
    NOTIFICATIONS_TOPIC_ID when a per-type topic is not configured.

    Topic IDs are read from config_service (DB > .env > default) so that
    changes made via the Settings UI take effect without a restart.
    """
    try:
        from web.backend.core.config import get_web_settings
        settings = get_web_settings()
        bot_token = settings.telegram_bot_token or None

        # Read chat_id and topics from config_service (DB-first, .env fallback)
        from shared.config_service import config_service
        chat_id = config_service.get("notifications_chat_id") or settings.notifications_chat_id
        chat_id = str(chat_id) if chat_id else None

        topic_key = f"notifications_topic_{topic_type}"
        topic_id = config_service.get(topic_key)
        if topic_id is None:
            topic_id = config_service.get("notifications_topic_id")
        # Final fallback to .env via pydantic settings
        if topic_id is None:
            topic_id = settings.get_topic_for(topic_type)
        topic_id = str(topic_id) if topic_id else None

        return bot_token, chat_id, topic_id
    except Exception as e:
        logger.debug("Telegram config not available: %s", e)
        return None, None, None


# ── Email (SMTP) ─────────────────────────────────────────────────

async def _get_smtp_config() -> Optional[Dict[str, Any]]:
    """Load SMTP config from DB."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(SMTP_CONFIG_TABLE, "*", "WHERE is_enabled = true ORDER BY id LIMIT 1")
            )
            return dict(row) if row else None
    except Exception as e:
        logger.error("Failed to load SMTP config: %s", e, exc_info=True)
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
                NOTIFICATIONS_SENT.labels(channel="email").inc()
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
            # Use from_email domain as EHLO hostname to avoid sending
            # the Docker container ID (e.g. "cfe04705b6d4") in HELO.
            from_domain = config["from_email"].split("@")[-1] if "@" in config.get("from_email", "") else None
            if config.get("use_ssl"):
                ctx = ssl.create_default_context()
                server = smtplib.SMTP_SSL(config["host"], config["port"], context=ctx, timeout=15,
                                          local_hostname=from_domain)
            else:
                server = smtplib.SMTP(config["host"], config["port"], timeout=15,
                                      local_hostname=from_domain)
                if config.get("use_tls"):
                    ctx = ssl.create_default_context()
                    server.starttls(context=ctx)

            if config.get("username") and config.get("password"):
                server.login(config["username"], config["password"])

            server.sendmail(config["from_email"], [to_email], msg.as_string())
            server.quit()
            return True
        except Exception as e:
            logger.error("SMTP send failed to %s: %s", to_email, e, exc_info=True)
            return False

    try:
        ok = await asyncio.get_event_loop().run_in_executor(None, _send)
        if ok:
            NOTIFICATIONS_SENT.labels(channel="email").inc()
        else:
            NOTIFICATIONS_FAILED.labels(channel="email").inc()
        return ok
    except Exception as e:
        logger.error("Email send error: %s", e, exc_info=True)
        NOTIFICATIONS_FAILED.labels(channel="email").inc()
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

async def _send_telegram_via_bot_callback(
    chat_id: str,
    title: str,
    body: str,
    topic_id: Optional[str] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send Telegram notification via bot callback endpoint.

    Calls the bot's /internal/telegram-send endpoint with INTERNAL_API_SECRET.
    This is the preferred method as the bot controls its own token.
    """
    import os
    callback_url = os.environ.get("BOT_TELEGRAM_SEND_URL", "http://bot:8080/internal/telegram-send")
    internal_secret = os.environ.get("INTERNAL_API_SECRET", "")
    if not internal_secret:
        return False

    payload: Dict[str, Any] = {
        "chat_id": chat_id,
        "title": title,
        "body": body,
    }
    if topic_id and str(topic_id) != "0":
        payload["topic_id"] = str(topic_id)
    if reply_markup:
        payload["reply_markup"] = reply_markup

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                callback_url,
                json=payload,
                headers={"X-Internal-Api-Secret": internal_secret},
            )
            if resp.status_code == 200:
                logger.debug("Bot callback sent to chat_id=%s", chat_id)
                return True
            logger.warning("Bot callback failed: %d %s", resp.status_code, resp.text[:200])
            return False
    except Exception as e:
        logger.warning("Bot callback error: %s", e)
        return False


async def send_telegram(
    chat_id: str,
    title: str,
    body: str,
    topic_id: Optional[str] = None,
    bot_token: Optional[str] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
) -> bool:
    """Send notification to Telegram chat/group.

    Tries bot callback first (if INTERNAL_API_SECRET is configured), then
    falls back to direct Telegram Bot API with the provided or global bot_token.
    ``reply_markup`` is an optional InlineKeyboardMarkup dict for quick action buttons.
    """
    # Try bot callback first (preferred)
    callback_ok = await _send_telegram_via_bot_callback(chat_id, title, body, topic_id, reply_markup)
    if callback_ok:
        NOTIFICATIONS_SENT.labels(channel="telegram").inc()
        return True

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
        if reply_markup:
            payload["reply_markup"] = reply_markup

        logger.debug("Sending Telegram notification to chat_id=%s", chat_id)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json=payload,
            )
            if resp.status_code == 200:
                logger.info("Telegram notification sent to chat_id=%s", chat_id)
                NOTIFICATIONS_SENT.labels(channel="telegram").inc()
                return True
            logger.error("Telegram send failed (chat_id=%s): %s %s", chat_id, resp.status_code, resp.text, exc_info=True)
            NOTIFICATIONS_FAILED.labels(channel="telegram").inc()
            return False
    except Exception as e:
        logger.error("Telegram notification error (chat_id=%s): %s", chat_id, e, exc_info=True)
        NOTIFICATIONS_FAILED.labels(channel="telegram").inc()
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
                NOTIFICATIONS_SENT.labels(channel="webhook").inc()
                return True
            logger.error("Webhook send failed: %s %s", resp.status_code, resp.text[:200], exc_info=True)
            NOTIFICATIONS_FAILED.labels(channel="webhook").inc()
            return False
    except Exception as e:
        logger.error("Webhook notification error: %s", e, exc_info=True)
        NOTIFICATIONS_FAILED.labels(channel="webhook").inc()
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
    telegram_body: Optional[str] = None,
    reply_markup: Optional[Dict[str, Any]] = None,
    event: Optional[str] = None,
    **kwargs,
) -> Optional[int]:
    """Create in-app notification and dispatch to configured channels.

    If admin_id is None, creates notification for all admins.
    ``topic_type`` controls which Telegram topic the global fallback
    message is sent to ("nodes", "service", "users", "errors", …).
    ``telegram_body`` if set, will be used for Telegram messages instead of ``body``
    (useful for sending HTML-formatted messages to Telegram while storing plain text in DB).
    Returns the notification ID.
    """
    channels = channels or ["in_app"]
    notification_id = None

    try:
        from shared.database import db_service

        if admin_id is not None:
            # Single admin
            async with db_service.acquire() as conn:
                # Deduplication: skip if same group_key exists within last 5 min
                if group_key:
                    existing = await conn.fetchval(
                        select_sql(NOTIFICATIONS_TABLE, "id", "WHERE admin_id = $1 AND group_key = $2 AND created_at > NOW() - INTERVAL '5 minutes'"),
                        admin_id, group_key,
                    )
                    if existing:
                        logger.debug("Skipping duplicate notification (group_key=%s)", group_key)
                        return existing

                notification_id = await conn.fetchval(
                    insert_sql(NOTIFICATIONS_TABLE, ["admin_id", "type", "severity", "title", "body", "link", "source", "source_id", "group_key"], "RETURNING id"),
                    admin_id, type, severity, title, body, link, source, source_id, group_key,
                )
                if notification_id is not None:
                    NOTIFICATIONS_SENT.labels(channel="in_app").inc()
        else:
            # Broadcast to all admins
            all_deduplicated = True
            async with db_service.acquire() as conn:
                admin_ids = await conn.fetch(
                    select_sql(
                        ADMIN_TABLE,
                        "id",
                        "WHERE is_active = true",
                    ),
                )
                for row in admin_ids:
                    aid = row["id"]

                    # Deduplication: skip if same group_key exists within last 15 min
                    if group_key:
                        existing = await conn.fetchval(
                            select_sql(NOTIFICATIONS_TABLE, "id", "WHERE admin_id = $1 AND group_key = $2 AND created_at > NOW() - INTERVAL '15 minutes'"),
                            aid, group_key,
                        )
                        if existing:
                            logger.debug("Skipping duplicate broadcast notification (admin=%s, group_key=%s)", aid, group_key)
                            if notification_id is None:
                                notification_id = existing
                            continue

                    all_deduplicated = False
                    nid = await conn.fetchval(
                        "INSERT INTO notifications (admin_id, type, severity, title, body, link, source, source_id, group_key) "
                        "VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING id",
                        aid, type, severity, title, body, link, source, source_id, group_key,
                    )
                    if nid is not None:
                        NOTIFICATIONS_SENT.labels(channel="in_app").inc()
                    if notification_id is None:
                        notification_id = nid

            # If all broadcast notifications were deduplicated, skip all dispatch
            if all_deduplicated and admin_ids:
                logger.debug("All broadcast notifications deduplicated (group_key=%s), skipping dispatch", group_key)
                return notification_id

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

        # Use telegram_body for Telegram channels if provided, otherwise fall back to body
        tg_body = telegram_body or body

        # Collect per-admin Telegram chat_ids to avoid duplicate global send
        per_admin_tg_chat_ids: set = set()

        # Dispatch to external channels (per-admin configured channels)
        if admin_id is not None:
            per_admin_tg_chat_ids = await _collect_telegram_chat_ids(admin_id)
            asyncio.create_task(_dispatch_external(admin_id, title, tg_body, severity, link, channels, reply_markup=reply_markup))
        else:
            # For broadcasts, dispatch to all admins' external channels
            try:
                async with db_service.acquire() as conn:
                    admin_ids_rows = await conn.fetch(
                        select_sql(
                            ADMIN_TABLE,
                            "id",
                            "WHERE is_active = true",
                        ),
                    )

                if admin_ids_rows:
                    logger.debug("Broadcasting external channels to %d admin accounts", len(admin_ids_rows))
                    for row in admin_ids_rows:
                        aid_chat_ids = await _collect_telegram_chat_ids(row["id"])
                        per_admin_tg_chat_ids.update(aid_chat_ids)
                        asyncio.create_task(
                            _dispatch_external(row["id"], title, tg_body, severity, link, channels, reply_markup=reply_markup)
                        )
                else:
                    logger.debug("No admin_accounts found for external dispatch")
            except Exception as e:
                logger.error("Failed to dispatch to admin channels: %s", e, exc_info=True)

        # Global channel fallback: send to NOTIFICATIONS_CHAT_ID for Telegram.
        # Skip if a per-admin channel already covers the same chat_id
        # to prevent duplicate messages.
        if "telegram" in channels or "all" in channels:
            _, global_chat_id, _ = _get_global_telegram_config(topic_type)
            if global_chat_id and global_chat_id not in per_admin_tg_chat_ids:
                asyncio.create_task(
                    _send_to_global_telegram(title, tg_body, severity, topic_type, reply_markup=reply_markup)
                )
            elif not global_chat_id:
                global _warned_no_global_chat
                if not _warned_no_global_chat:
                    _warned_no_global_chat = True
                    logger.warning(
                        "notifications_chat_id не настроен и нет per-admin Telegram-каналов — "
                        "Telegram-уведомления (включая нарушения) НЕ отправляются. "
                        "Укажите чат в Настройках → Уведомления."
                    )
                else:
                    logger.debug("No global NOTIFICATIONS_CHAT_ID, skipping global Telegram")
            else:
                logger.debug("Global chat_id=%s already covered by per-admin channel, skipping duplicate", global_chat_id)

        # FCM push для мобильных админов: дублируем все нотификации, у которых
        # явно запрошен канал "push" или "all". В data-payload кладём тип/source/id —
        # клиент решит, куда диплинкнуть (users/{uuid}, nodes/{uuid}, violations/{id}).
        if "push" in channels or "all" in channels:
            try:
                from web.backend.core.push_service import (
                    is_enabled as _push_enabled,
                    send_to_admin as _push_to_admin,
                    broadcast_to_admins as _push_broadcast,
                )
                if _push_enabled():
                    push_data = {
                        "type": type or "info",
                        "severity": severity or "info",
                    }
                    if event:
                        push_data["event"] = event
                    if source:
                        push_data["source"] = source
                    if source_id:
                        push_data["source_id"] = str(source_id)
                    if link:
                        push_data["link"] = link
                    if admin_id is not None:
                        asyncio.create_task(_push_to_admin(admin_id, title, body, push_data))
                    else:
                        asyncio.create_task(_push_broadcast(title, body, push_data))
            except Exception as e:
                logger.debug("FCM push dispatch skipped: %s", e)

    except Exception as e:
        logger.error("Failed to create notification: %s", e, exc_info=True)

    return notification_id


async def _collect_telegram_chat_ids(admin_id: int) -> set:
    """Return the set of Telegram chat_ids configured for this admin."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(NOTIFICATION_CHANNELS_TABLE, "config", "WHERE admin_id = $1 AND channel_type = 'telegram' AND is_enabled = true"),
                admin_id,
            )
        chat_ids = set()
        for row in rows:
            config = row["config"] if isinstance(row["config"], dict) else json.loads(row["config"] or "{}")
            cid = config.get("chat_id")
            if cid:
                chat_ids.add(str(cid))
        return chat_ids
    except Exception as e:
        logger.debug("Failed to collect telegram chat_ids for admin %s: %s", admin_id, e)
        return set()


async def _send_to_global_telegram(
    title: str, body: str, severity: str, topic_type: str = "service",
    reply_markup: Optional[Dict[str, Any]] = None,
):
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

        ok = await send_telegram(chat_id, full_title, body, topic_id, bot_token, reply_markup=reply_markup)
        if ok:
            logger.info("Global Telegram notification sent to chat_id=%s", chat_id)
        else:
            logger.warning("Global Telegram notification failed for chat_id=%s", chat_id)
    except Exception as e:
        logger.error("Global Telegram dispatch error: %s", e, exc_info=True)


async def _dispatch_external(
    admin_id: int,
    title: str,
    body: str,
    severity: str,
    link: Optional[str],
    requested_channels: List[str],
    reply_markup: Optional[Dict[str, Any]] = None,
):
    """Dispatch notification to external channels based on admin's channel config."""
    try:
        from shared.database import db_service
        async with db_service.acquire() as conn:
            channels = await conn.fetch(
                select_sql(NOTIFICATION_CHANNELS_TABLE, "channel_type, config", "WHERE admin_id = $1 AND is_enabled = true"),
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
                        await send_telegram(chat_id, title, body, topic_id, bot_token_override, reply_markup=reply_markup)
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
                logger.error("Channel dispatch error (%s, admin=%s): %s", ch_type, admin_id, e, exc_info=True)

    except Exception as e:
        logger.error("External dispatch failed for admin %s: %s", admin_id, e, exc_info=True)


# ── Security notifications (consolidated from notifier.py) ────────


def _esc_html(text: str) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _now_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")


async def notify_login_failed(
    ip: str, username: str, auth_method: str,
    reason: str = "", failures_count: int = 0, password: str = "",
) -> None:
    lines = [
        "<b>Failed login attempt</b>", "",
        f"<b>IP:</b> <code>{_esc_html(ip)}</code>",
        f"<b>Username:</b> <code>{_esc_html(username)}</code>",
        f"<b>Method:</b> {_esc_html(auth_method)}",
    ]
    if password:
        lines.append(f"<b>Password:</b> <tg-spoiler>{_esc_html(password)}</tg-spoiler>")
    if reason:
        lines.append(f"<b>Reason:</b> {_esc_html(reason)}")
    if failures_count > 0:
        lines.append(f"<b>Consecutive failures:</b> {failures_count}")
    lines.append(f"<b>Time:</b> {_now_str()}")
    asyncio.create_task(_send_to_global_telegram("Login failed", "\n".join(lines), "warning", "service"))


async def notify_login_success(ip: str, username: str, auth_method: str) -> None:
    lines = [
        f"<b>IP:</b> <code>{_esc_html(ip)}</code>",
        f"<b>Username:</b> <code>{_esc_html(username)}</code>",
        f"<b>Method:</b> {_esc_html(auth_method)}",
        f"<b>Time:</b> {_now_str()}",
    ]
    asyncio.create_task(_send_to_global_telegram("Admin login", "\n".join(lines), "info", "service"))


async def notify_ip_blocked(ip: str, lockout_seconds: int, failures: int) -> None:
    lines = [
        f"<b>IP:</b> <code>{_esc_html(ip)}</code>",
        f"<b>Failed attempts:</b> {failures}",
        f"<b>Lockout:</b> {lockout_seconds // 60} min",
        f"<b>Time:</b> {_now_str()}",
    ]
    asyncio.create_task(_send_to_global_telegram("IP locked out (brute-force)", "\n".join(lines), "critical", "service"))


async def notify_ip_rejected(ip: str, path: str) -> None:
    lines = [
        f"<b>IP:</b> <code>{_esc_html(ip)}</code>",
        f"<b>Path:</b> <code>{_esc_html(path[:100])}</code>",
        f"<b>Time:</b> {_now_str()}",
    ]
    asyncio.create_task(_send_to_global_telegram("Access denied (IP whitelist)", "\n".join(lines), "warning", "service"))
