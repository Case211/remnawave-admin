"""Утилиты для отправки уведомлений в Telegram топики."""
import asyncio
import io
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import qrcode
from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

from src.config import get_settings
from src.utils.formatters import format_bytes, format_datetime, format_provider_name
from src.utils.i18n import tr
from shared.logger import logger
from shared.notification_config import (
    is_notification_type_enabled,
    resolve_notification_topic,
    resolve_notifications_chat_id,
)


def _strip_html(text: str) -> str:
    """Чистим HTML-теги из текста — для FCM payload, который читается как plain text."""
    return re.sub(r"<[^>]+>", "", text)


async def _send_card(bot: Bot, message_kwargs: Dict[str, Any]) -> None:
    """Отправить карточку уведомления rich-сообщением (Bot API 10.1).

    Первая строка становится настоящим заголовком, поля с отступом — списком.
    При отказе rich-пути (или выключенном тумблере notifications_rich_enabled)
    внутри send_rich_or_html срабатывает фолбэк на обычный HTML — уведомление
    доходит в любом случае. aiogram у бота старый (3.12, без Rich-типов),
    поэтому шлём raw-запросом с токеном бота.
    """
    from shared import tg_rich

    reply_markup = message_kwargs.get("reply_markup")
    if reply_markup is not None and hasattr(reply_markup, "model_dump"):
        reply_markup = reply_markup.model_dump(exclude_none=True, by_alias=True)

    await tg_rich.send_rich_or_html(
        bot.token,
        message_kwargs["chat_id"],
        message_kwargs["text"],
        message_thread_id=message_kwargs.get("message_thread_id"),
        reply_markup=reply_markup,
    )


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


async def _local_user_uuid(info: dict) -> Optional[str]:
    """Local user uuid for a payload — v2 sends uuid, panel v3 sends numeric id."""
    from shared.data_access import resolve_local_user_uuid
    return await resolve_local_user_uuid(info)


def _short_user_id(info: dict, local_uuid: Optional[str]) -> str:
    """Короткий идентификатор юзера для карточки уведомления."""
    display = local_uuid or info.get("uuid") or info.get("id") or ""
    return str(display)[:8]


