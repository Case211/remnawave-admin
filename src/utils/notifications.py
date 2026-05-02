"""Утилиты для отправки уведомлений в Telegram топики."""
import asyncio
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from aiogram import Bot
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

from src.config import get_settings
from src.utils.formatters import format_bytes, format_datetime, format_provider_name
from shared.logger import logger


def _strip_html(text: str) -> str:
    """Чистим HTML-теги из текста — для FCM payload, который читается как plain text."""
    return re.sub(r"<[^>]+>", "", text)


def _push_dispatch(
    title: str,
    body: str,
    notification_type: str = "info",
    source: Optional[str] = None,
    source_id: Optional[str] = None,
    severity: str = "info",
    event: Optional[str] = None,
) -> None:
    """Запускаем broadcast пуша в фоне — НЕ блокирует основной поток отправки в TG.

    `event` — конкретный event_id (например `user.expires_in_72_hours`,
    `node.connection_lost`). Используется push_service для точечной фильтрации
    по подпискам устройства; должен соответствовать одному из id в
    `shared/notification_events.py`.

    Бот ловит часть событий от Panel (node.online/offline, user.*, hwid.*, service.*)
    напрямую через webhook и отправляет в Telegram через aiogram, обходя
    `notification_service.create_notification()`. Чтобы те же события долетели
    до мобильника как FCM-пуш, дёргаем shared.push_service отсюда.
    """
    try:
        from shared.push_service import broadcast_to_admins, is_enabled
        if not is_enabled():
            return
        data: Dict[str, Any] = {
            "type": notification_type,
            "severity": severity,
        }
        if event:
            data["event"] = event
        if source:
            data["source"] = source
        if source_id:
            data["source_id"] = str(source_id)
        clean_body = _strip_html(body)
        clean_title = _strip_html(title)
        asyncio.create_task(
            broadcast_to_admins(
                title=clean_title or "Remnawave Admin",
                body=clean_body,
                data=data,
            )
        )
    except Exception as e:
        # Падать в push не должны — бот шлёт TG в любом случае.
        logger.debug("push dispatch from bot skipped: %s", e)


# Кэш для throttling уведомлений о нарушениях
# Ключ: user_uuid, Значение: datetime последнего уведомления
_violation_notification_cache: Dict[str, datetime] = {}

# Минимальный интервал между уведомлениями для одного пользователя (минуты)
VIOLATION_NOTIFICATION_COOLDOWN_MINUTES = 15


def _cleanup_notification_cache() -> None:
    """Очищает устаревшие записи из кэша уведомлений (старше 1 часа)."""
    global _violation_notification_cache
    now = datetime.utcnow()
    max_age = timedelta(hours=1)

    expired_keys = [
        key for key, timestamp in _violation_notification_cache.items()
        if now - timestamp > max_age
    ]

    for key in expired_keys:
        del _violation_notification_cache[key]

    if expired_keys:
        logger.debug("Cleaned up %d expired notification cache entries", len(expired_keys))


async def _get_squad_name_by_uuid(squad_uuid: str) -> str:
    """Получает имя сквада по UUID из API."""
    try:
        from shared.api_client import api_client
        squads_res = await api_client.get_internal_squads()
        all_squads = squads_res.get("response", {}).get("internalSquads", [])
        for squad in all_squads:
            if squad.get("uuid") == squad_uuid:
                return squad.get("name", squad_uuid[:8] + "...")
        return squad_uuid[:8] + "..."
    except Exception as exc:
        logger.debug("Failed to get squad name from API for uuid=%s: %s", squad_uuid, exc)
        return squad_uuid[:8] + "..."


async def _resolve_squads_display(active_squads: list) -> str:
    """Resolve all active internal squads to a comma-separated display string."""
    if not active_squads:
        return "—"
    names = []
    for sq in active_squads:
        if isinstance(sq, dict):
            name = sq.get("name")
            if name:
                names.append(name)
            else:
                uuid = sq.get("uuid", "")
                names.append(await _get_squad_name_by_uuid(uuid) if uuid else "?")
        else:
            names.append(await _get_squad_name_by_uuid(str(sq)))
    return ", ".join(names) if names else "—"


