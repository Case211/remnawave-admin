"""Утилиты для отправки уведомлений в Telegram топики."""
import asyncio
import io
import json
import re
from typing import Any, Dict, Optional

import qrcode
from aiogram import Bot

from src.config import get_settings
from src.utils.formatters import format_bytes, format_datetime
from src.utils.i18n import tr
# реэкспорт для обработчиков кнопок нарушений и их тестов
from shared.analyzers.models import VIOLATION_ANALYZERS, dominant_analyzer  # noqa: F401
from shared.tg_card import (
    CAPTION_LIMIT, HTML_LIMIT, Card, b, code, i, link, mark, s, section, spoiler, tg_user, when,
)
from shared.logger import logger
from shared.notification_config import (
    is_notification_type_enabled,
    resolve_notification_topic,
    resolve_notifications_chat_id,
)


def _strip_html(text: str) -> str:
    """Чистим HTML-теги из текста — для FCM payload, который читается как plain text."""
    return re.sub(r"<[^>]+>", "", text)


async def _send_card(
    bot: Bot, message_kwargs: Dict[str, Any], card: Optional[Card] = None,
    media: Optional[tuple] = None,
) -> None:
    """Отправить карточку уведомления rich-сообщением (Bot API 10.1+).

    С ``card`` (shared.tg_card) уходят её блоки — таблицы, секции, подвал, —
    а HTML-фолбэк берётся из неё же. Без карточки первая строка ``text``
    становится заголовком, поля с отступом — списком. При отказе rich-пути
    (или выключенном тумблере notifications_rich_enabled) внутри
    send_rich_or_html срабатывает фолбэк на обычный HTML — уведомление доходит
    в любом случае. aiogram у бота старый (3.12, без Rich-типов), поэтому шлём
    raw-запросом с токеном бота. ``media`` — (вид, имя, байты) вложения для
    медиа-блока карточки; в фолбэке оно уходит файлом с подписью.
    """
    from shared import tg_rich

    reply_markup = message_kwargs.get("reply_markup")
    if reply_markup is not None and hasattr(reply_markup, "model_dump"):
        reply_markup = reply_markup.model_dump(exclude_none=True, by_alias=True)

    await tg_rich.send_rich_or_html(
        bot.token,
        message_kwargs["chat_id"],
        card.to_html(limit=CAPTION_LIMIT if media else HTML_LIMIT) if card is not None else message_kwargs["text"],
        blocks=card.to_blocks() if card is not None else None,
        message_thread_id=message_kwargs.get("message_thread_id"),
        reply_markup=reply_markup,
        fallback_markup=card.keyboard() if card is not None else None,
        media=media,
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


def _title(key: str, fallback_key: str, **kwargs: Any) -> str:
    """Заголовок события; незнакомое событие — запасной заголовок с его именем."""
    value = tr(key)
    return tr(fallback_key, **kwargs) if value == key else value


def _qr_png(url: str) -> bytes:
    buf = io.BytesIO()
    qrcode.make(url, box_size=8, border=2).save(buf, format="PNG")
    return buf.getvalue()


def _user_diff_rows(info: dict, old_info: dict) -> list:
    """Изменившиеся поля: старое значение зачёркнуто, новое — маркером."""
    unlimited = tr("notify.user.label.unlimited")
    fields = (
        ("trafficLimitBytes", "notify.user.field.traffic_limit", lambda v: format_bytes(v) if v else unlimited),
        ("expireAt", "notify.user.field.expire", lambda v: format_datetime(v) if v else "—"),
        ("trafficLimitStrategy", "notify.user.field.strategy", lambda v: v or "NO_RESET"),
        ("hwidDeviceLimit", "notify.user.field.hwid_limit",
         lambda v: unlimited if v == 0 else str(v) if v is not None else "—"),
        ("status", "notify.user.field.status", lambda v: str(v) if v else "—"),
        ("description", "notify.user.field.description", lambda v: str(v)[:60] if v else "—"),
        ("telegramId", "notify.user.field.telegram_id", lambda v: str(v) if v is not None else "—"),
        ("email", "notify.user.field.email", lambda v: str(v) if v else "—"),
        ("tag", "notify.user.field.tag", lambda v: str(v) if v else "—"),
    )
    return [[tr(label), s(fmt(old_info.get(key))), mark(fmt(info.get(key)))]
            for key, label, fmt in fields if old_info.get(key) != info.get(key)]


async def send_user_notification(
    bot: Bot,
    action: str,  # "created", "updated", "deleted", "expired", "expires_in_*", etc.
    user_info: dict,
    old_user_info: dict | None = None,
    changes: list | None = None,  # Список изменений из sync_service
    event_type: str | None = None,  # Оригинальный тип события из webhook
    subscription_url: str | None = None,  # Для QR-кода при создании
    created_by: str | None = None,  # Админ, создавший юзера через бота
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
        unlimited = tr("notify.user.label.unlimited")
        expire_at = info.get("expireAt")
        telegram_id = info.get("telegramId")

        card = Card(_title(f"notify.user.title.{action}", "notify.user.fallback"))
        # Срок — относительным временем: «через 3 дня» читается быстрее даты
        card.lead(b(info.get("username", "n/a")), code(info["status"]) if info.get("status") else None,
                  when(expire_at, "r") if expire_at else None)
        # Полный UUID, а не обрезок: по нему юзера и находят, и копируют
        card.fields([
            (tr("notify.user.field.uuid"), code(str(local_uuid or info.get("uuid") or info.get("id") or ""))),
            (tr("notify.user.label.telegram"),
             tg_user(str(telegram_id), telegram_id) if telegram_id is not None else None),
            (tr("notify.user.field.email"), code(info["email"]) if info.get("email") else None),
            (tr("notify.user.field.description"), info["description"][:100] if info.get("description") else None),
            (tr("notify.user.label.created_by"), created_by),
        ])

        traffic_limit = info.get("trafficLimitBytes")
        hwid_limit = info.get("hwidDeviceLimit")
        limits = [
            (tr("notify.user.label.limit"), code(format_bytes(traffic_limit) if traffic_limit else unlimited)),
            (tr("notify.user.label.expires"), when(expire_at) if expire_at else "—"),
            (tr("notify.user.label.reset"), code(info.get("trafficLimitStrategy") or "NO_RESET")),
            (tr("notify.user.label.hwid"),
             code(unlimited if hwid_limit == 0 else str(hwid_limit)) if hwid_limit is not None else None),
        ]

        if action == "updated" and old_user_info:
            old_info = old_user_info.get("response", old_user_info)
            diff_rows = _user_diff_rows(info, old_info)
            active_squads = info.get("activeInternalSquads", [])
            old_active_squads = old_info.get("activeInternalSquads", [])
            if active_squads != old_active_squads:
                old_sq = await _resolve_squads_display(old_active_squads)
                new_sq = await _resolve_squads_display(active_squads)
                if old_sq != new_sq:
                    diff_rows.append([tr("notify.user.field.squad"), s(old_sq), mark(new_sq)])

            if diff_rows:
                card.section(tr("notify.user.section.changes"))
                card.table(diff_rows, head=[tr("notify.user.col.field"), tr("notify.user.col.old"),
                                            tr("notify.user.col.new")])
            elif changes:
                card.section(tr("notify.user.section.changes"))
                card.bullets(changes)
            else:
                card.text(i(tr("notify.user.section.no_changes")))
            # Изменения главные; остальное — свёрнутой карточкой, а не простынёй
            card.details(tr("notify.user.section.card"), section().fields(limits))
        else:
            active_squads = info.get("activeInternalSquads", [])
            squad_display = await _resolve_squads_display(active_squads)
            external_squad = info.get("externalSquadUuid")
            if squad_display == "—" and external_squad:
                squad_display = tr("notify.user.external_squad", uuid=external_squad[:8])
            card.section(tr("notify.user.section.traffic_limits"))
            card.fields([
                *limits,
                (tr("notify.user.label.squad"), code(squad_display) if squad_display != "—" else None),
                # ссылка даёт доступ к подписке — под спойлером, не на виду в общем чате
                (tr("notify.user.label.subscription"),
                 spoiler(code(info["subscriptionUrl"])) if info.get("subscriptionUrl") else None),
            ])

        media = None
        if action == "created" and subscription_url:
            try:
                media = ("photo", "subscription.png", _qr_png(subscription_url))
                card.details(tr("notify.user.qr"), section().media("photo"))
            except Exception as e:
                logger.warning("Failed to build subscription QR: %s", e)
        card.stamp()

        message_kwargs: Dict[str, Any] = {"chat_id": chat_id}
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs, card=card, media=media)
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
            body=info.get("username") or str(local_uuid or info.get("uuid") or info.get("id") or ""),
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


def unknown_event_card(event: str, event_data: Any) -> Card:
    """Событие, которого мы не знаем: имя и сырые данные — свёрнутым JSON."""
    try:
        raw = json.dumps(event_data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        raw = str(event_data)
    card = Card(tr("notify.unknown.title"))
    card.fields([(tr("notify.unknown.event"), code(event))])
    card.details(tr("notify.unknown.data"), section().code(raw[:3000], "json"))
    return card.stamp()


async def send_generic_notification(
    bot: Bot,
    title: str = "",
    message: str = "",
    emoji: str = "ℹ️",
    topic_type: str | None = None,
    card: Optional[Card] = None,
) -> None:
    """Отправляет общее уведомление в Telegram топик.

    Args:
        topic_type: Тип топика (users, nodes, service, hwid, crm, errors).
                   Если не указан, используется общий notifications_topic_id.
        card: готовая карточка (shared.tg_card) вместо title/message.
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
        message_kwargs: Dict[str, Any] = {"chat_id": chat_id}
        if card is None:
            message_kwargs["text"] = f"{emoji} <b>{title}</b>\n\n{message}"

        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs, card=card)
        logger.info("Generic notification sent successfully title=%s topic_id=%s",
                    card.title_text() if card is not None else title, topic_id)

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

        title_key = f"notify.node.title.{event}"
        node_name = node_info.get("name", "n/a")
        node_uuid = node_info.get("uuid", "n/a")
        address = node_info.get("address", "—")
        port = node_info.get("port", "—")
        country = node_info.get("countryCode", "—")
        status = node_info.get("status", "—")
        addr_str = f"{address}:{port}" if port != "—" else str(address)
        traffic_limit = node_info.get("trafficLimitBytes")

        card = Card(_title(title_key, "notify.node.fallback", event=event))
        card.lead(b(node_name), code(addr_str), country if country != "—" else None)
        card.fields([
            (tr("notify.node.label.uuid"), code(node_uuid)),
            (tr("notify.node.label.status"), code(status) if status != "—" else None),
            (tr("notify.node.label.traffic_limit"), code(format_bytes(traffic_limit)) if traffic_limit else None),
        ])
        if changes and event == "node.modified":
            card.section(tr("notify.node.label.changes"))
            card.bullets(changes)
        card.stamp()

        message_kwargs: Dict[str, Any] = {"chat_id": chat_id}
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs, card=card)
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
        card = Card(_title(f"notify.service.title.{event}", "notify.service.fallback", event=event))

        if event == "service.login_attempt_failed" or event == "service.login_attempt_success":
            # Remnawave вкладывает поля под data.loginAttempt (не на верхнем уровне)
            la = event_data.get("loginAttempt")
            la = la if isinstance(la, dict) else event_data
            card.lead(b(la.get("username") or "—"), code(la["ip"]) if la.get("ip") else None)
            card.fields([
                (tr("notify.service.login.username"), code(la["username"]) if la.get("username") else None),
                (tr("notify.service.login.ip"), code(la["ip"]) if la.get("ip") else None),
                (tr("notify.service.login.user_agent"), code(la["userAgent"][:200]) if la.get("userAgent") else None),
                (tr("notify.service.login.description"), la.get("description")),
            ])
        elif event == "panel.unavailable":
            error_message = event_data.get("error_message")
            last_check = event_data.get("last_check")
            card.fields([
                (tr("notify.service.panel_unavailable.error_type"), code(event_data.get("error_type") or "—")),
                (tr("notify.service.panel_unavailable.failures"), b(str(event_data.get("consecutive_failures", 0)))),
                (tr("notify.service.panel_unavailable.last_check"),
                 (when(last_check) or last_check) if last_check else None),
            ])
            if error_message:
                card.section(tr("notify.service.panel_unavailable.error_message"))
                card.code(str(error_message)[:500])
        card.stamp()

        message_kwargs: Dict[str, Any] = {"chat_id": chat_id}
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs, card=card)
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
        user_data = event_data.get("user", {})
        # Webhook может прислать hwidDevice или hwidUserDevice
        hwid_data = event_data.get("hwidDevice", {}) or event_data.get("hwidUserDevice", {})
        user_local_uuid = await _local_user_uuid(user_data) if user_data else None

        card = Card(_title(f"notify.hwid.title.{event}", "notify.hwid.fallback", event=event))
        card.lead(b(user_data.get("username", "n/a")) if user_data else None,
                  hwid_data.get("platform") if hwid_data else None,
                  hwid_data.get("deviceModel") if hwid_data else None)

        if user_data:
            telegram_id = user_data.get("telegramId")
            hwid_device_limit = user_data.get("hwidDeviceLimit", 0)
            card.section(tr("notify.hwid.user_header"))
            card.fields([
                (tr("notify.hwid.label.user"), code(user_data.get("username", "n/a"))),
                (tr("notify.hwid.label.uuid"),
                 code(str(user_local_uuid or user_data.get("uuid") or user_data.get("id", "n/a")))),
                (tr("notify.hwid.label.tg_id"),
                 tg_user(str(telegram_id), telegram_id) if telegram_id is not None else None),
                (tr("notify.hwid.label.status"), code(user_data.get("status", "—"))),
                (tr("notify.hwid.label.device_limit"),
                 code("∞" if hwid_device_limit == 0 else str(hwid_device_limit))),
                (tr("notify.hwid.label.description"),
                 user_data["description"][:100] if user_data.get("description") else None),
            ])

        if hwid_data:
            created_at = hwid_data.get("createdAt")
            card.section(tr("notify.hwid.device_header"))
            card.fields([
                (tr("notify.hwid.device.hwid"), code(hwid_data["hwid"]) if hwid_data.get("hwid") else None),
                (tr("notify.hwid.device.platform"), hwid_data.get("platform")),
                (tr("notify.hwid.device.os_version"), hwid_data.get("osVersion")),
                (tr("notify.hwid.device.model"), hwid_data.get("deviceModel")),
                (tr("notify.hwid.device.user_agent"),
                 code(hwid_data["userAgent"][:60]) if hwid_data.get("userAgent") else None),
                (tr("notify.hwid.device.added"), when(created_at) if created_at else None),
            ])
        card.stamp()

        message_kwargs: Dict[str, Any] = {"chat_id": chat_id}
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs, card=card)
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
        card = Card(tr("notify.error.title"))
        card.fields([(tr("notify.error.type"), code(event))])
        message = event_data.get("message", "")
        if message:
            # текст ошибки — моноширинным блоком: его копируют в поиск и в тикеты
            card.section(tr("notify.error.message"))
            card.code(str(message)[:1500])
        card.stamp()

        message_kwargs: Dict[str, Any] = {"chat_id": chat_id}
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs, card=card)
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
        card = Card(_title(f"notify.crm.title.{event}", "notify.crm.fallback", event=event))

        # Webhook может прислать данные в двух форматах:
        # 1. Плоский формат: {nodeName, providerName, loginUrl, nextBillingAt}
        # 2. Вложенный формат: {node: {...}, provider: {...}, billingNode: {...}}
        if event_data.get("nodeName") or event_data.get("providerName"):
            login_url = event_data.get("loginUrl")
            next_billing_at = event_data.get("nextBillingAt")
            card.lead(b(event_data.get("nodeName") or "—"), event_data.get("providerName"),
                      when(next_billing_at, "r") if next_billing_at else None)
            card.fields([
                (tr("notify.crm.section.node"), code(event_data["nodeName"]) if event_data.get("nodeName") else None),
                (tr("notify.crm.section.provider"), event_data.get("providerName")),
                (tr("notify.crm.label.login_url"), link(login_url, login_url) if login_url else None),
                (tr("notify.crm.label.next_billing"), when(next_billing_at) if next_billing_at else None),
            ])
        else:
            node_data = event_data.get("node", {})
            provider_data = event_data.get("provider", {})
            billing_data = event_data.get("billingNode", {})
            card.lead(b(node_data.get("name", "—")) if node_data else None,
                      provider_data.get("name") if provider_data else None)
            if node_data:
                card.section(tr("notify.crm.section.node"))
                card.fields([
                    (tr("notify.crm.label.name"), code(node_data.get("name", "n/a"))),
                    (tr("notify.crm.label.uuid"), code(node_data["uuid"]) if node_data.get("uuid") else None),
                    (tr("notify.crm.label.address"),
                     code(node_data["address"]) if node_data.get("address") else None),
                    (tr("notify.crm.label.port"), code(str(node_data["port"])) if node_data.get("port") else None),
                    (tr("notify.crm.label.country"), node_data.get("countryCode")),
                ])
            if provider_data:
                card.section(tr("notify.crm.section.provider"))
                card.fields([
                    (tr("notify.crm.label.name"), code(provider_data.get("name", "n/a"))),
                    (tr("notify.crm.label.uuid"),
                     code(provider_data["uuid"]) if provider_data.get("uuid") else None),
                ])
            if billing_data:
                amount = billing_data.get("amount")
                currency = billing_data.get("currency", "")
                next_billing_at = billing_data.get("nextBillingAt")
                last_billing_at = billing_data.get("lastBillingAt")
                card.section(tr("notify.crm.section.billing"))
                card.fields([
                    (tr("notify.crm.label.amount"),
                     b(f"{amount} {currency}".strip()) if amount is not None else None),
                    (tr("notify.crm.label.interval"), billing_data.get("billingInterval")),
                    (tr("notify.crm.label.next_billing"), when(next_billing_at) if next_billing_at else None),
                    (tr("notify.crm.label.last_billing"), when(last_billing_at) if last_billing_at else None),
                ])
        card.stamp()

        message_kwargs: Dict[str, Any] = {"chat_id": chat_id}
        if topic_id is not None:
            message_kwargs["message_thread_id"] = topic_id

        await _send_card(bot, message_kwargs, card=card)
        logger.info("CRM notification sent successfully event=%s topic_id=%s", event, topic_id)

    except Exception as exc:
        logger.exception("Failed to send CRM notification event=%s error=%s", event, exc)