async def send_user_notification(
    bot: Bot,
    action: str,  # "created", "updated", "deleted", "expired", "expires_in_*", etc.
    user_info: dict,
    old_user_info: dict | None = None,
    changes: list | None = None,  # Список изменений из sync_service
    event_type: str | None = None,  # Оригинальный тип события из webhook
    subscription_url: str | None = None,  # Для QR-кода при создании
) -> None:
    """Отправляет уведомление о действии с пользователем в Telegram топик."""
    settings = get_settings()

    if not is_notification_type_enabled("users"):
        logger.debug("User notifications disabled in dynamic settings")
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return  # Уведомления отключены

    topic_id = resolve_notification_topic(
        "users",
        type_fallback=settings.notifications_topic_users,
        general_fallback=settings.notifications_topic_id,
    )
    logger.debug(
        "Sending user notification action=%s chat_id=%s topic_id=%s",
        action,
        chat_id,
        topic_id,
    )
    
    try:
        info = user_info.get("response", user_info)
        local_uuid = await _local_user_uuid(info)

        lines = []

        # Заголовок уведомления в зависимости от типа события.
        # Если ключ не найден в локали, `tr()` вернёт сам ключ — это
        # используем как маркер отсутствия и берём fallback.
        title_value = tr(f"notify.user.title.{action}")
        if title_value == f"notify.user.title.{action}":
            title_value = tr("notify.user.fallback")
        lines.append(title_value)
        lines.append("")

        # Идентификация
        lines.append(f"👤 <code>{_esc(info.get('username', 'n/a'))}</code>  <code>{_short_user_id(info, local_uuid)}</code>")
        lines.append("")

        # Для updated: показываем только изменившиеся поля (diff)
        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            diff_lines = []

            unlimited = tr("notify.user.label.unlimited")

            def _fmt_unlimited(v):
                return format_bytes(v) if v else unlimited

            diff_fields = [
                ("trafficLimitBytes", tr("notify.user.field.traffic_limit"), _fmt_unlimited),
                ("expireAt", tr("notify.user.field.expire"), lambda v: format_datetime(v) if v else "—"),
                ("trafficLimitStrategy", tr("notify.user.field.strategy"), lambda v: v or "NO_RESET"),
                ("hwidDeviceLimit", tr("notify.user.field.hwid_limit"), lambda v: unlimited if v == 0 else str(v) if v is not None else "—"),
                ("status", tr("notify.user.field.status"), lambda v: str(v) if v else "—"),
                ("description", tr("notify.user.field.description"), lambda v: _esc(str(v)[:60]) if v else "—"),
                ("telegramId", tr("notify.user.field.telegram_id"), lambda v: str(v) if v is not None else "—"),
                ("email", tr("notify.user.field.email"), lambda v: _esc(str(v)) if v else "—"),
                ("tag", tr("notify.user.field.tag"), lambda v: _esc(str(v)) if v else "—"),
            ]

            for key, label, fmt in diff_fields:
                old_val = old_info.get(key)
                new_val = info.get(key)
                if old_val != new_val:
                    # новое значение — жирным: взгляд сразу цепляется за итог
                    diff_lines.append(f"   {label}: <code>{fmt(old_val)}</code> → <b><code>{fmt(new_val)}</code></b>")

            # Сквад diff
            active_squads = info.get("activeInternalSquads", [])
            old_active_squads = old_info.get("activeInternalSquads", [])
            if active_squads != old_active_squads:
                old_sq = await _resolve_squads_display(old_active_squads)
                new_sq = await _resolve_squads_display(active_squads)
                if old_sq != new_sq:
                    diff_lines.append(f"   {tr('notify.user.field.squad')}: <code>{old_sq}</code> → <code>{new_sq}</code>")

            if diff_lines:
                lines.append(tr("notify.user.section.changes"))
                lines.extend(diff_lines)
            elif changes:
                lines.append(tr("notify.user.section.changes"))
                for change in changes:
                    lines.append(f"   {_esc(change)}")
            else:
                lines.append(tr("notify.user.section.no_changes"))

            # Краткая карточка с основными полями — сворачиваемой секцией:
            # diff главный, контекст не должен занимать пол-экрана простынёй.
            # В rich это details, в HTML-фолбэке — expandable-цитата.
            lines.append("")
            card_parts = []
            status = info.get("status")
            if status:
                card_parts.append(f"{tr('notify.user.field.status')}: <code>{status}</code>")
            traffic_limit = info.get("trafficLimitBytes")
            card_parts.append(f"{tr('notify.user.label.limit')}: <code>{format_bytes(traffic_limit) if traffic_limit else unlimited}</code>")
            expire_at = info.get("expireAt")
            if expire_at:
                card_parts.append(f"{tr('notify.user.label.expires')}: <code>{format_datetime(expire_at)}</code>")
            telegram_id = info.get("telegramId")
            if telegram_id is not None:
                card_parts.append(f"TG: <code>{telegram_id}</code>")
            email = info.get("email")
            if email:
                card_parts.append(f"{tr('notify.user.field.email')}: <code>{_esc(email)}</code>")
            description = info.get("description")
            if description:
                card_parts.append(f"{tr('notify.user.field.description')}: <code>{_esc(description[:50])}</code>")
            lines.append("<blockquote expandable>" + tr("notify.user.section.card")
                         + "\n" + "\n".join(card_parts) + "</blockquote>")

        else:
            # Для created/deleted/other: полная информация
            lines.append(tr("notify.user.section.traffic_limits"))
            traffic_limit = info.get("trafficLimitBytes")
            unlimited = tr("notify.user.label.unlimited")
            lines.append(f"   {tr('notify.user.label.limit')}: <code>{format_bytes(traffic_limit) if traffic_limit else unlimited}</code>")
            expire_at = info.get("expireAt")
            lines.append(f"   {tr('notify.user.label.expires')}: <code>{format_datetime(expire_at) if expire_at else '—'}</code>")
            lines.append(f"   {tr('notify.user.label.reset')}: <code>{info.get('trafficLimitStrategy') or 'NO_RESET'}</code>")
            hwid_limit = info.get("hwidDeviceLimit")
            if hwid_limit is not None:
                lines.append(f"   {tr('notify.user.label.hwid')}: <code>{unlimited if hwid_limit == 0 else hwid_limit}</code>")
            lines.append("")

            subscription_url = info.get("subscriptionUrl")
            if subscription_url:
                url_display = _esc(subscription_url[:80]) + ("..." if len(subscription_url) > 80 else "")
                lines.append(tr("notify.user.subscription_link", url=url_display))

            active_squads = info.get("activeInternalSquads", [])
            squad_display = await _resolve_squads_display(active_squads)
            external_squad = info.get("externalSquadUuid")
            if squad_display == "—" and external_squad:
                squad_display = tr("notify.user.external_squad", uuid=external_squad[:8])
            if squad_display != "—":
                lines.append(f"   {tr('notify.user.label.squad')}: <code>{squad_display}</code>")

            telegram_id = info.get("telegramId")
            email = info.get("email")
            if telegram_id is not None:
                lines.append(f"📞 {tr('notify.user.label.telegram')}: <code>{telegram_id}</code>")
            if email:
                lines.append(f"📧 {tr('notify.user.field.email')}: <code>{_esc(email)}</code>")

            description = info.get("description")
            if description:
                lines.append(f"📝 <code>{_esc(description[:100])}</code>")
        
        text = "\n".join(lines)

        # Для "created" отправляем фото с QR-кодом и полным текстом в caption
        if action == "created" and subscription_url:
            try:
                qr_buf = io.BytesIO()
                qrcode.make(subscription_url, box_size=8, border=2).save(qr_buf, format='PNG')
                qr_buf.seek(0)
                photo_kwargs = {
                    "chat_id": chat_id,
                    "photo": BufferedInputFile(qr_buf.read(), filename="subscription.png"),
                    "caption": text,
                    "parse_mode": "HTML",
                }
                if topic_id is not None:
                    photo_kwargs["message_thread_id"] = topic_id
                await bot.send_photo(**photo_kwargs)
                logger.info("User created notification with QR sent successfully chat_id=%s", chat_id)
                return
            except Exception as e:
                logger.warning("Failed to send QR photo, falling back to text: %s", e)
                # Fall through to text message

        # Отправляем в топик
        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        # Добавляем message_thread_id только если он указан
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)
        logger.info("User notification sent successfully action=%s chat_id=%s", action, chat_id)

        # Маппинг коротких action-имён → event_id из catalog
        # (shared/notification_events.py). Без этого fallback `user.{action}`
        # генерил event_id, не совпадающий с тем, что мобильник кладёт в
        # disabled_events — фильтр пропускал пуши, отключённые в UI.
        # Mismatch'и были у `updated` (catalog: user.modified) и
        # `bandwidth_threshold` (catalog: user.bandwidth_usage_threshold_reached).
        action_to_event = {
            "updated": "user.modified",
            "expires_in_72h": "user.expires_in_72_hours",
            "expires_in_48h": "user.expires_in_48_hours",
            "expires_in_24h": "user.expires_in_24_hours",
            "expired_24h_ago": "user.expired_24_hours_ago",
            "bandwidth_threshold": "user.bandwidth_usage_threshold_reached",
        }
        event_id = action_to_event.get(action, f"user.{action}")
        push_title = tr(f"notify.push.user.{action}")
        if push_title == f"notify.push.user.{action}":
            push_title = tr("notify.push.user.fallback", action=action)
        _push_dispatch(
            title=push_title,
            body=info.get("username") or _short_user_id(info, local_uuid),
            notification_type="info",
            source="panel.webhook",
            source_id=local_uuid,
            event=event_id,
        )

    except Exception as exc:
        logger.exception(
            "Failed to send user notification action=%s user_uuid=%s chat_id=%s topic_id=%s error=%s",
            action,
            local_uuid or info.get("id", "unknown"),
            chat_id,
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

    notification_type = topic_type or "service"
    if not is_notification_type_enabled(notification_type):
        logger.debug("Generic %s notifications disabled in dynamic settings", notification_type)
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_fallbacks = {
        "users": settings.notifications_topic_users,
        "nodes": settings.notifications_topic_nodes,
        "service": settings.notifications_topic_service,
        "hwid": settings.notifications_topic_hwid,
        "crm": settings.notifications_topic_crm,
        "errors": settings.notifications_topic_errors,
        "violations": settings.notifications_topic_violations,
    }
    topic_id = resolve_notification_topic(
        notification_type,
        type_fallback=topic_fallbacks.get(notification_type),
        general_fallback=settings.notifications_topic_id,
    )

    try:
        text = f"{emoji} <b>{title}</b>\n\n{message}"

        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)
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

    if not is_notification_type_enabled("nodes"):
        logger.debug("Node notifications disabled in dynamic settings")
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = resolve_notification_topic(
        "nodes",
        type_fallback=settings.notifications_topic_nodes,
        general_fallback=settings.notifications_topic_id,
    )

    try:
        node_info = node_data.get("response", node_data) if isinstance(node_data, dict) else node_data

        lines = []

        # Определяем заголовок по типу события
        title_key = f"notify.node.title.{event}"
        title_value = tr(title_key)
        if title_value == title_key:
            title_value = tr("notify.node.fallback", event=event)
        lines.append(title_value)
        lines.append("")

        # Информация о ноде
        node_name = node_info.get("name", "n/a")
        node_uuid = node_info.get("uuid", "n/a")
        address = node_info.get("address", "—")
        port = node_info.get("port", "—")
        country = node_info.get("countryCode", "—")
        status = node_info.get("status", "—")

        lines.append(f"🖥 <b>{_esc(node_name)}</b>  <code>{node_uuid[:8]}</code>")
        addr_str = f"{_esc(str(address))}:{port}" if port != "—" else _esc(str(address))
        lines.append(f"   {tr('notify.node.label.address')}: <code>{addr_str}</code>  {country if country != '—' else ''}")
        if status != "—":
            lines.append(f"   📊 {tr('notify.node.label.status')}: <code>{status}</code>")

        # Трафик (если есть)
        traffic_limit = node_info.get("trafficLimitBytes")
        if traffic_limit:
            lines.append(f"   📶 {tr('notify.node.label.traffic_limit')}: <code>{format_bytes(traffic_limit)}</code>")

        # Секция изменений
        if changes and event == "node.modified":
            lines.append("")
            lines.append(tr("notify.node.label.changes"))
            for change in changes:
                lines.append(f"   {_esc(change)}")

        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)
        logger.info("Node notification sent successfully event=%s node_uuid=%s topic_id=%s", event, node_uuid, topic_id)

        # FCM push: критичные события про ноды отправляем как category=alerts,
        # обычные изменения — как info. node.connection_lost = 🔴 → severity critical.
        critical_events = {"node.connection_lost", "node.disabled", "node.deleted"}
        push_severity = "critical" if event in critical_events else "info"
        push_type = "alert" if event in critical_events else "info"
        push_title = tr(title_key)
        if push_title == title_key:
            push_title = tr("notify.push.node_fallback")
        _push_dispatch(
            title=push_title,
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

    if not is_notification_type_enabled("service"):
        logger.debug("Service notifications disabled in dynamic settings")
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = resolve_notification_topic(
        "service",
        type_fallback=settings.notifications_topic_service,
        general_fallback=settings.notifications_topic_id,
    )

    try:
        lines = []

        title_key = f"notify.service.title.{event}"
        title_value = tr(title_key)
        if title_value == title_key:
            title_value = tr("notify.service.fallback", event=event)
        lines.append(title_value)
        lines.append("")

        # Дополнительная информация
        if event == "service.login_attempt_failed" or event == "service.login_attempt_success":
            # Remnawave вкладывает поля под data.loginAttempt (не на верхнем уровне)
            la = event_data.get("loginAttempt")
            la = la if isinstance(la, dict) else event_data
            username = la.get("username") or "—"
            ip = la.get("ip") or "—"
            user_agent = la.get("userAgent") or "—"
            description = la.get("description") or "—"

            lines.append(f"   {tr('notify.service.login.username', username=_esc(username))}")
            if ip != "—":
                lines.append(f"   {tr('notify.service.login.ip', ip=_esc(ip))}")
            if user_agent != "—":
                lines.append(f"   {tr('notify.service.login.user_agent', user_agent=_esc(user_agent[:200]))}")
            if description != "—":
                lines.append(f"   {tr('notify.service.login.description', description=_esc(description))}")
        elif event == "panel.unavailable":
            error_type = event_data.get("error_type", "—")
            error_message = event_data.get("error_message", "—")
            consecutive_failures = event_data.get("consecutive_failures", 0)
            last_check = event_data.get("last_check", "—")

            lines.append(f"   {tr('notify.service.panel_unavailable.error_type', error_type=_esc(error_type))}")
            if error_message != "—":
                lines.append(f"   {tr('notify.service.panel_unavailable.error_message', error_message=_esc(error_message[:100]))}")
            lines.append(f"   {tr('notify.service.panel_unavailable.failures', count=consecutive_failures)}")
            if last_check != "—":
                lines.append(f"   {tr('notify.service.panel_unavailable.last_check', last_check=last_check)}")

        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)
        logger.info("Service notification sent successfully event=%s topic_id=%s", event, topic_id)

        # Сервисные события (бэкап, рестарт панели и т.п.) — alert-категория,
        # они интересны на телефоне даже когда ты не у компа.
        _push_dispatch(
            title=tr("notify.push.service_title", event=event),
            body=tr("notify.push.service_body", event=event),
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

    if not is_notification_type_enabled("hwid"):
        logger.debug("HWID notifications disabled in dynamic settings")
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = resolve_notification_topic(
        "hwid",
        type_fallback=settings.notifications_topic_hwid,
        general_fallback=settings.notifications_topic_id,
    )

    try:
        lines = []

        title_key = f"notify.hwid.title.{event}"
        title_value = tr(title_key)
        if title_value == title_key:
            title_value = tr("notify.hwid.fallback", event=event)
        lines.append(title_value)
        lines.append("")

        # Информация о пользователе
        user_data = event_data.get("user", {})
        # Webhook может прислать hwidDevice или hwidUserDevice
        hwid_data = event_data.get("hwidDevice", {}) or event_data.get("hwidUserDevice", {})

        user_local_uuid = await _local_user_uuid(user_data) if user_data else None

        if user_data:
            username = user_data.get("username", "n/a")
            user_uuid = user_data.get("uuid") or user_local_uuid or user_data.get("id", "n/a")
            telegram_id = user_data.get("telegramId")
            status = user_data.get("status", "—")
            description = user_data.get("description", "")
            hwid_device_limit = user_data.get("hwidDeviceLimit", 0)

            lines.append(f"{tr('notify.hwid.label.user', username=_esc(username))}  <code>{_short_user_id(user_data, user_local_uuid)}</code>")
            if telegram_id is not None:
                lines.append(f"   {tr('notify.hwid.label.tg_id', telegram_id=telegram_id)}")

            lines.append(f"   {tr('notify.hwid.label.status', status=status)}")

            if description:
                lines.append(f"   {tr('notify.hwid.label.description', description=_esc(description[:100]))}")

            # Информация о лимите устройств
            limit_display = "∞" if hwid_device_limit == 0 else str(hwid_device_limit)
            lines.append(f"   {tr('notify.hwid.label.device_limit', limit=limit_display)}")

            lines.append("")

        if hwid_data:
            lines.append(tr("notify.hwid.device_header"))
            hwid = hwid_data.get("hwid", "—")
            platform = hwid_data.get("platform", "—")
            os_version = hwid_data.get("osVersion", "—")
            device_model = hwid_data.get("deviceModel", "—")
            user_agent = hwid_data.get("userAgent", "—")
            created_at = hwid_data.get("createdAt")

            if hwid != "—":
                lines.append(f"   {tr('notify.hwid.device.hwid', hwid=_esc(hwid))}")
            if platform != "—":
                lines.append(f"   {tr('notify.hwid.device.platform', platform=_esc(platform))}")
            if os_version != "—":
                lines.append(f"   {tr('notify.hwid.device.os_version', os_version=_esc(os_version))}")
            if device_model != "—":
                lines.append(f"   {tr('notify.hwid.device.model', model=_esc(device_model))}")
            if user_agent != "—":
                lines.append(f"   {tr('notify.hwid.device.user_agent', user_agent=_esc(user_agent[:60]))}")
            if created_at:
                lines.append(f"   {tr('notify.hwid.device.added', created_at=format_datetime(created_at))}")
        
        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)
        logger.info("HWID notification sent successfully event=%s topic_id=%s", event, topic_id)

        # FCM push: соответствует событиям user_hwid_devices.added/.deleted в
        # каталоге shared/notification_events.py. Открываем карточку юзера —
        # там видно весь список устройств. Для type="user" RemnawavePushService
        # построит deeplink users/{uuid}, потому что event_id "user_hwid_devices.*"
        # не подходит под startsWith("user.") (нет точки после user).
        username = user_data.get("username") if user_data else None
        user_uuid = user_data.get("uuid") if user_data else None
        if not user_uuid:
            user_uuid = user_local_uuid
        platform = hwid_data.get("platform") if hwid_data else None
        if event == "user_hwid_devices.added":
            action_label = tr("notify.hwid.action.added")
        elif event == "user_hwid_devices.deleted":
            action_label = tr("notify.hwid.action.deleted")
        else:
            action_label = tr("notify.hwid.action.fallback", event=event)
        body_parts = []
        if username:
            body_parts.append(str(username))
        if platform:
            body_parts.append(str(platform))
        push_body = " · ".join(body_parts) if body_parts else action_label
        _push_dispatch(
            title=action_label,
            body=push_body,
            notification_type="user",
            source="panel.webhook",
            source_id=user_uuid,
            severity="info",
            event=event,
        )

    except Exception as exc:
        logger.exception("Failed to send HWID notification event=%s error=%s", event, exc)