async def send_user_notification(
    bot: Bot,
    action: str,  # "created", "updated", "deleted", "expired", "expires_in_*", etc.
    user_info: dict,
    old_user_info: dict | None = None,
    changes: list | None = None,  # Список изменений из sync_service
    event_type: str | None = None,  # Оригинальный тип события из webhook
) -> None:
    """Отправляет уведомление о действии с пользователем в Telegram топик."""
    settings = get_settings()
    
    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return  # Уведомления отключены
    
    topic_id = settings.get_topic_for_users()
    logger.info(
        "Sending user notification action=%s chat_id=%s topic_id=%s",
        action,
        settings.notifications_chat_id,
        topic_id,
    )
    
    try:
        info = user_info.get("response", user_info)
        
        lines = []
        
        # Заголовок уведомления в зависимости от типа события
        event_titles = {
            "created": "✅ <b>Пользователь создан</b>",
            "updated": "✏️ <b>Пользователь изменен</b>",
            "deleted": "🗑 <b>Пользователь удален</b>",
            "expired": "⏱️ <b>Подписка истекла</b>",
            "expires_in_72h": "⏰ <b>Подписка истекает через 72 часа</b>",
            "expires_in_48h": "⏰ <b>Подписка истекает через 48 часов</b>",
            "expires_in_24h": "⏰ <b>Подписка истекает через 24 часа</b>",
            "expired_24h_ago": "⏱️ <b>Подписка истекла 24 часа назад</b>",
            "revoked": "🚫 <b>Подписка отозвана</b>",
            "disabled": "❌ <b>Пользователь отключен</b>",
            "enabled": "✅ <b>Пользователь включен</b>",
            "limited": "⚠️ <b>Достигнут лимит трафика</b>",
            "traffic_reset": "🔄 <b>Трафик сброшен</b>",
            "first_connected": "🟢 <b>Первый вход пользователя</b>",
            "bandwidth_threshold": "📊 <b>Достигнут порог использования трафика</b>",
            "not_connected": "🔴 <b>Пользователь не подключался</b>",
        }
        
        lines.append(event_titles.get(action, "✏️ <b>Пользователь изменен</b>"))
        lines.append("")
        
        # Основная информация о пользователе
        lines.append("👤 <b>Информация о пользователе</b>")
        lines.append(f"   Username: <code>{_esc(info.get('username', 'n/a'))}</code>")
        
        user_uuid = info.get("uuid", "")
        short_uuid = info.get("shortUuid", "")
        if user_uuid:
            lines.append(f"   UUID: <code>{user_uuid}</code>")
        if short_uuid:
            lines.append(f"   Short UUID: <code>{short_uuid}</code>")
        
        lines.append("")
        
        # Секция: Трафик и лимиты
        lines.append("📊 <b>Трафик и лимиты</b>")
        
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
                lines.append(f"   Лимит трафика: <code>{old_traffic_display}</code> → <code>{traffic_display}</code>")
            else:
                lines.append(f"   Лимит трафика: <code>{traffic_display}</code>")
        else:
            lines.append(f"   Лимит трафика: <code>{traffic_display}</code>")
        
        # Дата истечения подписки (особенно важно для expired событий)
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
                lines.append(f"   Дата истечения: <code>{old_expire_display}</code> → <code>{expire_display}</code>")
            else:
                lines.append(f"   Дата истечения: <code>{expire_display}</code>")
        else:
            lines.append(f"   Дата истечения: <code>{expire_display}</code>")
        
        traffic_strategy = info.get("trafficLimitStrategy") or "NO_RESET"
        strategy_display = traffic_strategy
        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            old_strategy = old_info.get("trafficLimitStrategy") or "NO_RESET"
            old_strategy_display = old_strategy
            
            if old_strategy_display != strategy_display:
                lines.append(f"   Период сброса: <code>{old_strategy_display}</code> → <code>{strategy_display}</code>")
            else:
                lines.append(f"   Период сброса: <code>{strategy_display}</code>")
        else:
            lines.append(f"   Период сброса: <code>{strategy_display}</code>")
        
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
                    lines.append(f"   HWID лимит: <code>{old_hwid_display}</code> → <code>{hwid_display}</code>")
                else:
                    lines.append(f"   HWID лимит: <code>{hwid_display}</code>")
            else:
                lines.append(f"   HWID лимит: <code>{hwid_display}</code>")
        
        lines.append("")
        
        # Секция: Дополнительная информация
        lines.append("🔗 <b>Дополнительная информация</b>")
        
        subscription_url = info.get("subscriptionUrl")
        if subscription_url:
            lines.append(f"   Ссылка на подписку: {_esc(subscription_url)}")
        else:
            lines.append(f"   Ссылка на подписку: —")
        
        # Внутренний сквад
        active_squads = info.get("activeInternalSquads", [])
        external_squad = info.get("externalSquadUuid")
        
        squad_display = await _resolve_squads_display(active_squads)
        if squad_display == "—" and external_squad:
            squad_display = f"External: {external_squad[:8]}..."

        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            old_active_squads = old_info.get("activeInternalSquads", [])
            old_external_squad = old_info.get("externalSquadUuid")

            old_squad_display = await _resolve_squads_display(old_active_squads)
            if old_squad_display == "—" and old_external_squad:
                old_squad_display = f"External: {old_external_squad[:8]}..."

            if old_squad_display != squad_display:
                lines.append(f"   Сквад: <code>{old_squad_display}</code> → <code>{squad_display}</code>")
            else:
                lines.append(f"   Сквад: <code>{squad_display}</code>")
        else:
            lines.append(f"   Сквад: <code>{squad_display}</code>")
        
        # Контакты
        telegram_id = info.get("telegramId")
        email = info.get("email")
        if telegram_id is not None or email:
            lines.append("")
            lines.append("📞 <b>Контакты</b>")
            if telegram_id is not None:
                lines.append(f"   Telegram ID: <code>{telegram_id}</code>")
            if email:
                lines.append(f"   Email: <code>{_esc(email)}</code>")
        
        # Описание (только если есть)
        description = info.get("description")
        if description:
            lines.append("")
            lines.append("📝 <b>Описание</b>")
            if action == "updated" and old_user_info:
                old_info = old_user_info.get("response", old_user_info)
                old_description = old_info.get("description")
                
                if old_description != description:
                    lines.append(f"   <code>{_esc(old_description or '—')}</code> → <code>{_esc(description)}</code>")
                else:
                    lines.append(f"   <code>{_esc(description)}</code>")
            else:
                lines.append(f"   <code>{_esc(description)}</code>")
        
        # Секция изменений (если есть changes из sync_service)
        if changes and action == "updated":
            lines.append("")
            lines.append("📋 <b>Изменения</b>")
            for change in changes:
                lines.append(f"   {_esc(change)}")
        
        text = "\n".join(lines)
        
        # Отправляем в топик
        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        # Добавляем message_thread_id только если он указан
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)
        logger.info("User notification sent successfully action=%s chat_id=%s", action, settings.notifications_chat_id)

        # Маппинг наших коротких action-имён в Panel webhook event_id, под которыми
        # они известны и хранятся в каталоге shared/notification_events.py.
        action_to_event = {
            "expires_in_72h": "user.expires_in_72_hours",
            "expires_in_48h": "user.expires_in_48_hours",
            "expires_in_24h": "user.expires_in_24_hours",
            "expired_24h_ago": "user.expired_24_hours_ago",
        }
        event_id = action_to_event.get(action, f"user.{action}")
        _push_dispatch(
            title=f"Юзер: {action}",
            body=info.get("username") or info.get("uuid", "")[:8],
            notification_type="info",
            source="panel.webhook",
            source_id=info.get("uuid"),
            event=event_id,
        )

    except Exception as exc:
        logger.exception(
            "Failed to send user notification action=%s user_uuid=%s chat_id=%s topic_id=%s error=%s",
            action,
            info.get("uuid", "unknown"),
            settings.notifications_chat_id,
            topic_id,
            exc,
        )


