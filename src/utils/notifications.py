"""Утилиты для отправки уведомлений в Telegram топики."""
from datetime import datetime

from aiogram import Bot
from aiogram.types import Message

from src.config import get_settings
from src.utils.formatters import format_bytes, format_datetime
from src.utils.logger import logger


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