async def send_error_notification(
    bot: Bot,
    event: str,
    event_data: dict,
) -> None:
    """Отправляет уведомление об ошибке."""
    settings = get_settings()

    if not is_notification_type_enabled("errors"):
        logger.debug("Error notifications disabled in dynamic settings")
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = resolve_notification_topic(
        "errors",
        type_fallback=settings.notifications_topic_errors,
        general_fallback=settings.notifications_topic_id,
    )

    try:
        lines = []

        lines.append(tr("notify.error.title"))
        lines.append("")
        lines.append(f"   {tr('notify.error.type', event=_esc(event))}")

        # Дополнительная информация
        message = event_data.get("message", "")
        if message:
            lines.append(f"   {tr('notify.error.message', message=_esc(message))}")

        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)
        logger.info("Error notification sent successfully event=%s topic_id=%s", event, topic_id)

        # Ошибки/системные алерты обязательно пушим — это то, ради чего пуши и нужны.
        _push_dispatch(
            title=tr("notify.push.error_title", event=event),
            body=tr("notify.push.error_body", event=event),
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

    if not is_notification_type_enabled("crm"):
        logger.debug("CRM notifications disabled in dynamic settings")
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
        logger.debug("Notifications disabled: NOTIFICATIONS_CHAT_ID not set")
        return

    topic_id = resolve_notification_topic(
        "crm",
        type_fallback=settings.notifications_topic_crm,
        general_fallback=settings.notifications_topic_id,
    )

    try:
        lines = []

        title_key = f"notify.crm.title.{event}"
        title_value = tr(title_key)
        if title_value == title_key:
            title_value = tr("notify.crm.fallback", event=event)
        lines.append(title_value)
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
            lines.append(tr("notify.crm.section.node"))
            if node_name:
                lines.append(f"   {tr('notify.crm.label.name')}: <code>{_esc(node_name)}</code>")
            lines.append("")

            if provider_name:
                lines.append(tr("notify.crm.section.provider"))
                lines.append(f"   {tr('notify.crm.label.name')}: <code>{_esc(provider_name)}</code>")
                if login_url:
                    lines.append(f"   {tr('notify.crm.label.login_url', url=_esc(login_url))}")
                lines.append("")

            if next_billing_at:
                lines.append(tr("notify.crm.section.billing"))
                lines.append(f"   {tr('notify.crm.label.next_billing', date=format_datetime(next_billing_at))}")
        else:
            # Вложенный формат (для совместимости)
            node_data = event_data.get("node", {})
            provider_data = event_data.get("provider", {})
            billing_data = event_data.get("billingNode", {})

            if node_data:
                lines.append(tr("notify.crm.section.node"))
                node_name = node_data.get("name", "n/a")
                node_uuid = node_data.get("uuid", "")
                node_address = node_data.get("address", "")
                node_port = node_data.get("port")
                node_country = node_data.get("countryCode", "")

                lines.append(f"   {tr('notify.crm.label.name')}: <code>{_esc(node_name)}</code>")
                if node_uuid:
                    lines.append(f"   {tr('notify.crm.label.uuid')}: <code>{node_uuid}</code>")
                if node_address:
                    lines.append(f"   {tr('notify.crm.label.address')}: <code>{_esc(node_address)}</code>")
                if node_port:
                    lines.append(f"   {tr('notify.crm.label.port')}: <code>{node_port}</code>")
                if node_country:
                    lines.append(f"   {tr('notify.crm.label.country')}: <code>{node_country}</code>")
                lines.append("")

            if provider_data:
                lines.append(tr("notify.crm.section.provider"))
                provider_name = provider_data.get("name", "n/a")
                provider_uuid = provider_data.get("uuid", "")
                lines.append(f"   {tr('notify.crm.label.name')}: <code>{_esc(provider_name)}</code>")
                if provider_uuid:
                    lines.append(f"   {tr('notify.crm.label.uuid')}: <code>{provider_uuid}</code>")
                lines.append("")

            if billing_data:
                lines.append(tr("notify.crm.section.billing"))
                amount = billing_data.get("amount")
                currency = billing_data.get("currency", "")
                next_billing_at = billing_data.get("nextBillingAt")
                last_billing_at = billing_data.get("lastBillingAt")
                billing_interval = billing_data.get("billingInterval", "")

                if amount is not None:
                    amount_str = f"{amount}"
                    if currency:
                        amount_str += f" {currency}"
                    lines.append(f"   {tr('notify.crm.label.amount')}: <code>{amount_str}</code>")
                if billing_interval:
                    lines.append(f"   {tr('notify.crm.label.interval')}: <code>{billing_interval}</code>")
                if next_billing_at:
                    lines.append(f"   {tr('notify.crm.label.next_billing', date=format_datetime(next_billing_at))}")
                if last_billing_at:
                    lines.append(f"   {tr('notify.crm.label.last_billing', date=format_datetime(last_billing_at))}")

        text = "\n".join(lines)

        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)
        logger.info("CRM notification sent successfully event=%s topic_id=%s", event, topic_id)

    except Exception as exc:
        logger.exception("Failed to send CRM notification event=%s error=%s", event, exc)