async def send_generic_notification(
    bot: Bot,
    title: str,
    message: str,
    emoji: str = "ℹ️",
    topic_type: str | None = None,
) -> None:
    """Отправляет общее уведомление в Telegram топик.

    Args:
        topic_type: Тип топика (users, nodes, service, hwid, crm, errors).
                   Если не указан, используется общий notifications_topic_id.
    """
    settings = get_settings()

    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    # Определяем топик по типу
    topic_getters = {
        "users": settings.get_topic_for_users,
        "nodes": settings.get_topic_for_nodes,
        "service": settings.get_topic_for_service,
        "hwid": settings.get_topic_for_hwid,
        "crm": settings.get_topic_for_crm,
        "errors": settings.get_topic_for_errors,
    }
    topic_id = topic_getters.get(topic_type, lambda: settings.notifications_topic_id)()

    try:
        text = f"{emoji} <b>{title}</b>\n\n{message}"

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)
        logger.info("Generic notification sent successfully title=%s topic_id=%s", title, topic_id)

    except Exception as exc:
        logger.exception("Failed to send generic notification title=%s error=%s", title, exc)


async def send_node_notification(
    bot: Bot,
    event: str,
    node_data: dict,
    old_node_data: dict | None = None,
    changes: list | None = None,
) -> None:
    """Отправляет уведомление о событии с нодой с поддержкой изменений."""
    settings = get_settings()

    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = settings.get_topic_for_nodes()

    try:
        node_info = node_data.get("response", node_data) if isinstance(node_data, dict) else node_data
        
        lines = []
        
        # Определяем заголовок по типу события
        event_titles = {
            "node.created": "🆕 <b>Нода создана</b>",
            "node.modified": "✏️ <b>Нода изменена</b>",
            "node.disabled": "❌ <b>Нода отключена</b>",
            "node.enabled": "✅ <b>Нода включена</b>",
            "node.deleted": "🗑 <b>Нода удалена</b>",
            "node.connection_lost": "🔴 <b>Потеряно соединение с нодой</b>",
            "node.connection_restored": "🟢 <b>Соединение с нодой восстановлено</b>",
            "node.traffic_notify": "📊 <b>Уведомление о трафике ноды</b>",
        }
        
        lines.append(event_titles.get(event, f"ℹ️ <b>Событие ноды: {event}</b>"))
        lines.append("")
        
        # Информация о ноде
        node_name = node_info.get("name", "n/a")
        node_uuid = node_info.get("uuid", "n/a")
        address = node_info.get("address", "—")
        port = node_info.get("port", "—")
        country = node_info.get("countryCode", "—")
        status = node_info.get("status", "—")
        
        lines.append(f"🖥 <b>Название:</b> <code>{_esc(node_name)}</code>")
        lines.append(f"🆔 <b>UUID:</b> <code>{node_uuid[:8]}...</code>")
        lines.append(f"🌐 <b>Адрес:</b> <code>{_esc(str(address))}</code>")
        if port != "—":
            lines.append(f"🔌 <b>Порт:</b> <code>{port}</code>")
        if country != "—":
            lines.append(f"🌍 <b>Страна:</b> <code>{country}</code>")
        if status != "—":
            lines.append(f"📊 <b>Статус:</b> <code>{status}</code>")
        
        # Трафик (если есть)
        traffic_limit = node_info.get("trafficLimitBytes")
        if traffic_limit:
            lines.append(f"📶 <b>Лимит трафика:</b> <code>{format_bytes(traffic_limit)}</code>")
        
        # Секция изменений
        if changes and event == "node.modified":
            lines.append("")
            lines.append("📋 <b>Изменения</b>")
            for change in changes:
                lines.append(f"   {_esc(change)}")
        
        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)
        logger.info("Node notification sent successfully event=%s node_uuid=%s topic_id=%s", event, node_uuid, topic_id)

        # FCM push: критичные события про ноды отправляем как category=alerts,
        # обычные изменения — как info. node.connection_lost = 🔴 → severity critical.
        critical_events = {"node.connection_lost", "node.disabled", "node.deleted"}
        push_severity = "critical" if event in critical_events else "info"
        push_type = "alert" if event in critical_events else "info"
        _push_dispatch(
            title=event_titles.get(event, "Событие ноды"),
            body=f"{node_name} ({address})",
            notification_type=push_type,
            source="panel.webhook",
            source_id=node_uuid,
            severity=push_severity,
            event=event,
        )

    except Exception as exc:
        logger.exception("Failed to send node notification event=%s error=%s", event, exc)


