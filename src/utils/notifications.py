"""Утилиты для отправки уведомлений в Telegram топики."""
from datetime import datetime, timedelta
from typing import Dict

from aiogram import Bot
from aiogram.types import Message

from src.config import get_settings
from src.utils.formatters import format_bytes, format_datetime
from src.utils.logger import logger


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
        from src.services.api_client import api_client
        squads_res = await api_client.get_internal_squads()
        all_squads = squads_res.get("response", {}).get("internalSquads", [])
        # Ищем сквад по UUID
        for squad in all_squads:
            if squad.get("uuid") == squad_uuid:
                return squad.get("name", squad_uuid[:8] + "...")
        # Если не нашли, возвращаем короткий UUID
        return squad_uuid[:8] + "..."
    except Exception as exc:
        logger.debug("Failed to get squad name from API for uuid=%s: %s", squad_uuid, exc)
        # Если не удалось получить из API, возвращаем короткий UUID
        return squad_uuid[:8] + "..."


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
            lines.append(f"   UUID: <code>{user_uuid[:8]}...</code>")
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
        
        squad_display = "—"
        if active_squads:
            first_squad = active_squads[0]
            if isinstance(first_squad, dict):
                squad_uuid = first_squad.get("uuid", "")
                squad_name = first_squad.get("name")
                if squad_name:
                    squad_display = squad_name
                elif squad_uuid:
                    squad_display = await _get_squad_name_by_uuid(squad_uuid)
            else:
                squad_info = info.get("internalSquads", [])
                if squad_info and isinstance(squad_info, list) and len(squad_info) > 0:
                    squad_display = squad_info[0].get("name", first_squad)
                else:
                    squad_display = await _get_squad_name_by_uuid(first_squad)
        elif external_squad:
            squad_display = f"External: {external_squad[:8]}..."
        
        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            old_active_squads = old_info.get("activeInternalSquads", [])
            old_external_squad = old_info.get("externalSquadUuid")
            
            old_squad_display = "—"
            if old_active_squads:
                old_first_squad = old_active_squads[0]
                if isinstance(old_first_squad, dict):
                    old_squad_uuid = old_first_squad.get("uuid", "")
                    old_squad_name = old_first_squad.get("name")
                    if old_squad_name:
                        old_squad_display = old_squad_name
                    elif old_squad_uuid:
                        old_squad_display = await _get_squad_name_by_uuid(old_squad_uuid)
                else:
                    old_squad_info = old_info.get("internalSquads", [])
                    if old_squad_info and isinstance(old_squad_info, list) and len(old_squad_info) > 0:
                        old_squad_display = old_squad_info[0].get("name", old_first_squad)
                    else:
                        old_squad_display = await _get_squad_name_by_uuid(old_first_squad)
            elif old_external_squad:
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
        hwid_data = event_data.get("hwidDevice", {})
        
        if user_data:
            username = user_data.get("username", "n/a")
            user_uuid = user_data.get("uuid", "n/a")
            lines.append(f"👤 <b>Пользователь:</b> <code>{_esc(username)}</code>")
            lines.append(f"🆔 <b>UUID:</b> <code>{user_uuid[:8]}...</code>")
        
        if hwid_data:
            hwid = hwid_data.get("hwid", "—")
            created_at = hwid_data.get("createdAt")
            if hwid != "—":
                lines.append(f"💻 <b>HWID:</b> <code>{_esc(hwid[:40])}...</code>")
            if created_at:
                lines.append(f"📅 <b>Создано:</b> <code>{format_datetime(created_at)}</code>")
        
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
        
        # Информация о ноде
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
                lines.append(f"   UUID: <code>{node_uuid[:8]}...</code>")
            if node_address:
                lines.append(f"   Адрес: <code>{_esc(node_address)}</code>")
            if node_port:
                lines.append(f"   Порт: <code>{node_port}</code>")
            if node_country:
                lines.append(f"   Страна: <code>{node_country}</code>")
            lines.append("")
        
        # Информация о провайдере
        if provider_data:
            lines.append("🏢 <b>Провайдер</b>")
            provider_name = provider_data.get("name", "n/a")
            provider_uuid = provider_data.get("uuid", "")
            lines.append(f"   Название: <code>{_esc(provider_name)}</code>")
            if provider_uuid:
                lines.append(f"   UUID: <code>{provider_uuid[:8]}...</code>")
            lines.append("")
        
        # Информация об оплате
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
            from src.services.database import db_service
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
                from src.services.database import db_service
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
                        provider_info = meta.asn_org
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

        # Устройства (конкретные ОС и клиенты)
        if os_list or client_list:
            # Формируем строку с комбинацией ОС и клиентов
            device_parts = []
            if os_list and client_list and len(os_list) == len(client_list):
                # Если количество ОС и клиентов совпадает, объединяем их
                for i, os_name in enumerate(os_list):
                    client_name = client_list[i] if i < len(client_list) else ""
                    if client_name:
                        device_parts.append(f"{os_name} ({client_name})")
                    else:
                        device_parts.append(os_name)
            else:
                # Выводим отдельно
                if os_list:
                    device_parts.append(f"ОС: {', '.join(os_list)}")
                if client_list:
                    device_parts.append(f"Клиенты: {', '.join(client_list)}")

            if device_parts:
                lines.append(f"📲 Устройства: {'; '.join(device_parts)}")
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

        message_kwargs = {
            "chat_id": settings.notifications_chat_id,
            "text": text,
            "parse_mode": "HTML",
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
