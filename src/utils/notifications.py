"""Утилиты для отправки уведомлений в Telegram топики."""
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message

from src.config import get_settings
from src.utils.formatters import format_bytes, format_datetime
from src.utils.logger import logger


async def send_user_notification(
    bot: Bot,
    action: str,  # "created", "updated", "deleted"
    user_info: dict,
    old_user_info: dict | None = None,
) -> None:
    """Отправляет уведомление о действии с пользователем в Telegram топик."""
    settings = get_settings()
    
    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return  # Уведомления отключены
    
    logger.info(
        "Sending user notification action=%s chat_id=%s topic_id=%s",
        action,
        settings.notifications_chat_id,
        settings.notifications_topic_id,
    )
    
    try:
        info = user_info.get("response", user_info)
        
        lines = []
        
        if action == "created":
            lines.append("✅ <b>Пользователь создан</b>")
        elif action == "updated":
            lines.append("✏️ <b>Пользователь изменен</b>")
        elif action == "deleted":
            lines.append("🗑 <b>Пользователь удален</b>")
        
        lines.append("")
        lines.append(f"👤 <b>Username:</b> <code>{_esc(info.get('username', 'n/a'))}</code>")
        
        # Лимит трафика
        traffic_limit = info.get("trafficLimitBytes")
        if traffic_limit:
            traffic_display = format_bytes(traffic_limit)
        else:
            traffic_display = "Безлимит"
        
        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            old_traffic_limit = old_info.get("trafficLimitBytes")
            if old_traffic_limit:
                old_traffic_display = format_bytes(old_traffic_limit)
            else:
                old_traffic_display = "Безлимит"
            
            if old_traffic_display != traffic_display:
                lines.append(f"📶 <b>Лимит трафика:</b> <code>{old_traffic_display}</code> → <code>{traffic_display}</code>")
            else:
                lines.append(f"📶 <b>Лимит трафика:</b> <code>{traffic_display}</code>")
        else:
            lines.append(f"📶 <b>Лимит трафика:</b> <code>{traffic_display}</code>")
        
        # Дата истечения подписки
        expire_at = info.get("expireAt")
        if expire_at:
            expire_display = format_datetime(expire_at)
        else:
            expire_display = "—"
        
        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            old_expire_at = old_info.get("expireAt")
            if old_expire_at:
                old_expire_display = format_datetime(old_expire_at)
            else:
                old_expire_display = "—"
            
            if old_expire_display != expire_display:
                lines.append(f"⏳ <b>Дата истечения подписки:</b> <code>{old_expire_display}</code> → <code>{expire_display}</code>")
            else:
                lines.append(f"⏳ <b>Дата истечения подписки:</b> <code>{expire_display}</code>")
        else:
            lines.append(f"⏳ <b>Дата истечения подписки:</b> <code>{expire_display}</code>")
        
        # Ссылка на подписку
        subscription_url = info.get("subscriptionUrl")
        if subscription_url:
            if action == "updated" and old_user_info:
                old_info = old_user_info.get("response", old_user_info)
                old_subscription_url = old_info.get("subscriptionUrl")
                
                if old_subscription_url != subscription_url:
                    lines.append(f"🔗 <b>Ссылка на подписку:</b> {_esc(old_subscription_url)} → {_esc(subscription_url)}")
                else:
                    lines.append(f"🔗 <b>Ссылка на подписку:</b> {_esc(subscription_url)}")
            else:
                lines.append(f"🔗 <b>Ссылка на подписку:</b> {_esc(subscription_url)}")
        else:
            lines.append(f"🔗 <b>Ссылка на подписку:</b> —")
        
        # Внутренний сквад
        active_squads = info.get("activeInternalSquads", [])
        external_squad = info.get("externalSquadUuid")
        
        squad_display = "—"
        if active_squads:
            squad_info = info.get("internalSquads", [])
            if squad_info and isinstance(squad_info, list) and len(squad_info) > 0:
                squad_display = squad_info[0].get("name", active_squads[0])
        elif external_squad:
            squad_display = f"External: {external_squad[:8]}..."
        
        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            old_active_squads = old_info.get("activeInternalSquads", [])
            old_external_squad = old_info.get("externalSquadUuid")
            
            old_squad_display = "—"
            if old_active_squads:
                old_squad_info = old_info.get("internalSquads", [])
                if old_squad_info and isinstance(old_squad_info, list) and len(old_squad_info) > 0:
                    old_squad_display = old_squad_info[0].get("name", old_active_squads[0])
            elif old_external_squad:
                old_squad_display = f"External: {old_external_squad[:8]}..."
            
            if old_squad_display != squad_display:
                lines.append(f"👥 <b>Внутренний сквад:</b> <code>{old_squad_display}</code> → <code>{squad_display}</code>")
            else:
                lines.append(f"👥 <b>Внутренний сквад:</b> <code>{squad_display}</code>")
        else:
            lines.append(f"👥 <b>Внутренний сквад:</b> <code>{squad_display}</code>")
        
        # HWID (только если есть)
        hwid_limit = info.get("hwidDeviceLimit")
        if hwid_limit is not None:
            hwid_display = "Безлимит" if hwid_limit == 0 else str(hwid_limit)
            if action == "updated" and old_user_info:
                old_info = old_user_info.get("response", old_user_info)
                old_hwid_limit = old_info.get("hwidDeviceLimit")
                if old_hwid_limit is not None:
                    old_hwid_display = "Безлимит" if old_hwid_limit == 0 else str(old_hwid_limit)
                else:
                    old_hwid_display = "—"
                
                if old_hwid_display != hwid_display:
                    lines.append(f"💻 <b>HWID:</b> <code>{old_hwid_display}</code> → <code>{hwid_display}</code>")
                else:
                    lines.append(f"💻 <b>HWID:</b> <code>{hwid_display}</code>")
            else:
                lines.append(f"💻 <b>HWID:</b> <code>{hwid_display}</code>")
        
        # Период сброса трафика
        traffic_strategy = info.get("trafficLimitStrategy") or "NO_RESET"
        strategy_display = traffic_strategy
        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            old_strategy = old_info.get("trafficLimitStrategy") or "NO_RESET"
            old_strategy_display = old_strategy
            
            if old_strategy_display != strategy_display:
                lines.append(f"🔁 <b>Период сброса трафика:</b> <code>{old_strategy_display}</code> → <code>{strategy_display}</code>")
            else:
                lines.append(f"🔁 <b>Период сброса трафика:</b> <code>{strategy_display}</code>")
        else:
            lines.append(f"🔁 <b>Период сброса трафика:</b> <code>{strategy_display}</code>")
        
        # TG ID (только если есть)
        telegram_id = info.get("telegramId")
        if telegram_id is not None:
            tg_display = str(telegram_id)
            if action == "updated" and old_user_info:
                old_info = old_user_info.get("response", old_user_info)
                old_telegram_id = old_info.get("telegramId")
                old_tg_display = str(old_telegram_id) if old_telegram_id is not None else "—"
                
                if old_tg_display != tg_display:
                    lines.append(f"✈️ <b>TG ID:</b> <code>{old_tg_display}</code> → <code>{tg_display}</code>")
                else:
                    lines.append(f"✈️ <b>TG ID:</b> <code>{tg_display}</code>")
            else:
                lines.append(f"✈️ <b>TG ID:</b> <code>{tg_display}</code>")
        
        # Описание (только если есть)
        description = info.get("description")
        if description:
            if action == "updated" and old_user_info:
                old_info = old_user_info.get("response", old_user_info)
                old_description = old_info.get("description")
                
                if old_description != description:
                    lines.append(f"📝 <b>Описание:</b> <code>{_esc(old_description or '—')}</code> → <code>{_esc(description)}</code>")
                else:
                    lines.append(f"📝 <b>Описание:</b> <code>{_esc(description)}</code>")
            else:
                lines.append(f"📝 <b>Описание:</b> <code>{_esc(description)}</code>")
        
        text = "\n".join(lines)
        
        # Отправляем в топик
        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }
        
        # Добавляем message_thread_id только если он указан
        if settings.notifications_topic_id is not None:
            message_kwargs["message_thread_id"] = settings.notifications_topic_id
        
        await bot.send_message(**message_kwargs)
        logger.info("User notification sent successfully action=%s chat_id=%s", action, settings.notifications_chat_id)
        
    except Exception as exc:
        logger.exception(
            "Failed to send user notification action=%s user_uuid=%s chat_id=%s topic_id=%s error=%s",
            action,
            info.get("uuid", "unknown"),
            settings.notifications_chat_id,
            settings.notifications_topic_id,
            exc,
        )


def _esc(text: str) -> str:
    """Экранирует HTML символы."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