async def send_service_notification(
    bot: Bot,
    event: str,
    event_data: dict,
) -> None:
    """Отправляет уведомление о событии сервиса."""
    settings = get_settings()

    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = settings.get_topic_for_service()

    try:
        lines = []
        
        event_titles = {
            "service.panel_started": "🚀 <b>Панель запущена</b>",
            "service.login_attempt_failed": "⚠️ <b>Неудачная попытка входа</b>",
            "service.login_attempt_success": "✅ <b>Успешный вход</b>",
            "panel.unavailable": "❌ <b>Панель недоступна</b>",
        }
        
        lines.append(event_titles.get(event, f"ℹ️ <b>Событие сервиса: {event}</b>"))
        lines.append("")
        
        # Дополнительная информация
        if event == "service.login_attempt_failed" or event == "service.login_attempt_success":
            username = event_data.get("username", "—")
            ip = event_data.get("ip", "—")
            user_agent = event_data.get("userAgent", "—")
            
            lines.append(f"👤 <b>Username:</b> <code>{_esc(username)}</code>")
            if ip != "—":
                lines.append(f"🌐 <b>IP:</b> <code>{_esc(ip)}</code>")
            if user_agent != "—":
                lines.append(f"🔍 <b>User Agent:</b> <code>{_esc(user_agent[:50])}</code>")
        elif event == "panel.unavailable":
            error_type = event_data.get("error_type", "—")
            error_message = event_data.get("error_message", "—")
            consecutive_failures = event_data.get("consecutive_failures", 0)
            last_check = event_data.get("last_check", "—")
            
            lines.append(f"⚠️ <b>Ошибка:</b> <code>{_esc(error_type)}</code>")
            if error_message != "—":
                lines.append(f"📝 <b>Сообщение:</b> <code>{_esc(error_message[:100])}</code>")
            lines.append(f"🔄 <b>Неудачных попыток подряд:</b> {consecutive_failures}")
            if last_check != "—":
                lines.append(f"🕒 <b>Последняя проверка:</b> {last_check}")
        
        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)
        logger.info("Service notification sent successfully event=%s topic_id=%s", event, topic_id)

        # Сервисные события (бэкап, рестарт панели и т.п.) — alert-категория,
        # они интересны на телефоне даже когда ты не у компа.
        _push_dispatch(
            title=f"Сервис: {event}",
            body=f"Событие {event}",
            notification_type="alert",
            source="panel.webhook",
            source_id=event,
            severity="warning",
            event=event,
        )

    except Exception as exc:
        logger.exception("Failed to send service notification event=%s error=%s", event, exc)