# Ключи анализаторов в breakdown совпадают с теми, что понимает
# excluded_analyzers в violation_whitelist — на этом и держится кнопка
# частичного исключения.
VIOLATION_ANALYZERS = ("temporal", "geo", "asn", "profile", "device", "hwid", "user_agent")


def _analyzer_score(entry: Any) -> float:
    """Вклад анализатора. Breakdown приходит и датаклассами, и словарями."""
    if isinstance(entry, dict):
        value = entry.get("score", 0)
    else:
        value = getattr(entry, "score", 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def dominant_analyzer(breakdown: dict | None) -> str | None:
    """Анализатор, давший наибольший вклад в скор, — по нему и предлагаем исключение.

    Нужен, чтобы кнопка под уведомлением вела в тот же разрез, что и само
    нарушение: сработал HWID — предлагаем не проверять по HWID, а не
    отключать человеку всю защиту разом. Ничего не набрало — None, тогда
    останется только полный белый список.
    """
    if not breakdown:
        return None
    scored = [(key, _analyzer_score(breakdown.get(key))) for key in VIOLATION_ANALYZERS if key in breakdown]
    if not scored:
        return None
    key, top = max(scored, key=lambda pair: pair[1])
    return key if top > 0 else None


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

    if not is_notification_type_enabled("violations"):
        logger.debug("Violation notifications disabled in dynamic settings")
        return

    chat_id = resolve_notifications_chat_id(settings.notifications_chat_id)
    if not chat_id:
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
    topic_id = resolve_notification_topic(
        "violations",
        type_fallback=settings.notifications_topic_violations,
        general_fallback=settings.notifications_topic_id,
    )

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

        # Формируем сообщение: заголовок → сводка (кто и насколько плохо) →
        # секции списками. Строки с «   »-отступом конвертер rich собирает
        # в аккуратные списки, секции — жирные строки-параграфы.
        lines = []
        lines.append(tr("notify.violation.title"))
        lines.append("")

        # Сводка — главное с первого взгляда
        lines.append(tr(
            "notify.violation.summary",
            username=_esc(username), score=f"{total_score:.0f}",
            count=ip_count, limit=device_limit,
        ))
        lines.append("")

        # Информация о пользователе — секция со списком полей
        user_lines = []
        if email:
            user_lines.append(f"   {tr('notify.violation.email', email=_esc(email))}")
        if telegram_id is not None:
            user_lines.append(f"   {tr('notify.violation.tg_id', telegram_id=telegram_id)}")
        if description:
            user_lines.append(f"   {tr('notify.violation.description', description=_esc(description[:100]))}")
        if user_lines:
            lines.append(tr("notify.violation.user_section"))
            lines.extend(user_lines)
            lines.append("")

        # IP адреса
        lines.append(tr("notify.violation.ip_count", count=ip_count, limit=device_limit))

        if unique_ips:
            lines.append(tr("notify.violation.ips_providers"))
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

                if provider_info and country_code:
                    lines.append(tr("notify.violation.ip_with_meta", ip=ip, provider=_esc(provider_info), country=country_code))
                elif country_code:
                    lines.append(tr("notify.violation.ip_with_country", ip=ip, country=country_code))
                elif provider_info:
                    lines.append(tr("notify.violation.ip_with_meta", ip=ip, provider=_esc(provider_info), country=""))
                else:
                    lines.append(tr("notify.violation.ip_bare", ip=ip))

        # Ноды — в тот же список, что и IP
        if nodes_used:
            nodes_str = ", ".join(sorted(nodes_used))
            lines.append(f"   {tr('notify.violation.nodes', nodes=_esc(nodes_str))}")

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
                platform_key = f"notify.violation.platform.{platform.lower()}" if platform else "notify.violation.platform.unknown"
                platform_display = tr(platform_key)
                if platform_display == platform_key:
                    platform_display = platform or tr("notify.violation.platform.unknown")

                # Собираем строку устройства
                device_str = platform_display
                if os_version:
                    device_str += f" {os_version}"
                if app_version:
                    device_str += f" (v{app_version})"

                device_parts.append(device_str)

            if hwid_count > 5:
                device_parts.append(tr("notify.violation.more_devices", count=hwid_count - 5))

            lines.append(tr("notify.violation.devices", count=hwid_count, limit=device_limit))
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
                        device_parts.append(tr("notify.violation.os_list", list=", ".join(os_list)))
                    if client_list:
                        device_parts.append(tr("notify.violation.client_list", list=", ".join(client_list)))

                if device_parts:
                    lines.append(tr("notify.violation.devices_ua", details="; ".join(device_parts)))
                else:
                    lines.append(tr("notify.violation.devices_empty"))
            else:
                lines.append(tr("notify.violation.devices_empty"))

        # Хвост: длительность и время (скор уже в сводке сверху)
        lines.append("")
        if violation_duration_sec > 0:
            lines.append(tr("notify.violation.duration", seconds=violation_duration_sec))
        lines.append(tr("notify.violation.time_msk", time=moscow_time_str))

        text = "\n".join(lines)

        rows = [
            [
                InlineKeyboardButton(text=tr("notify.violation.btn.info"), callback_data=f"vact:info:{user_uuid}"),
                InlineKeyboardButton(text=tr("notify.violation.btn.block"), callback_data=f"vact:block:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=tr("notify.violation.btn.kill"), callback_data=f"vact:kill:{user_uuid}"),
                InlineKeyboardButton(text=tr("notify.violation.btn.reset"), callback_data=f"vact:reset:{user_uuid}"),
            ],
            [
                InlineKeyboardButton(text=tr("notify.violation.btn.annul"), callback_data=f"vact:dismiss:{user_uuid}"),
            ],
        ]

        # Белый список: целиком и «только по этому поводу». Второй кнопки
        # нет, если ни один анализатор не набрал очков — предлагать разрез
        # наугад хуже, чем не предлагать вовсе.
        whitelist_row = [
            InlineKeyboardButton(
                text=tr("notify.violation.btn.whitelist"), callback_data=f"vact:wl:{user_uuid}",
            ),
        ]
        analyzer = dominant_analyzer(breakdown)
        if analyzer:
            whitelist_row.append(InlineKeyboardButton(
                text=tr(
                    "notify.violation.btn.whitelist_partial",
                    analyzer=tr(f"notify.violation.analyzer.{analyzer}"),
                ),
                callback_data=f"vact:wlp_{analyzer}:{user_uuid}",
            ))
        rows.append(whitelist_row)

        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

        message_kwargs = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs)

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


from src.utils.formatters import _esc  # noqa: E402 — reuse single implementation
