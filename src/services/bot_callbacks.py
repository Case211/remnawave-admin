"""Bot callback endpoints for receiving notification requests from backend.

The backend calls these endpoints when it wants the bot to send Telegram
notifications. This replaces the old pattern where the collector forwarded
raw Panel webhooks to the bot's webhook endpoint.
"""
import html
import json
import os
import secrets
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from aiogram import Bot

from shared.logger import logger

app = FastAPI(title="Remnawave Admin Bot Callbacks")


def _verify_internal_secret(request: Request) -> bool:
    """Verify the X-Internal-Api-Secret header."""
    expected = os.environ.get("INTERNAL_API_SECRET", "")
    if not expected:
        logger.error("INTERNAL_API_SECRET not set, rejecting callback")
        return False
    received = request.headers.get("X-Internal-Api-Secret", "")
    if not received or not secrets.compare_digest(received, expected):
        logger.warning("Invalid INTERNAL_API_SECRET in callback")
        return False
    return True


@app.post("/internal/telegram-send")
async def telegram_send(request: Request):
    """Send a Telegram notification via the bot instance.

    Called by the backend notification_service when it wants to send
    a Telegram message. This ensures the bot controls its own token
    and the backend never needs direct Telegram API access.

    Body:
    {
        "chat_id": "123456",
        "title": "Notification title",
        "body": "Notification body (HTML)",
        "topic_id": "123" (optional),
        "reply_markup": {...} (optional)
    }
    """
    if not _verify_internal_secret(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    bot: Optional[Bot] = request.app.state.bot
    if not bot:
        raise HTTPException(status_code=500, detail="Bot instance not available")

    try:
        body = await request.json()
        chat_id = body.get("chat_id")
        title = body.get("title", "")
        text = body.get("body", "")
        topic_id = body.get("topic_id")
        reply_markup = body.get("reply_markup")

        if not chat_id:
            raise HTTPException(status_code=400, detail="chat_id is required")

        message_text = f"<b>{html.escape(title)}</b>\n\n{text}" if title else text

        # Rich-уведомление (Bot API 10.1): заголовок → настоящий heading,
        # строки-поля → список; при отказе — фолбэк на обычный HTML внутри.
        from shared import tg_rich
        await tg_rich.send_rich_or_html(
            bot.token,
            chat_id,
            message_text,
            message_thread_id=int(topic_id) if topic_id and str(topic_id) != "0" else None,
            reply_markup=reply_markup,
        )
        return JSONResponse(status_code=200, content={"status": "ok"})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to send telegram message: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/internal/panel-event")
async def panel_event(request: Request):
    """Handle a panel event forwarded by the backend collector.

    The backend receives the Panel webhook, syncs it to DB,
    and then calls this endpoint to have the bot send formatted
    Telegram notifications.

    Body:
    {
        "event": "user.created",
        "data": {...},
        "timestamp": "2026-01-12T23:31:32Z"
    }
    """
    if not _verify_internal_secret(request):
        raise HTTPException(status_code=401, detail="Unauthorized")

    bot: Optional[Bot] = request.app.state.bot
    if not bot:
        raise HTTPException(status_code=500, detail="Bot instance not available")

    try:
        body = await request.json()
        event = body.get("event", "")
        event_data = body.get("data", {})
        meta = body.get("meta") or {}

        logger.info("Panel event callback: %s", event)

        # Dispatch to notification handlers
        if event.startswith("user."):
            from src.utils.notifications import send_user_notification

            user_uuid = event_data.get("uuid") or event_data.get("id")
            if not user_uuid:
                logger.warning("User UUID not found in panel event data")
                return JSONResponse(status_code=200, content={"status": "skipped", "reason": "no uuid"})

            special_events = {
                "user.expired": "expired",
                "user.expires_in_72_hours": "expires_in_72h",
                "user.expires_in_48_hours": "expires_in_48h",
                "user.expires_in_24_hours": "expires_in_24h",
                "user.expired_24_hours_ago": "expired_24h_ago",
                "user.revoked": "revoked",
                "user.disabled": "disabled",
                "user.enabled": "enabled",
                "user.limited": "limited",
                "user.traffic_reset": "traffic_reset",
                "user.first_connected": "first_connected",
                "user.bandwidth_usage_threshold_reached": "bandwidth_threshold",
                "user.not_connected": "not_connected",
            }

            if event == "user.created":
                action = "created"
            elif event == "user.modified":
                action = "updated"
            elif event == "user.deleted":
                action = "deleted"
            elif event == "user.expiration":
                # 2.8.0: единое событие истечения с часами в meta.expiration
                from src.services.webhook import _expiration_action_from_hours
                action = _expiration_action_from_hours(meta.get("expiration"))
            elif event in special_events:
                action = special_events[event]
            else:
                action = "updated"

            if "response" not in event_data:
                user_data = {"response": event_data}
            else:
                user_data = event_data

            await send_user_notification(bot=bot, action=action, user_info=user_data, event_type=event)

        elif event.startswith("node."):
            from src.utils.notifications import send_node_notification

            if "response" not in event_data:
                node_data = {"response": event_data}
            else:
                node_data = event_data

            await send_node_notification(bot=bot, event=event, node_data=node_data)

        elif event.startswith("service."):
            from src.utils.notifications import send_service_notification

            await send_service_notification(bot=bot, event=event, event_data=event_data)

        elif event.startswith("user_hwid_devices."):
            from src.utils.notifications import send_hwid_notification

            await send_hwid_notification(bot=bot, event=event, event_data=event_data)

        elif event.startswith("errors."):
            from src.utils.notifications import send_error_notification

            await send_error_notification(bot=bot, event=event, event_data=event_data)

        elif event.startswith("crm."):
            from src.utils.notifications import send_crm_notification

            await send_crm_notification(bot=bot, event=event, event_data=event_data)

        else:
            from src.utils.notifications import send_generic_notification

            await send_generic_notification(
                bot=bot,
                title="Unknown event",
                message=f"Event: <code>{html.escape(event)}</code>\n\nData: <code>{html.escape(str(event_data)[:200])}</code>",
                emoji="❓",
            )

        return JSONResponse(status_code=200, content={"status": "ok"})
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error processing panel event: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/internal/health")
async def health():
    return JSONResponse(status_code=200, content={"status": "ok", "service": "bot-callbacks"})