async def send_hwid_notification(
    bot: Bot,
    event: str,
    event_data: dict,
) -> None:
    """Отправляет уведомление о HWID устройстве."""
    settings = get_settings()

    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = settings.get_topic_for_hwid()

    try:
        lines = []
        
        event_titles = {
            "user_hwid_devices.added": "➕ <b>HWID устройство добавлено</b>",
            "user_hwid_devices.deleted": "➖ <b>HWID устройство удалено</b>",
        }
        
        lines.append(event_titles.get(event, f"💻 <b>Событие HWID: {event}</b>"))
        lines.append("")
        
        # Информация о пользователе
        user_data = event_data.get("user", {})
        # Webhook может прислать hwidDevice или hwidUserDevice
        hwid_data = event_data.get("hwidDevice", {}) or event_data.get("hwidUserDevice", {})

        if user_data:
            username = user_data.get("username", "n/a")
            user_uuid = user_data.get("uuid", "n/a")
            telegram_id = user_data.get("telegramId")
            status = user_data.get("status", "—")
            description = user_data.get("description", "")
            hwid_device_limit = user_data.get("hwidDeviceLimit", 0)

            lines.append(f"👤 <b>Пользователь:</b> <code>{_esc(username)}</code>")
            lines.append(f"🆔 <b>UUID:</b> <code>{user_uuid}</code>")

            if telegram_id is not None:
                lines.append(f"📱 <b>TG ID:</b> <code>{telegram_id}</code>")

            lines.append(f"📊 <b>Статус:</b> <code>{status}</code>")

            if description:
                lines.append(f"📝 <b>Описание:</b> <code>{_esc(description[:100])}</code>")

            # Информация о лимите устройств
            limit_display = "∞" if hwid_device_limit == 0 else str(hwid_device_limit)
            lines.append(f"📲 <b>Лимит устройств:</b> <code>{limit_display}</code>")

            lines.append("")

        if hwid_data:
            lines.append("💻 <b>Информация об устройстве</b>")
            hwid = hwid_data.get("hwid", "—")
            platform = hwid_data.get("platform", "—")
            os_version = hwid_data.get("osVersion", "—")
            device_model = hwid_data.get("deviceModel", "—")
            user_agent = hwid_data.get("userAgent", "—")
            created_at = hwid_data.get("createdAt")

            if hwid != "—":
                lines.append(f"   HWID: <code>{_esc(hwid)}</code>")
            if platform != "—":
                lines.append(f"   Платформа: <code>{_esc(platform)}</code>")
            if os_version != "—":
                lines.append(f"   Версия ОС: <code>{_esc(os_version)}</code>")
            if device_model != "—":
                lines.append(f"   Модель: <code>{_esc(device_model)}</code>")
            if user_agent != "—":
                lines.append(f"   User-Agent: <code>{_esc(user_agent[:60])}</code>")
            if created_at:
                lines.append(f"   Добавлено: <code>{format_datetime(created_at)}</code>")
        
        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)
        logger.info("HWID notification sent successfully event=%s topic_id=%s", event, topic_id)

    except Exception as exc:
        logger.exception("Failed to send HWID notification event=%s error=%s", event, exc)


async def send_error_notification(
    bot: Bot,
    event: str,
    event_data: dict,
) -> None:
    """Отправляет уведомление об ошибке."""
    settings = get_settings()

    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = settings.get_topic_for_errors()

    try:
        lines = []
        
        lines.append("⚠️ <b>Ошибка системы</b>")
        lines.append("")
        lines.append(f"<b>Тип:</b> <code>{_esc(event)}</code>")
        
        # Дополнительная информация
        message = event_data.get("message", "")
        if message:
            lines.append(f"<b>Сообщение:</b> <code>{_esc(message)}</code>")
        
        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)
        logger.info("Error notification sent successfully event=%s topic_id=%s", event, topic_id)

        # Ошибки/системные алерты обязательно пушим — это то, ради чего пуши и нужны.
        _push_dispatch(
            title=f"Ошибка: {event}",
            body=f"Событие {event}",
            notification_type="alert",
            source="panel.webhook",
            source_id=event,
            severity="critical",
            event=event,
        )

    except Exception as exc:
        logger.exception("Failed to send error notification event=%s error=%s", event, exc)


async def send_crm_notification(
    bot: Bot,
    event: str,
    event_data: dict,
) -> None:
    """Отправляет уведомление о событиях CRM (биллинг инфраструктуры)."""
    settings = get_settings()

    if not settings.notifications_chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = settings.get_topic_for_crm()

    try:
        lines = []

        event_titles = {
            "crm.infra_billing_node_payment_in_7_days": "📅 <b>Оплата ноды через 7 дней</b>",
            "crm.infra_billing_node_payment_in_48hrs": "⏰ <b>Оплата ноды через 48 часов</b>",
            "crm.infra_billing_node_payment_in_24hrs": "⏰ <b>Оплата ноды через 24 часа</b>",
            "crm.infra_billing_node_payment_due_today": "🔴 <b>Оплата ноды сегодня</b>",
            "crm.infra_billing_node_payment_overdue_24hrs": "⚠️ <b>Оплата ноды просрочена на 24 часа</b>",
            "crm.infra_billing_node_payment_overdue_48hrs": "⚠️ <b>Оплата ноды просрочена на 48 часов</b>",
            "crm.infra_billing_node_payment_overdue_7_days": "🚨 <b>Оплата ноды просрочена на 7 дней</b>",
        }

        lines.append(event_titles.get(event, f"💰 <b>Событие CRM: {event}</b>"))
        lines.append("")

        # Webhook может прислать данные в двух форматах:
        # 1. Плоский формат: {nodeName, providerName, loginUrl, nextBillingAt}
        # 2. Вложенный формат: {node: {...}, provider: {...}, billingNode: {...}}

        # Проверяем плоский формат (приоритет)
        node_name = event_data.get("nodeName")
        provider_name = event_data.get("providerName")
        login_url = event_data.get("loginUrl")
        next_billing_at = event_data.get("nextBillingAt")

        if node_name or provider_name:
            # Плоский формат webhook
            lines.append("🖥 <b>Информация о ноде</b>")
            if node_name:
                lines.append(f"   Название: <code>{_esc(node_name)}</code>")
            lines.append("")

            if provider_name:
                lines.append("🏢 <b>Провайдер</b>")
                lines.append(f"   Название: <code>{_esc(provider_name)}</code>")
                if login_url:
                    lines.append(f"   Личный кабинет: {_esc(login_url)}")
                lines.append("")

            if next_billing_at:
                lines.append("💰 <b>Информация об оплате</b>")
                lines.append(f"   Следующая оплата: <code>{format_datetime(next_billing_at)}</code>")
        else:
            # Вложенный формат (для совместимости)
            node_data = event_data.get("node", {})
            provider_data = event_data.get("provider", {})
            billing_data = event_data.get("billingNode", {})

            if node_data:
                lines.append("🖥 <b>Информация о ноде</b>")
                node_name = node_data.get("name", "n/a")
                node_uuid = node_data.get("uuid", "")
                node_address = node_data.get("address", "")
                node_port = node_data.get("port")
                node_country = node_data.get("countryCode", "")

                lines.append(f"   Название: <code>{_esc(node_name)}</code>")
                if node_uuid:
                    lines.append(f"   UUID: <code>{node_uuid}</code>")
                if node_address:
                    lines.append(f"   Адрес: <code>{_esc(node_address)}</code>")
                if node_port:
                    lines.append(f"   Порт: <code>{node_port}</code>")
                if node_country:
                    lines.append(f"   Страна: <code>{node_country}</code>")
                lines.append("")

            if provider_data:
                lines.append("🏢 <b>Провайдер</b>")
                provider_name = provider_data.get("name", "n/a")
                provider_uuid = provider_data.get("uuid", "")
                lines.append(f"   Название: <code>{_esc(provider_name)}</code>")
                if provider_uuid:
                    lines.append(f"   UUID: <code>{provider_uuid}</code>")
                lines.append("")

            if billing_data:
                lines.append("💰 <b>Информация об оплате</b>")
                amount = billing_data.get("amount")
                currency = billing_data.get("currency", "")
                next_billing_at = billing_data.get("nextBillingAt")
                last_billing_at = billing_data.get("lastBillingAt")
                billing_interval = billing_data.get("billingInterval", "")

                if amount is not None:
                    amount_str = f"{amount}"
                    if currency:
                        amount_str += f" {currency}"
                    lines.append(f"   Сумма: <code>{amount_str}</code>")
                if billing_interval:
                    lines.append(f"   Интервал: <code>{billing_interval}</code>")
                if next_billing_at:
                    lines.append(f"   Следующая оплата: <code>{format_datetime(next_billing_at)}</code>")
                if last_billing_at:
                    lines.append(f"   Последняя оплата: <code>{format_datetime(last_billing_at)}</code>")

        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)
        logger.info("CRM notification sent successfully event=%s topic_id=%s", event, topic_id)

    except Exception as exc:
        logger.exception("Failed to send CRM notification event=%s error=%s", event, exc)


async def send_violation_notification(
    bot: Bot,
    user_uuid: str,
    violation_score: dict,
    user_info: dict | None = None,
    force: bool = False,
    active_connections: list | None = None,
    ip_metadata: dict | None = None,
    violation_start_time: datetime | None = None,
) -> None:
    """Отправляет уведомление о нарушении в Telegram топик.

    Args:
        bot: Экземпляр бота для отправки сообщений
        user_uuid: UUID пользователя
        violation_score: Словарь с данными о нарушении (ViolationScore)
        user_info: Опциональная информация о пользователе из БД
        force: Если True, игнорирует throttling и отправляет уведомление в любом случае
        active_connections: Список активных подключений пользователя
        ip_metadata: Словарь метаданных IP адресов {ip: IPMetadata}
        violation_start_time: Время начала нарушения (для расчёта длительности)
    """
    settings = get_settings()

    if not settings.notifications_chat_id:
        logger.debug("Violation notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    # Throttling: проверяем, не было ли недавно уведомления для этого пользователя
    now = datetime.utcnow()
    if not force and user_uuid in _violation_notification_cache:
        last_notification = _violation_notification_cache[user_uuid]
        cooldown = timedelta(minutes=VIOLATION_NOTIFICATION_COOLDOWN_MINUTES)

        if now - last_notification < cooldown:
            logger.debug(
                "Violation notification throttled for user %s (cooldown active)",
                user_uuid
            )
            return

    # Очищаем старые записи из кэша (старше 1 часа)
    _cleanup_notification_cache()

    # Используем топик для нарушений (подозреваемых пользователей)
    topic_id = settings.get_topic_for_violations()

    try:
        # Получаем информацию о пользователе если не передана
        if not user_info:
            from shared.database import db_service
            user_info = await db_service.get_user_by_uuid(user_uuid)

        # Извлекаем данные пользователя
        info = user_info.get("response", user_info) if user_info else {}
        username = info.get("username", "n/a")
        email = info.get("email", "")
        telegram_id = info.get("telegramId")
        description = info.get("description", "")
        device_limit = info.get("hwidDeviceLimit", 1)
        if device_limit == 0:
            device_limit = "∞"

        # Извлекаем данные о нарушении
        total_score = violation_score.get("total", violation_score.get("score", 0))
        breakdown = violation_score.get("breakdown", {})

        # Получаем количество одновременных IP из temporal breakdown
        ip_count = 0
        if breakdown and "temporal" in breakdown:
            temporal_data = breakdown["temporal"]
            if isinstance(temporal_data, dict):
                ip_count = temporal_data.get("simultaneous_connections_count", 0)
            elif hasattr(temporal_data, 'simultaneous_connections_count'):
                ip_count = temporal_data.simultaneous_connections_count

        # Если нет ip_count из breakdown, считаем из активных подключений
        if ip_count == 0 and active_connections:
            ip_count = len(set(str(c.ip_address) for c in active_connections))

        # Время в нарушении (секунды)
        violation_duration_sec = 0
        if violation_start_time:
            violation_duration_sec = int((now - violation_start_time).total_seconds())

        # Время в Москве (UTC+3)
        moscow_time = now + timedelta(hours=3)
        moscow_time_str = moscow_time.strftime("%d.%m.%Y %H:%M:%S")

        # Собираем уникальные IP и ноды
        unique_ips = set()
        node_uuids = set()
        if active_connections:
            for conn in active_connections:
                unique_ips.add(str(conn.ip_address))
                if hasattr(conn, 'node_uuid') and conn.node_uuid:
                    node_uuids.add(conn.node_uuid)

        # Получаем имена нод по UUID
        nodes_used = set()
        if node_uuids:
            try:
                from shared.database import db_service
                for node_uuid in node_uuids:
                    node_info = await db_service.get_node_by_uuid(node_uuid)
                    if node_info and node_info.get("name"):
                        nodes_used.add(node_info.get("name"))
                    else:
                        nodes_used.add(node_uuid[:8])  # Короткий UUID если имя недоступно
            except Exception as node_error:
                logger.debug("Failed to get node names: %s", node_error)
                # Используем короткие UUID
                nodes_used = {uuid[:8] for uuid in node_uuids}

        # Собираем информацию об устройствах (конкретные ОС и клиенты)
        os_list = []
        client_list = []
        if breakdown and "device" in breakdown:
            device_data = breakdown["device"]
            if isinstance(device_data, dict):
                os_list = device_data.get("os_list") or []
                client_list = device_data.get("client_list") or []
            elif hasattr(device_data, 'os_list'):
                os_list = device_data.os_list or []
                client_list = getattr(device_data, 'client_list', None) or []

        # Формируем сообщение
        lines = []
        lines.append("🚨 <b>НАРУШИТЕЛЬ ЛИМИТА</b>")
        lines.append("")

        # Информация о пользователе
        if email:
            lines.append(f"📧 Email: <code>{_esc(email)}</code>")
        else:
            lines.append(f"📧 Username: <code>{_esc(username)}</code>")

        if telegram_id is not None:
            lines.append(f"📱 TG ID: <code>{telegram_id}</code>")

        if description:
            lines.append(f"📝 Описание: <code>{_esc(description[:100])}</code>")

        lines.append("")

        # IP адреса
        lines.append(f"🌐 IP адресов: <b>{ip_count}/{device_limit}</b>")

        if unique_ips:
            lines.append("📍 IP (провайдеры):")
            for ip in sorted(unique_ips):
                provider_info = ""
                country_code = ""
                if ip_metadata and ip in ip_metadata:
                    meta = ip_metadata[ip]
                    if hasattr(meta, 'asn_org') and meta.asn_org:
                        # Преобразуем техническое название в понятное
                        provider_info = format_provider_name(meta.asn_org)
                    if hasattr(meta, 'country_code') and meta.country_code:
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

        # Ноды
        if nodes_used:
            nodes_str = ", ".join(sorted(nodes_used))
            lines.append(f"🖥 Ноды: <code>{_esc(nodes_str)}</code>")

        lines.append("")

        # Получаем HWID устройства из БД
        hwid_devices = []
        try:
            from shared.database import db_service
            hwid_devices = await db_service.get_user_hwid_devices(user_uuid)
        except Exception as hwid_error:
            logger.debug("Failed to get HWID devices for user %s: %s", user_uuid, hwid_error)

        # Устройства (HWID из БД)
        if hwid_devices:
            hwid_count = len(hwid_devices)
            device_parts = []
            for device in hwid_devices[:5]:  # Показываем максимум 5 устройств
                platform = device.get("platform", "unknown")
                os_version = device.get("os_version", "")
                app_version = device.get("app_version", "")

                # Форматируем название платформы
                platform_names = {
                    "android": "Android",
                    "ios": "iOS",
                    "windows": "Windows",
                    "macos": "macOS",
                    "linux": "Linux",
                }
                platform_display = platform_names.get(platform.lower(), platform) if platform else "Unknown"

                # Собираем строку устройства
                device_str = platform_display
                if os_version:
                    device_str += f" {os_version}"
                if app_version:
                    device_str += f" (v{app_version})"

                device_parts.append(device_str)

            if hwid_count > 5:
                device_parts.append(f"... и ещё {hwid_count - 5}")

            lines.append(f"📲 Устройства ({hwid_count}/{device_limit}):")
            for part in device_parts:
                lines.append(f"   {_esc(part)}")
        else:
            # Если нет HWID устройств, показываем данные из breakdown (ОС и клиенты из user-agent)
            if os_list or client_list:
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
                    lines.append(f"📲 Устройства (по UA): {'; '.join(device_parts)}")
                else:
                    lines.append(f"📲 Устройства: —")
            else:
                lines.append(f"📲 Устройства: —")

        # Время в нарушении
        if violation_duration_sec > 0:
            lines.append(f"⏱ В нарушении: <code>{violation_duration_sec} сек</code>")

        # Скор нарушения
        lines.append(f"📊 Скор: <code>{total_score:.1f}/100</code>")

        # Время
        lines.append(f"🕐 Время (МСК): <code>{moscow_time_str}</code>")

        text = "\n".join(lines)

        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="👤 Подробнее", callback_data=f"vact:info:{user_uuid}"),
                InlineKeyboardButton(text="🔒 Заблокировать", callback_data=f"vact:block:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text="⛔ Откл + разорвать", callback_data=f"vact:kill:{user_uuid}"),
                InlineKeyboardButton(text="🔄 Сбросить трафик", callback_data=f"vact:reset:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text="🚫 Аннулировать", callback_data=f"vact:dismiss:{user_uuid}"),
            ],
        ])

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await bot.send_message(**message_kwargs)

        # Обновляем кэш после успешной отправки
        _violation_notification_cache[user_uuid] = datetime.utcnow()

        logger.info(
            "Violation notification sent successfully user_uuid=%s score=%.1f ip_count=%d topic_id=%s",
            user_uuid,
            total_score,
            ip_count,
            topic_id
        )

    except Exception as exc:
        logger.exception(
            "Failed to send violation notification user_uuid=%s error=%s",
            user_uuid,
            exc
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
