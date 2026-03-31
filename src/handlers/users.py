"""Обработчики для работы с пользователями."""
import asyncio
import base64
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _cleanup_message, _edit_text_safe, _get_target_user_id, _not_admin, _send_clean_message
from src.handlers.state import (
    MAX_SEARCH_RESULTS,
    PENDING_INPUT,
    SEARCH_PAGE_SIZE,
    USER_DETAIL_BACK_TARGET,
    USER_SEARCH_CONTEXT,
)
from src.keyboards.main_menu import main_menu_keyboard, users_menu_keyboard
from src.keyboards.navigation import NavTarget, nav_keyboard, nav_row
from src.keyboards.user_actions import (
    user_actions_keyboard,
    user_edit_keyboard,
    user_edit_squad_keyboard,
    user_edit_strategy_keyboard,
)
from src.keyboards.user_create import (
    user_create_confirm_keyboard,
    user_create_description_keyboard,
    user_create_expire_keyboard,
    user_create_hwid_keyboard,
    user_create_squad_keyboard,
    user_create_telegram_keyboard,
    user_create_traffic_keyboard,
)
from src.keyboards.user_stats import user_stats_keyboard
from src.keyboards.hwid_devices import hwid_devices_keyboard
from src.keyboards.hwid_menu import hwid_management_keyboard
from shared.api_client import ApiClientError, NotFoundError, UnauthorizedError, api_client
from shared.database import db_service
from src.services import data_access
from src.utils.formatters import (
    _esc,
    build_created_user,
    build_user_summary,
    format_bytes,
    format_datetime,
    format_hwid_device,
    format_hwid_devices_list,
)
from shared.logger import logger
from src.utils.notifications import send_user_notification

# Функции перенесены из basic.py

router = Router(name="users")


def _store_user_detail_back_target(user_id: int, back_to: str) -> None:
    """Сохраняет целевое меню для возврата из детального просмотра пользователя."""
    USER_DETAIL_BACK_TARGET[user_id] = back_to


def _get_user_detail_back_target(user_id: int) -> str:
    """Получает целевое меню для возврата из детального просмотра пользователя."""
    return USER_DETAIL_BACK_TARGET.get(user_id, NavTarget.USERS_MENU)


def _truncate(text: str, limit: int = 64) -> str:
    """Обрезает текст до указанной длины."""
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _iso_from_days(days: int) -> str:
    """Преобразует количество дней в ISO строку даты."""
    now = datetime.utcnow()
    return (now + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


def _user_matches_query(user: dict, normalized_query: str) -> bool:
    """Проверяет, соответствует ли пользователь поисковому запросу."""
    info = user.get("response", user)
    needle = normalized_query.lstrip("@")
    candidates = [
        (info.get("username") or "").lstrip("@").lower(),
        (info.get("email") or "").lower(),
        (info.get("description") or "").lower(),
    ]
    telegram_id = info.get("telegramId")
    if telegram_id is not None:
        candidates.append(str(telegram_id))
    return any(needle in field for field in candidates if field)


def _format_user_choice(user: dict) -> str:
    """Форматирует пользователя для отображения в списке."""
    status = user.get("status", "UNKNOWN")
    status_emoji = {
        "ACTIVE": "✅",
        "DISABLED": "❌",
        "LIMITED": "🟠",
        "EXPIRED": "⏰",
    }.get(status, "⚙️")

    username = user.get("username") or "n/a"
    username = username if username.startswith("@") else f"@{username}"
    email = user.get("email") or ""
    telegram_id = user.get("telegramId")
    description = user.get("description") or ""

    details = []
    if email:
        details.append(email)
    if telegram_id is not None:
        details.append(f"tg:{telegram_id}")
    if description:
        details.append(description)

    label = f"{status_emoji} {username}"
    if details:
        label = f"{label} - {' | '.join(details)}"
    return _truncate(label, limit=64)


async def _fetch_user(query: str) -> dict:
    """
    Получает пользователя по запросу (username или telegram_id).
    
    Сначала пытается найти в локальной БД для быстрого ответа,
    если не найден - запрашивает из API.
    """
    # Попробуем сначала найти в БД
    if db_service.is_connected:
        try:
            db_user = None
            if query.isdigit():
                db_user = await db_service.get_user_by_telegram_id(int(query))
            else:
                db_user = await db_service.get_user_by_username(query)
            
            if db_user:
                # Данные из БД уже в формате API (через _db_row_to_api_format)
                return {"response": db_user}
        except Exception as e:
            logger.debug("Database lookup failed, using API: %s", e)
    
    # Fallback на API
    if query.isdigit():
        return await api_client.get_user_by_telegram_id(int(query))
    return await api_client.get_user_by_username(query)


async def _search_users(query: str) -> list[dict]:
    """
    Ищет пользователей по запросу.
    
    Использует локальную БД для быстрого поиска, если она доступна.
    Если БД недоступна - fallback на API с пагинацией.
    """
    search_term = query.strip()
    if not search_term:
        return []
    
    # Попробуем сначала использовать локальную БД (если подключена и синхронизирована)
    if db_service.is_connected:
        try:
            db_results = await db_service.search_users(search_term, limit=MAX_SEARCH_RESULTS)
            if db_results:
                # Данные из БД уже в формате API (через _db_row_to_api_format)
                logger.debug("Found %d users in database for query: %s", len(db_results), search_term)
                return db_results
        except Exception as e:
            logger.warning("Database search failed, falling back to API: %s", e)
    
    # Fallback на API (оригинальная логика)
    normalized = search_term.lower()
    matches: list[dict] = []
    start = 0
    while True:
        data = await api_client.get_users(start=start, size=SEARCH_PAGE_SIZE)
        payload = data.get("response", data)
        users = payload.get("users") or []
        total = payload.get("total", len(users))
        for user in users:
            if _user_matches_query(user, normalized):
                matches.append(user)
        start += SEARCH_PAGE_SIZE
        if start >= total or not users:
            break
    return matches


async def _send_user_detail(
    target: Message | CallbackQuery, query: str, back_to: str = NavTarget.USERS_MENU
) -> None:
    """Отправляет детальную информацию о пользователе."""
    try:
        user = await _fetch_user(query)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        markup = nav_keyboard(back_to)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup)
        else:
            await _send_clean_message(target, text, reply_markup=markup)
        return
    except NotFoundError:
        text = _("user.not_found")
        markup = nav_keyboard(back_to)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup)
        else:
            await _send_clean_message(target, text, reply_markup=markup)
        return
    except ApiClientError:
        logger.exception("⚠️ API client error while fetching user query=%s", query)
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=nav_keyboard(back_to))
        else:
            await _send_clean_message(target, text, reply_markup=nav_keyboard(back_to))
        return

    await _send_user_summary(target, user, back_to=back_to)


async def _send_user_summary(target: Message | CallbackQuery, user: dict, back_to: str) -> None:
    """Отправляет краткую информацию о пользователе."""
    summary = build_user_summary(user, _)
    info = user.get("response", user)
    status = info.get("status", "UNKNOWN")
    uuid = info.get("uuid")
    reply_markup = user_actions_keyboard(uuid, status, back_to=back_to)
    user_id = None
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=reply_markup, parse_mode="HTML")
        user_id = target.from_user.id
    else:
        await _send_clean_message(target, summary, reply_markup=reply_markup, parse_mode="HTML")
        user_id = target.from_user.id if getattr(target, "from_user", None) else None
    if user_id is not None:
        _store_user_detail_back_target(user_id, back_to)


async def _start_user_search_flow(target: Message | CallbackQuery, preset_query: str | None = None) -> None:
    """Начинает процесс поиска пользователя."""
    user_id = _get_target_user_id(target)
    if user_id is None:
        return
    if preset_query:
        await _run_user_search(target, preset_query)
    else:
        # Устанавливаем PENDING_INPUT, чтобы сообщения пользователя не удалялись сразу
        PENDING_INPUT[user_id] = {"action": "user_search"}
        logger.info("_start_user_search_flow: set PENDING_INPUT for user_id=%s", user_id)
        await _send_clean_message(target, _("user.search_prompt"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))


async def _run_user_search(target: Message | CallbackQuery, query: str) -> None:
    """Выполняет поиск пользователей."""
    user_id = _get_target_user_id(target)
    if user_id is None:
        return
    try:
        matches = await _search_users(query)
    except UnauthorizedError:
        await _send_clean_message(target, _("errors.unauthorized"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return
    except ApiClientError:
        logger.exception("User search failed query=%s actor_id=%s", query, user_id)
        await _send_clean_message(target, _("errors.generic"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return

    if user_id is not None:
        PENDING_INPUT[user_id] = {"action": "user_search"}
        USER_SEARCH_CONTEXT[user_id] = {"query": query, "results": matches}

    if not matches:
        await _send_clean_message(
            target,
            _("user.search_no_results").format(query=_esc(query)),
            reply_markup=nav_keyboard(NavTarget.USERS_MENU),
        )
        return

    if len(matches) == 1:
        await _send_user_summary(target, matches[0], back_to=NavTarget.USER_SEARCH_PROMPT)
        return

    await _show_user_search_results(target, query, matches)


async def _show_user_search_results(target: Message | CallbackQuery, query: str, results: list[dict]) -> None:
    """Показывает результаты поиска пользователей."""
    user_id = _get_target_user_id(target)
    if user_id is not None:
        PENDING_INPUT[user_id] = {"action": "user_search"}

    rows = []
    for user in results[:MAX_SEARCH_RESULTS]:
        info = user.get("response", user)
        uuid = info.get("uuid")
        if not uuid:
            continue
        rows.append([InlineKeyboardButton(text=_format_user_choice(info), callback_data=f"user_search:view:{uuid}")])

    rows.append(nav_row(NavTarget.USER_SEARCH_PROMPT))
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)

    extra_line = ""
    if len(results) > MAX_SEARCH_RESULTS:
        extra_line = _("user.search_results_limited").format(shown=MAX_SEARCH_RESULTS, total=len(results))

    text = _("user.search_results").format(count=len(results), query=_esc(query))
    if extra_line:
        text = f"{text}\n{extra_line}"
    await _send_clean_message(target, text, reply_markup=keyboard)


async def _handle_user_search_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод поискового запроса."""
    query = (message.text or "").strip()
    user_id = message.from_user.id
    
    # Удаляем из PENDING_INPUT только после начала обработки
    # Это гарантирует, что сообщение не будет удалено до обработки
    if user_id in PENDING_INPUT:
        PENDING_INPUT.pop(user_id, None)
    
    if not query:
        await _send_clean_message(message, _("user.search_prompt"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        # Удаляем сообщение пользователя после обработки
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return
    
    # Выполняем поиск
    await _run_user_search(message, query)
    
    # Удаляем сообщение пользователя после обработки поиска
    asyncio.create_task(_cleanup_message(message, delay=0.5))


async def _delete_ctx_message(ctx: dict, bot) -> None:
    """Удаляет сообщение бота из контекста."""
    message_id = ctx.pop("bot_message_id", None)
    chat_id = ctx.get("bot_chat_id")
    if not message_id or not chat_id:
        return
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception as exc:
        logger.warning(
            "🧹 Failed to delete bot prompt chat_id=%s message_id=%s err=%s",
            chat_id,
            message_id,
            exc,
        )


async def _send_user_create_prompt(
    target: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    ctx: dict | None = None,
) -> None:
    """Отправляет промпт для создания пользователя."""
    bot = target.bot if isinstance(target, Message) else target.message.bot
    chat_id = target.chat.id if isinstance(target, Message) else target.message.chat.id
    message_id = ctx.get("bot_message_id") if ctx else None

    if ctx and message_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id, message_id=message_id, text=text, reply_markup=reply_markup
            )
            return
        except Exception as exc:
            logger.warning(
                "✏️ Failed to edit user create prompt chat_id=%s message_id=%s err=%s",
                chat_id,
                message_id,
                exc,
            )
            try:
                await bot.delete_message(chat_id=chat_id, message_id=message_id)
            except Exception:
                pass
            ctx.pop("bot_message_id", None)

    sent = await _send_clean_message(target, text, reply_markup=reply_markup)

    if ctx is not None:
        ctx["bot_message_id"] = sent.message_id
        ctx["bot_chat_id"] = sent.chat.id


def _build_user_create_preview(data: dict) -> str:
    """Создает превью данных пользователя перед созданием."""
    expire_at = format_datetime(data.get("expire_at"))
    traffic_limit = data.get("traffic_limit_bytes")
    hwid_limit = data.get("hwid_limit")
    traffic_display = _("user.unlimited") if traffic_limit in (None, 0) else format_bytes(traffic_limit)
    hwid_display = _("user.unlimited") if not hwid_limit else str(hwid_limit)
    telegram_id = data.get("telegram_id") or _("user.not_set")
    description = data.get("description") or _("user.not_set")
    squad = data.get("squad_uuid") or _("user.no_squad")

    return _("user.create_preview").format(
        username=_esc(data.get("username", "n/a")),
        expire=expire_at,
        traffic=traffic_display,
        hwid=hwid_display,
        telegramId=telegram_id,
        description=_esc(description),
        squad=_esc(squad),
    )


async def _create_user(target: Message | CallbackQuery, data: dict) -> None:
    """Создает пользователя."""
    async def _respond(text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
        await _send_clean_message(target, text, reply_markup=reply_markup)

    username = data.get("username")
    expire_at = data.get("expire_at")
    if not username or not expire_at:
        await _respond(_("user.prompt_username"))
        return

    try:
        telegram_id = int(data["telegram_id"]) if data.get("telegram_id") not in (None, "") else None
    except (ValueError, TypeError):
        await _respond(_("user.invalid_telegram"), reply_markup=users_menu_keyboard())
        return

    try:
        squad_uuid = data.get("squad_uuid")
        squad_source = data.get("squad_source") or "internal"
        internal_squads = [squad_uuid] if squad_uuid and squad_source != "external" else None
        external_squad_uuid = squad_uuid if squad_uuid and squad_source == "external" else None
        logger.info(
            "👤 Creating user username=%s expire_at=%s traffic_bytes=%s hwid=%s telegram_id=%s squad_source=%s internal_squads=%s external_squad_uuid=%s actor_id=%s",
            username,
            expire_at,
            data.get("traffic_limit_bytes"),
            data.get("hwid_limit"),
            telegram_id,
            squad_source,
            internal_squads,
            external_squad_uuid,
            target.from_user.id if hasattr(target, "from_user") else "n/a",
        )
        user = await api_client.create_user(
            username=username,
            expire_at=expire_at,
            telegram_id=telegram_id,
            traffic_limit_bytes=data.get("traffic_limit_bytes"),
            hwid_device_limit=data.get("hwid_limit"),
            description=data.get("description"),
            external_squad_uuid=external_squad_uuid,
            active_internal_squads=internal_squads,
            traffic_limit_strategy="MONTH",
        )
    except UnauthorizedError:
        await _respond(_("errors.unauthorized"), reply_markup=users_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("❌ Create user failed")
        await _respond(_("errors.generic"), reply_markup=users_menu_keyboard())
        return

    summary = build_created_user(user, _)
    info = user.get("response", user)
    status = info.get("status", "UNKNOWN")
    reply_markup = user_actions_keyboard(info.get("uuid", ""), status)
    await _respond(summary, reply_markup)
    
    # Удаляем сообщение пользователя после создания (только для Message, не для CallbackQuery)
    if isinstance(target, Message):
        asyncio.create_task(_cleanup_message(target, delay=0.5))
    
    # Отправляем уведомление о создании пользователя
    try:
        bot = target.bot if isinstance(target, Message) else target.message.bot
        await send_user_notification(bot, "created", user)
    except Exception:
        logger.exception("Failed to send user creation notification")


def _get_protocol_type(link: str) -> str:
    """Определяет тип протокола по ссылке."""
    if link.startswith("vless://"):
        return "vless"
    elif link.startswith("ss://"):
        return "ss"
    elif link.startswith("trojan://"):
        return "trojan"
    elif link.startswith("vmess://"):
        return "vmess"
    elif link.startswith("hysteria://"):
        return "hysteria"
    elif link.startswith("tuic://"):
        return "tuic"
    else:
        return "unknown"


def _get_protocol_name(protocol_type: str) -> str:
    """Возвращает название протокола с эмодзи."""
    protocol_names = {
        "vless": "🔷 VLESS",
        "ss": "🔶 SS",
        "trojan": "🔴 Trojan",
        "vmess": "🟣 VMess",
        "hysteria": "🟡 Hysteria",
        "tuic": "🟢 TUIC",
        "unknown": "🔗 Link",
    }
    return protocol_names.get(protocol_type.lower(), "🔗 Link")


def _format_user_edit_snapshot(info: dict, t) -> str:
    """Форматирует снимок данных пользователя для отображения при редактировании."""
    traffic_limit = info.get("trafficLimitBytes")
    strategy = info.get("trafficLimitStrategy")
    expire = format_datetime(info.get("expireAt"))
    hwid = info.get("hwidDeviceLimit")
    tag = info.get("tag") or t("user.not_set")
    telegram_id = info.get("telegramId") or t("user.not_set")
    email = info.get("email") or t("user.not_set")
    description = info.get("description") or t("user.not_set")
    username = info.get("username", "n/a")
    short_uuid = info.get("shortUuid", "n/a")
    uuid = info.get("uuid", "n/a")

    # Получаем информацию о скваде
    active_squads = info.get("activeInternalSquads", [])
    squad_display = t("user.not_set")
    if active_squads:
        first_squad = active_squads[0]
        # activeInternalSquads может быть списком словарей или списком строк UUID
        if isinstance(first_squad, dict):
            # Если это словарь, извлекаем имя сквада
            squad_display = first_squad.get("name", first_squad.get("uuid", t("user.not_set")))
        else:
            # Если это строка UUID, пытаемся получить имя сквада
            squad_info = info.get("internalSquads", [])
            if squad_info and isinstance(squad_info, list) and len(squad_info) > 0:
                squad_display = squad_info[0].get("name", first_squad)
            else:
                squad_display = first_squad

    # Форматируем информацию о пользователе с группировкой по секциям
    lines = [
        f"<b>✏️ {t('user.edit_prompt')}</b>",
        "",
        f"<b>{t('user.edit_section_user_info')}</b>",
        f"   Username: <code>{_esc(username)}</code>",
        f"   🔖 Short: <code>{_esc(short_uuid)}</code>",
        f"   🆔 UUID: <code>{_esc(uuid)}</code>",
        f"   {t('user.edit_status_label')}: <b>{info.get('status', 'UNKNOWN')}</b>",
        "",
        f"<b>{t('user.edit_section_traffic')}</b>",
        f"   {t('user.edit_traffic_limit')}: <code>{format_bytes(traffic_limit)}</code>",
        f"   {t('user.edit_strategy')}: <code>{strategy or t('user.not_set')}</code>",
        f"   {t('user.edit_expire')}: <code>{expire}</code>",
        f"   {t('user.edit_hwid')}: <code>{hwid if hwid is not None else t('user.not_set')}</code>",
        "",
        f"<b>{t('user.edit_section_additional')}</b>",
        f"   {t('user.edit_tag')}: <code>{tag}</code>",
        f"   {t('user.edit_description')}: <code>{_esc(description)}</code>",
        "",
        f"<b>{t('user.edit_section_contacts')}</b>",
        f"   {t('user.edit_telegram')}: <code>{telegram_id}</code>",
        f"   {t('user.edit_email')}: <code>{email}</code>",
        "",
        f"<b>{t('user.edit_section_squad')}</b>",
        f"   <code>{_esc(squad_display)}</code>",
    ]
    
    return "\n".join(lines)


def _current_user_edit_values(info: dict) -> dict[str, str]:
    """Получает текущие значения полей пользователя для редактирования."""
    active_squads = info.get("activeInternalSquads", [])
    squad_display = ""
    if active_squads:
        squad_info = info.get("internalSquads", [])
        if squad_info and isinstance(squad_info, list) and len(squad_info) > 0:
            squad_display = squad_info[0].get("name", active_squads[0])
        else:
            squad_display = active_squads[0] if len(active_squads) > 0 else ""

    return {
        "traffic": format_bytes(info.get("trafficLimitBytes")),
        "strategy": info.get("trafficLimitStrategy") or "NO_RESET",
        "expire": format_datetime(info.get("expireAt")),
        "hwid": str(info.get("hwidDeviceLimit")) if info.get("hwidDeviceLimit") is not None else "0",
        "description": info.get("description") or "",
        "tag": info.get("tag") or "",
        "telegram": str(info.get("telegramId") or ""),
        "email": info.get("email") or "",
        "squad": squad_display,
    }


async def _apply_user_update(target: Message | CallbackQuery, user_uuid: str, payload: dict, back_to: str) -> None:
    """Применяет обновление пользователя."""
    try:
        # Получаем старое значение пользователя перед обновлением
        old_user = None
        try:
            old_user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        except Exception:
            logger.debug("Failed to get old user data for notification user_uuid=%s", user_uuid)
        
        await api_client.update_user(user_uuid, **payload)
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        info = user.get("response", user)
        text = _format_user_edit_snapshot(info, _)
        markup = user_edit_keyboard(user_uuid, back_to=back_to)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
        else:
            await _send_clean_message(target, text, reply_markup=markup, parse_mode="HTML")
            # Удаляем сообщение пользователя после обработки (только для Message, не для CallbackQuery)
            asyncio.create_task(_cleanup_message(target, delay=0.5))
        
        # Отправляем уведомление об изменении пользователя
        try:
            bot = target.message.bot if isinstance(target, CallbackQuery) else target.bot
            await send_user_notification(bot, "updated", user, old_user_info=old_user)
        except Exception:
            logger.exception("Failed to send user update notification")
    except UnauthorizedError:
        reply_markup = main_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("errors.unauthorized"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("errors.unauthorized"), reply_markup=reply_markup)
    except NotFoundError:
        reply_markup = main_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("user.not_found"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("user.not_found"), reply_markup=reply_markup)
    except ApiClientError:
        logger.exception("❌ User update failed user_uuid=%s payload_keys=%s", user_uuid, list(payload.keys()))
        reply_markup = main_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("errors.generic"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("errors.generic"), reply_markup=reply_markup)


async def _handle_user_edit_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод значений при редактировании пользователя."""
    import asyncio
    import re

    user_uuid = ctx.get("uuid")
    field = ctx.get("field")
    back_to = ctx.get("back_to", NavTarget.USERS_MENU)
    text = (message.text or "").strip()

    if not user_uuid or not field:
        await _send_clean_message(message, _("errors.generic"), reply_markup=nav_keyboard(back_to))
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    def _set_retry(prompt_key: str) -> None:
        PENDING_INPUT[message.from_user.id] = ctx
        asyncio.create_task(
            _send_clean_message(
                message,
                _(prompt_key),
                reply_markup=user_edit_keyboard(user_uuid, back_to=back_to),
            )
        )
        # Удаляем сообщение пользователя после обработки
        asyncio.create_task(_cleanup_message(message, delay=0.5))

    payload: dict[str, object | None] = {}

    if field == "traffic":
        try:
            gb = float(text)
            if gb < 0:
                raise ValueError
            payload["trafficLimitBytes"] = int(gb * 1024 * 1024 * 1024)
        except ValueError:
            _set_retry("user.edit_invalid_number")
            return
    elif field == "strategy":
        strategy = text.upper()
        if strategy not in {"NO_RESET", "DAY", "WEEK", "MONTH", "MONTH_ROLLING"}:
            _set_retry("user.edit_invalid_strategy")
            return
        payload["trafficLimitStrategy"] = strategy
    elif field == "expire":
        iso_text = text
        try:
            if len(text) == 10:
                # YYYY-MM-DD
                iso_text = f"{text}T00:00:00Z"
            datetime.fromisoformat(iso_text.replace("Z", "+00:00"))
        except Exception:
            _set_retry("user.edit_invalid_expire")
            return
        payload["expireAt"] = iso_text
    elif field == "hwid":
        try:
            hwid = int(text)
            if hwid < 0:
                raise ValueError
            payload["hwidDeviceLimit"] = hwid
        except ValueError:
            _set_retry("user.edit_invalid_number")
            return
    elif field == "description":
        payload["description"] = text or None
    elif field == "tag":
        tag = text.strip().upper()
        if tag in {"", "-"}:
            payload["tag"] = None
        elif not re.fullmatch(r"[A-Z0-9_]{1,16}", tag):
            _set_retry("user.edit_invalid_tag")
            return
        else:
            payload["tag"] = tag
    elif field == "telegram":
        if text in {"", "-"}:
            payload["telegramId"] = None
        else:
            try:
                payload["telegramId"] = int(text)
            except ValueError:
                _set_retry("user.edit_invalid_number")
                return
    elif field == "email":
        payload["email"] = None if text in {"", "-"} else text
    else:
        await _send_clean_message(message, _("errors.generic"), reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    await _apply_user_update(message, user_uuid, payload, back_to=back_to)


async def _handle_user_create_input(message: Message, ctx: dict) -> None:
    """Обрабатывает пошаговый ввод для создания пользователя."""
    user_id = message.from_user.id
    data = ctx.setdefault("data", {})
    stage = ctx.get("stage", "username")
    text = message.text.strip()
    logger.info(
        "✏️ User create input stage=%s user_id=%s text='%s' ctx_keys=%s",
        stage,
        user_id,
        text,
        sorted(list(ctx.keys())),
    )

    if stage == "username":
        if not text:
            await _send_user_create_prompt(message, _("user.prompt_username"), ctx=ctx)
            PENDING_INPUT[user_id] = ctx
            asyncio.create_task(_cleanup_message(message, delay=0.5))
            return
        data["username"] = text.split()[0]
        ctx["stage"] = "description"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_description"), user_create_description_keyboard(), ctx=ctx
        )
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    if stage == "description":
        data["description"] = text
        ctx["stage"] = "expire"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_expire"), user_create_expire_keyboard(), ctx=ctx
        )
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    if stage == "expire":
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            ctx["stage"] = "expire"
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                message, _("user.invalid_expire"), user_create_expire_keyboard(), ctx=ctx
            )
            asyncio.create_task(_cleanup_message(message, delay=0.5))
            return
        data["expire_at"] = text
        ctx["stage"] = "traffic"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_traffic"), user_create_traffic_keyboard(), ctx=ctx
        )
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    if stage == "traffic":
        try:
            gb = float(text)
        except ValueError:
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                message, _("user.invalid_traffic"), user_create_traffic_keyboard(), ctx=ctx
            )
            asyncio.create_task(_cleanup_message(message, delay=0.5))
            return
        data["traffic_limit_bytes"] = int(gb * 1024 * 1024 * 1024)
        ctx["stage"] = "hwid"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(message, _("user.prompt_hwid"), user_create_hwid_keyboard(), ctx=ctx)
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    if stage == "hwid":
        try:
            hwid = int(text)
        except ValueError:
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                message, _("user.invalid_hwid"), user_create_hwid_keyboard(), ctx=ctx
            )
            asyncio.create_task(_cleanup_message(message, delay=0.5))
            return
        data["hwid_limit"] = hwid
        ctx["stage"] = "telegram"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_telegram"), user_create_telegram_keyboard(), ctx=ctx
        )
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    if stage == "telegram":
        if text:
            try:
                data["telegram_id"] = int(text)
            except ValueError:
                PENDING_INPUT[user_id] = ctx
                await _send_user_create_prompt(
                    message, _("user.invalid_telegram"), user_create_telegram_keyboard(), ctx=ctx
                )
                asyncio.create_task(_cleanup_message(message, delay=0.5))
                return
        else:
            data["telegram_id"] = None
        ctx["stage"] = "squad"
        PENDING_INPUT[user_id] = ctx
        try:
            await _send_squad_prompt(message, ctx)
        except Exception:
            logger.exception("⚠️ Squad prompt failed, falling back to manual entry")
            await _send_user_create_prompt(
                message, _("user.squad_load_failed"), user_create_squad_keyboard([]), ctx=ctx
            )
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    if stage == "squad":
        data["squad_uuid"] = text or None
        ctx["stage"] = "confirm"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _build_user_create_preview(data), user_create_confirm_keyboard(), ctx=ctx
        )
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return

    # Default: stay on confirm
    if ctx.get("stage") == "confirm":
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _build_user_create_preview(data), user_create_confirm_keyboard(), ctx=ctx
        )


async def _handle_user_create_callback(callback: CallbackQuery) -> None:
    """Обрабатывает callback'и в процессе создания пользователя."""
    user_id = callback.from_user.id
    ctx = PENDING_INPUT.get(user_id, {"action": "user_create", "data": {}, "stage": "username"})
    data = ctx.setdefault("data", {})
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]

    if action == "skip" and len(parts) >= 3:
        field = parts[2]
        if field == "description":
            data["description"] = ""
            ctx["stage"] = "expire"
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                callback, _("user.prompt_expire"), user_create_expire_keyboard(), ctx=ctx
            )
            return
        if field == "telegram":
            data["telegram_id"] = None
            ctx["stage"] = "squad"
            PENDING_INPUT[user_id] = ctx
            try:
                await _send_squad_prompt(callback, ctx)
            except Exception:
                logger.exception("⚠️ Squad prompt failed from callback, falling back to manual entry")
                await _send_user_create_prompt(
                    callback, _("user.squad_load_failed"), user_create_squad_keyboard([]), ctx=ctx
                )
            return
        if field == "squad":
            data["squad_uuid"] = None
            ctx["stage"] = "confirm"
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                callback, _build_user_create_preview(data), user_create_confirm_keyboard(), ctx=ctx
            )
            return

    if action == "expire" and len(parts) >= 3:
        try:
            days = int(parts[2])
            if days == 2099:
                # Как в Панели: текущий день/месяц, год 2099
                now = datetime.utcnow()
                data["expire_at"] = now.replace(year=2099, microsecond=0).isoformat() + "Z"
            else:
                data["expire_at"] = _iso_from_days(days)
        except ValueError:
            pass
        ctx["stage"] = "traffic"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            callback, _("user.prompt_traffic"), user_create_traffic_keyboard(), ctx=ctx
        )
        return

    if action == "traffic" and len(parts) >= 3:
        value = parts[2]
        if value == "unlimited":
            data["traffic_limit_bytes"] = 0
        else:
            try:
                gb = float(value)
                data["traffic_limit_bytes"] = int(gb * 1024 * 1024 * 1024)
            except ValueError:
                data["traffic_limit_bytes"] = None
        ctx["stage"] = "hwid"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(callback, _("user.prompt_hwid"), user_create_hwid_keyboard(), ctx=ctx)
        return

    if action == "hwid" and len(parts) >= 3:
        try:
            hwid = int(parts[2])
            data["hwid_limit"] = hwid if hwid > 0 else None
        except ValueError:
            data["hwid_limit"] = None
        ctx["stage"] = "telegram"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            callback, _("user.prompt_telegram"), user_create_telegram_keyboard(), ctx=ctx
        )
        return

    if action == "confirm":
        try:
            await _create_user(callback, data)
            await _delete_ctx_message(ctx, callback.message.bot)
            PENDING_INPUT.pop(user_id, None)
        except Exception:
            PENDING_INPUT[user_id] = ctx
            raise
        return

    if action == "cancel":
        await _delete_ctx_message(ctx, callback.message.bot)
        PENDING_INPUT.pop(user_id, None)
        await _send_user_create_prompt(callback, _("user.cancelled"), users_menu_keyboard(), ctx=ctx)

    if action == "squad" and len(parts) >= 3:
        data["squad_uuid"] = parts[2]
        ctx["stage"] = "confirm"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            callback, _build_user_create_preview(data), user_create_confirm_keyboard(), ctx=ctx
        )


async def _send_squad_prompt(target: Message | CallbackQuery, ctx: dict) -> None:
    """Отправляет промпт для выбора сквада."""
    data = ctx.setdefault("data", {})
    # Получаем squads из БД с fallback на API
    try:
        squads, squad_source = await data_access.get_all_squads()
        logger.info("📥 Loaded %s %s squads for user_id=%s", len(squads), squad_source, target.from_user.id)
    except UnauthorizedError:
        await _send_user_create_prompt(target, _("errors.unauthorized"), users_menu_keyboard(), ctx=ctx)
        return
    except Exception as exc:
        logger.warning("⚠️ Failed to load squads: %s", exc)
        squads = []
        squad_source = "internal"

    if not squads:
        await _send_user_create_prompt(
            target, _("user.squad_load_failed"), user_create_squad_keyboard([]), ctx=ctx
        )
        return

    squads_sorted = sorted(squads, key=lambda s: s.get("viewPosition", 0))
    markup = user_create_squad_keyboard(squads_sorted)
    text = _("user.prompt_squad") if squads_sorted else _("user.squad_load_failed")
    data["squad_source"] = squad_source
    logger.info(
        "🧩 Squad prompt using source=%s squads_count=%s user_id=%s",
        squad_source,
        len(squads_sorted),
        target.from_user.id,
    )
    PENDING_INPUT[target.from_user.id] = ctx
    await _send_user_create_prompt(target, text, markup, ctx=ctx)


async def _show_squad_selection_for_edit(callback: CallbackQuery, user_uuid: str, back_to: str) -> None:
    """Показывает список сквадов для выбора при редактировании пользователя."""
    squads: list[dict] = []
    # Получаем squads из БД с fallback на API
    try:
        squads, squad_type = await data_access.get_all_squads()
        logger.info("📥 Loaded %s %s squads for edit user_id=%s", len(squads), squad_type, callback.from_user.id)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))
        return
    except Exception as exc:
        logger.warning("⚠️ Failed to load squads: %s", exc)
        squads = []
        squad_type = "internal"

    if not squads:
        await callback.message.edit_text(
            _("user.squad_load_failed"),
            reply_markup=user_edit_keyboard(user_uuid, back_to=back_to)
        )
        return

    squads_sorted = sorted(squads, key=lambda s: s.get("viewPosition", 0))
    # Сохраняем список сквадов в контексте для получения UUID по индексу
    user_id = callback.from_user.id
    PENDING_INPUT[user_id] = {
        "action": "user_edit_squad",
        "user_uuid": user_uuid,
        "squads": squads_sorted,
        "squad_type": squad_type,
        "back_to": back_to,
    }
    markup = user_edit_squad_keyboard(squads_sorted, user_uuid, back_to=back_to)
    text = _("user.edit_prompt_squad") if squads_sorted else _("user.squad_load_failed")
    await callback.message.edit_text(text, reply_markup=markup)


# Функции перенесены из basic.py


@router.callback_query(F.data == "menu:create_user")
async def cb_create_user(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Создать пользователя'."""
    if await _not_admin(callback):
        return
    await callback.answer()
    logger.info("🚀 User create flow started by user_id=%s", callback.from_user.id)
    ctx = {"action": "user_create", "stage": "username", "data": {}}
    PENDING_INPUT[callback.from_user.id] = ctx
    await _send_user_create_prompt(callback, _("user.prompt_username"), ctx=ctx)


@router.callback_query(F.data.startswith("user_create:"))
async def cb_user_create_flow(callback: CallbackQuery) -> None:
    """Обработчик callback'ов в процессе создания пользователя."""
    if await _not_admin(callback):
        return
    await callback.answer()
    logger.info("🔄 User create callback action=%s user_id=%s", callback.data, callback.from_user.id)
    await _handle_user_create_callback(callback)


@router.callback_query(F.data == "menu:find_user")
async def cb_find_user(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Найти пользователя'."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _start_user_search_flow(callback)


@router.callback_query(F.data.startswith("user_search:view:"))
async def cb_user_search_view(callback: CallbackQuery) -> None:
    """Обработчик просмотра пользователя из результатов поиска."""
    if await _not_admin(callback):
        return
    await callback.answer()
    user_uuid = callback.data.split(":", 2)[2]
    back_to = NavTarget.USER_SEARCH_RESULTS
    try:
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
        return
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
        return
    except ApiClientError:
        logger.exception("User view from search failed user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
        return

    await _send_user_summary(callback, user, back_to=back_to)


@router.callback_query(F.data.startswith("user:"))
async def cb_user_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с пользователем (enable, disable, reset, revoke) или возврата в профиль."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        await callback.answer(_("errors.generic"), show_alert=True)
        return
    
    user_uuid = parts[1]
    action = parts[2] if len(parts) > 2 else None
    back_to = _get_user_detail_back_target(callback.from_user.id)
    
    # Если action отсутствует, просто возвращаемся в профиль пользователя
    if not action:
        try:
            user = await data_access.get_user_by_uuid_wrapped(user_uuid)
            await _send_user_summary(callback, user, back_to=back_to)
        except UnauthorizedError:
            await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
        except NotFoundError:
            await callback.message.edit_text(_("user.not_found"), reply_markup=main_menu_keyboard())
        except ApiClientError:
            logger.exception("Failed to get user profile user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
            await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())
        return
    
    try:
        if action == "enable":
            await api_client.enable_user(user_uuid)
        elif action == "disable":
            await api_client.disable_user(user_uuid)
        elif action == "reset":
            await api_client.reset_user_traffic(user_uuid)
        elif action == "revoke":
            # Показываем подтверждение перед отзывом подписки
            try:
                user = await data_access.get_user_by_uuid_wrapped(user_uuid)
                user_info = user.get("response", user)
                username = user_info.get("username", "Unknown")
                from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("actions.revoke_confirm_yes"),
                            callback_data=f"user:{user_uuid}:revoke_confirm"
                        ),
                        InlineKeyboardButton(
                            text=_("actions.revoke_confirm_no"),
                            callback_data=f"user:{user_uuid}"
                        )
                    ]
                ])
                await _edit_text_safe(
                    callback.message,
                    _("actions.revoke_confirm").format(username=username),
                    reply_markup=keyboard,
                    parse_mode="HTML"
                )
                return
            except Exception:
                logger.exception("Failed to get user for revoke confirmation")
                await callback.answer(_("errors.generic"), show_alert=True)
                return
        elif action == "revoke_confirm":
            # Подтвержденное отзыв подписки
            await api_client.revoke_user_subscription(user_uuid)
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        summary = build_user_summary(user, _)
        status = user.get("response", user).get("status", "UNKNOWN")
        await _edit_text_safe(
            callback.message,
            summary,
            reply_markup=user_actions_keyboard(user_uuid, status, back_to=back_to),
            parse_mode="HTML"
        )
        _store_user_detail_back_target(callback.from_user.id, back_to)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ User action failed action=%s user_uuid=%s actor_id=%s", action, user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("user_actions:"))
async def cb_user_actions_menu(callback: CallbackQuery) -> None:
    """Обработчик для возврата к меню действий пользователя."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    
    user_uuid = parts[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)
    
    try:
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        summary = build_user_summary(user, _)
        status = user.get("response", user).get("status", "UNKNOWN")
        await callback.message.edit_text(
            summary, reply_markup=user_actions_keyboard(user_uuid, status, back_to=back_to), parse_mode="HTML"
        )
        _store_user_detail_back_target(callback.from_user.id, back_to)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user actions menu user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("user_edit:"))
async def cb_user_edit_menu(callback: CallbackQuery) -> None:
    """Обработчик входа в меню редактирования пользователя."""
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, user_uuid = callback.data.split(":")
    # Кнопка "Назад" должна вести в профиль пользователя, а не в поиск
    back_to = f"user:{user_uuid}"
    try:
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        info = user.get("response", user)
        header = _format_user_edit_snapshot(info, _)
        await callback.message.edit_text(
            header,
            reply_markup=user_edit_keyboard(user_uuid, back_to=back_to),
            parse_mode="HTML",
        )
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ User edit menu failed user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("uef:"))
async def cb_user_edit_field(callback: CallbackQuery) -> None:
    """Обработчик редактирования полей пользователя."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    # patterns:
    # uef:status:ACTIVE:{uuid}
    # uef:{field}::{uuid}
    if len(parts) < 3:
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())
        return
    _prefix, field = parts[0], parts[1]
    value = parts[2] if len(parts) > 3 else None
    user_uuid = parts[-1]
    back_to = _get_user_detail_back_target(callback.from_user.id)

    # load current user data for context/prompts
    try:
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        info = user.get("response", user)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("❌ User edit fetch failed user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())
        return

    if field == "status" and value:
        await _apply_user_update(callback, user_uuid, {"status": value}, back_to=back_to)
        return
    if field == "strategy" and value:
        await _apply_user_update(callback, user_uuid, {"trafficLimitStrategy": value}, back_to=back_to)
        return
    if field == "strategy" and not value:
        await callback.message.edit_text(
            _("user.edit_prompt_strategy"),
            reply_markup=user_edit_strategy_keyboard(user_uuid, back_to=back_to),
        )
        return

    current_values = _current_user_edit_values(info)

    if field == "squad" and not value:
        # Показываем список сквадов для выбора
        await _show_squad_selection_for_edit(callback, user_uuid, back_to)
        return
    
    if field == "squad" and value:
        # Обработка выбора сквада
        user_id = callback.from_user.id
        ctx = PENDING_INPUT.get(user_id, {})
        
        if ctx.get("action") == "user_edit_squad" and ctx.get("user_uuid") == user_uuid:
            squads = ctx.get("squads", [])
            back_to_ctx = ctx.get("back_to", back_to)
            
            if value == "remove":
                # Удаление сквада
                await _apply_user_update(callback, user_uuid, {"activeInternalSquads": []}, back_to=back_to_ctx)
                PENDING_INPUT.pop(user_id, None)
                return
            else:
                # Выбор сквада по индексу
                try:
                    squad_idx = int(value)
                    if 0 <= squad_idx < len(squads):
                        squad = squads[squad_idx]
                        squad_uuid = squad.get("uuid")
                        squad_type = ctx.get("squad_type", "internal")
                        
                        if squad_type == "external":
                            update_data = {"externalSquadUuid": squad_uuid, "activeInternalSquads": []}
                        else:
                            update_data = {"activeInternalSquads": [squad_uuid], "externalSquadUuid": None}
                        
                        await _apply_user_update(callback, user_uuid, update_data, back_to=back_to_ctx)
                        PENDING_INPUT.pop(user_id, None)
                        return
                except (ValueError, IndexError):
                    logger.warning("Invalid squad index: %s", value)
        
        # Если контекст не найден или индекс невалидный, показываем меню заново
        await _show_squad_selection_for_edit(callback, user_uuid, back_to)
        return

    prompt_map = {
        "traffic": _("user.edit_prompt_traffic"),
        "expire": _("user.edit_prompt_expire"),
        "hwid": _("user.edit_prompt_hwid"),
        "description": _("user.edit_prompt_description"),
        "tag": _("user.edit_prompt_tag"),
        "telegram": _("user.edit_prompt_telegram"),
        "email": _("user.edit_prompt_email"),
    }
    prompt = prompt_map.get(field, _("errors.generic"))
    if prompt == _("errors.generic"):
        await callback.message.edit_text(prompt, reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))
        return

    current_line = _("user.current").format(value=current_values.get(field, _("user.not_set")))
    prompt = f"{prompt}\n{current_line}"

    PENDING_INPUT[callback.from_user.id] = {
        "action": "user_edit",
        "field": field,
        "uuid": user_uuid,
        "back_to": back_to,
    }
    await callback.message.edit_text(prompt, reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))


@router.callback_query(F.data.startswith("user_configs:") | F.data.startswith("ucfg:"))
async def cb_user_configs(callback: CallbackQuery) -> None:
    """Обработчик просмотра конфигураций пользователя (подписные ссылки)."""
    if await _not_admin(callback):
        return
    await callback.answer()
    # Поддерживаем оба формата для обратной совместимости
    if callback.data.startswith("ucfg:"):
        user_uuid = callback.data.split(":", 1)[1]
    else:
        user_uuid = callback.data.split(":", 1)[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        short_uuid = user_info.get("shortUuid")
        subscription_url = user_info.get("subscriptionUrl")

        subscription_links = []
        happ_crypto_link = None

        # Получаем подписные ссылки из информации о подписке
        subscription_data = None
        accessible_nodes = []
        if short_uuid:
            try:
                sub_info = await api_client.get_subscription_info(short_uuid)
                sub_response = sub_info.get("response", sub_info)
                
                # Логируем структуру ответа для отладки
                logger.info("Subscription info API response: type=%s, keys=%s", type(sub_response).__name__, list(sub_response.keys()) if isinstance(sub_response, dict) else "N/A")
                if isinstance(sub_response, dict):
                    logger.info("Subscription info content (first 1000 chars): %s", str(sub_response)[:1000])
                
                subscription_data = sub_response
                # Инициализируем список ссылок (будет заполнен при обработке)
                subscription_links = []
            except Exception:
                logger.exception("Failed to fetch subscription links for user %s", short_uuid)
                subscription_links = []
        else:
            subscription_links = []
        
        # Получаем доступные ноды пользователя для формирования конфигов
        try:
            nodes_data = await api_client.get_user_accessible_nodes(user_uuid)
            nodes_response = nodes_data.get("response", nodes_data)
            
            # Логируем структуру ответа для отладки
            logger.info("Accessible nodes API response: type=%s, keys=%s", type(nodes_response).__name__, list(nodes_response.keys()) if isinstance(nodes_response, dict) else "N/A")
            if isinstance(nodes_response, dict):
                logger.info("Accessible nodes content (first 1000 chars): %s", str(nodes_response)[:1000])
                # API возвращает activeNodes, а не nodes
                accessible_nodes = nodes_response.get("activeNodes", nodes_response.get("nodes", nodes_response.get("data", [])))
            elif isinstance(nodes_response, list):
                accessible_nodes = nodes_response
            else:
                accessible_nodes = []
            logger.info("User accessible nodes count: %s", len(accessible_nodes) if isinstance(accessible_nodes, list) else 0)
        except Exception:
            logger.exception("Failed to fetch accessible nodes for user %s", user_uuid)
            accessible_nodes = []

        # Получаем Happ crypto link, если есть subscriptionUrl
        if subscription_url:
            try:
                happ_response = await api_client.encrypt_happ_crypto_link(subscription_url)
                happ_crypto_link = happ_response.get("response", {}).get("encryptedLink")
            except Exception:
                logger.debug("Failed to encrypt Happ crypto link for user %s", short_uuid)

        # Формируем текст и клавиатуру
        text_lines = [_("user.configs_title")]

        keyboard_rows: list[list[InlineKeyboardButton]] = []

        # Обрабатываем подписные ссылки с группировкой по серверам/нодам
        if subscription_data and isinstance(subscription_data, dict):
            # Пробуем получить структурированные данные о конфигах
            configs_by_node = subscription_data.get("configsByNode", subscription_data.get("nodes", []))
            links_list = subscription_data.get("links", subscription_data.get("subscriptionLinks", []))
            ss_conf_links = subscription_data.get("ssConfLinks", {})
            
            # Обрабатываем ssConfLinks (объект с конфигами по протоколам/нодам)
            if ss_conf_links and isinstance(ss_conf_links, dict) and ss_conf_links:
                text_lines.append("")
                text_lines.append(_("user.configs_by_nodes_title"))
                
                link_index = 0
                # ssConfLinks может быть объектом, где ключи - это ноды или протоколы
                for key, value in ss_conf_links.items():
                    if not value:
                        continue
                    
                    # Если значение - это массив ссылок
                    if isinstance(value, list):
                        # Пробуем определить название ноды из ключа или использовать ключ как название
                        node_name = key if key else "Unknown"
                        
                        # Формируем заголовок для ноды/протокола
                        text_lines.append(f"\n<b>🖥 {_esc(node_name)}</b>")
                        
                        for link in value:
                            if not isinstance(link, str):
                                continue
                            
                            protocol_type = _get_protocol_type(link)
                            protocol_name = _get_protocol_name(protocol_type)
                            
                            text_lines.append(f"   {protocol_name}")
                            keyboard_rows.append([
                                InlineKeyboardButton(
                                    text=f"{protocol_name} - {node_name}",
                                    callback_data=f"user_sub_link:{user_uuid}:{link_index}",
                                )
                            ])
                            subscription_links.append(link)
                            link_index += 1
                    # Если значение - это объект с дополнительной информацией
                    elif isinstance(value, dict):
                        node_name = value.get("nodeName", value.get("name", key))
                        node_country = value.get("countryCode", value.get("country", ""))
                        protocols = value.get("protocols", value.get("links", []))
                        
                        country_display = f" ({node_country})" if node_country else ""
                        text_lines.append(f"\n<b>🖥 {_esc(node_name)}{country_display}</b>")
                        
                        if isinstance(protocols, list):
                            for protocol in protocols:
                                if isinstance(protocol, str):
                                    protocol_type = _get_protocol_type(protocol)
                                    protocol_name = _get_protocol_name(protocol_type)
                                    
                                    text_lines.append(f"   {protocol_name}")
                                    keyboard_rows.append([
                                        InlineKeyboardButton(
                                            text=f"{protocol_name} - {node_name}",
                                            callback_data=f"user_sub_link:{user_uuid}:{link_index}",
                                        )
                                    ])
                                    subscription_links.append(protocol)
                                    link_index += 1
                                elif isinstance(protocol, dict):
                                    protocol_link = protocol.get("link", protocol.get("url", ""))
                                    if protocol_link:
                                        protocol_type = _get_protocol_type(protocol_link)
                                        protocol_name = _get_protocol_name(protocol_type)
                                        
                                        text_lines.append(f"   {protocol_name}")
                                        keyboard_rows.append([
                                            InlineKeyboardButton(
                                                text=f"{protocol_name} - {node_name}",
                                                callback_data=f"user_sub_link:{user_uuid}:{link_index}",
                                            )
                                        ])
                                        subscription_links.append(protocol_link)
                                        link_index += 1
            
            # Если есть структурированные данные по нодам
            elif configs_by_node and isinstance(configs_by_node, list):
                text_lines.append("")
                text_lines.append(_("user.configs_by_nodes_title"))
                
                link_index = 0
                for node_config in configs_by_node:
                    if not isinstance(node_config, dict):
                        continue
                    
                    node_name = node_config.get("nodeName", node_config.get("name", "Unknown"))
                    node_country = node_config.get("countryCode", node_config.get("country", ""))
                    node_protocols = node_config.get("protocols", node_config.get("links", []))
                    
                    # Формируем заголовок для ноды
                    country_display = f" ({node_country})" if node_country else ""
                    text_lines.append(f"\n<b>🖥 {_esc(node_name)}{country_display}</b>")
                    
                    # Добавляем протоколы для этой ноды
                    if isinstance(node_protocols, list):
                        for protocol in node_protocols:
                            if not isinstance(protocol, dict):
                                # Если это строка, используем её как ссылку
                                if isinstance(protocol, str):
                                    protocol_link = protocol
                                    protocol_type = _get_protocol_type(protocol_link)
                                    protocol_name = _get_protocol_name(protocol_type)
                                    
                                    text_lines.append(f"   {protocol_name}")
                                    keyboard_rows.append([
                                        InlineKeyboardButton(
                                            text=f"{protocol_name} - {node_name}",
                                            callback_data=f"user_sub_link:{user_uuid}:{link_index}",
                                        )
                                    ])
                                    # Сохраняем ссылку для последующего отображения
                                    if link_index < len(subscription_links):
                                        subscription_links[link_index] = protocol_link
                                    else:
                                        subscription_links.append(protocol_link)
                                    link_index += 1
                                continue
                            
                            # Если это объект с информацией о протоколе
                            protocol_link = protocol.get("link", protocol.get("url", ""))
                            protocol_type = protocol.get("type", protocol.get("protocol", ""))
                            if not protocol_type and protocol_link:
                                protocol_type = _get_protocol_type(protocol_link)
                            
                            if protocol_link:
                                protocol_name = _get_protocol_name(protocol_type)
                                text_lines.append(f"   {protocol_name}")
                                keyboard_rows.append([
                                    InlineKeyboardButton(
                                        text=f"{protocol_name} - {node_name}",
                                        callback_data=f"user_sub_link:{user_uuid}:{link_index}",
                                    )
                                ])
                                # Сохраняем ссылку для последующего отображения
                                if link_index < len(subscription_links):
                                    subscription_links[link_index] = protocol_link
                                else:
                                    subscription_links.append(protocol_link)
                                link_index += 1
            # Если есть просто список ссылок
            elif links_list and isinstance(links_list, list):
                text_lines.append("")
                text_lines.append(_("user.subscription_links_title"))
                for i, link in enumerate(links_list[:20]):  # Увеличиваем лимит до 20 ссылок
                    if not isinstance(link, str):
                        continue
                    
                    protocol_type = _get_protocol_type(link)
                    protocol_name = _get_protocol_name(protocol_type)
                    text_lines.append(f"   {protocol_name} {i+1}")
                    
                    keyboard_rows.append([
                        InlineKeyboardButton(
                            text=f"{protocol_name} {i+1}",
                            callback_data=f"user_sub_link:{user_uuid}:{i}",
                        )
                    ])
                    subscription_links.append(link)
            
            # Если конфигов нет в subscription_data, но есть доступные ноды, формируем конфиги на основе нод
            if not subscription_links and accessible_nodes and isinstance(accessible_nodes, list) and len(accessible_nodes) > 0:
                logger.info("No links in subscription_data, generating from accessible nodes. Nodes count: %s", len(accessible_nodes))
                
                # Получаем все хосты для получения адресов и портов (из БД с fallback на API)
                try:
                    hosts = await data_access.get_all_hosts()
                    hosts_dict = {h.get("uuid"): h for h in hosts if isinstance(h, dict)}
                except Exception:
                    logger.exception("Failed to get hosts for accessible nodes")
                    hosts_dict = {}
                
                # Получаем все ноды для получения hostUuid (из БД с fallback на API)
                try:
                    all_nodes = await data_access.get_all_nodes()
                    nodes_dict = {n.get("uuid"): n for n in all_nodes if isinstance(n, dict)}
                except Exception:
                    logger.exception("Failed to get nodes for accessible nodes")
                    nodes_dict = {}
                
                text_lines.append("")
                text_lines.append(_("user.configs_by_nodes_title"))
                
                # Получаем информацию о пользователе для формирования ссылок
                vless_uuid = user_info.get("vlessUuid")
                trojan_password = user_info.get("trojanPassword")
                ss_password = user_info.get("ssPassword")
                logger.info("User protocols: vless_uuid=%s, trojan=%s, ss=%s", bool(vless_uuid), bool(trojan_password), bool(ss_password))
                
                # Используем индекс вместо UUID для callback_data (лимит Telegram - 64 байта)
                for node_index, node in enumerate(accessible_nodes):
                    if not isinstance(node, dict):
                        logger.debug("Skipping non-dict node: %s", type(node))
                        continue
                    
                    # В accessible-nodes используется nodeName, а не name
                    node_name = node.get("nodeName", node.get("name", "Unknown"))
                    node_country = node.get("countryCode", node.get("country", ""))
                    node_uuid = node.get("uuid", "")
                    logger.info("Processing accessible node: name=%s, uuid=%s, country=%s", node_name, node_uuid, node_country)
                    
                    # Получаем адрес и порт из хоста через ноду
                    node_info = nodes_dict.get(node_uuid)
                    if not node_info:
                        logger.warning("Node info not found for uuid %s (node: %s). Available node UUIDs: %s", node_uuid, node_name, list(nodes_dict.keys())[:5])
                        continue
                    
                    # Логируем структуру ноды для отладки
                    logger.info("Node info for %s: keys=%s", node_name, list(node_info.keys())[:10])
                    
                    # Пробуем получить адрес и порт напрямую из ноды (как в nodes.py)
                    node_address = node_info.get("address", "")
                    node_port = node_info.get("port")
                    
                    # Если адрес и порт не найдены в ноде, пробуем получить через хост
                    if not node_address or not node_port:
                        host_uuid = node_info.get("hostUuid")
                        if not host_uuid:
                            # Пробуем альтернативные поля
                            host_uuid = node_info.get("host", {}).get("uuid") if isinstance(node_info.get("host"), dict) else None
                        
                        if host_uuid:
                            host = hosts_dict.get(host_uuid)
                            if host:
                                node_address = host.get("address", "")
                                node_port = host.get("port")
                                logger.info("Got address/port from host for node %s: address=%s, port=%s", node_name, node_address, node_port)
                            else:
                                logger.warning("Host not found for uuid %s (node: %s)", host_uuid, node_name)
                        else:
                            logger.warning("Host UUID not found for node %s (uuid: %s). Node keys: %s", node_name, node_uuid, list(node_info.keys())[:10])
                    
                    logger.info("Node %s: address=%s, port=%s", node_name, node_address, node_port)
                    
                    # Пропускаем ноды без адреса или порта
                    if not node_address or not node_port:
                        logger.warning("Node %s missing address or port: address=%s, port=%s", node_name, node_address, node_port)
                        continue
                    
                    country_display = f" ({node_country})" if node_country else ""
                    text_lines.append(f"\n<b>🖥 {_esc(node_name)}{country_display}</b>")
                    logger.info("Adding configs for node %s: vless=%s, trojan=%s, ss=%s", node_name, bool(vless_uuid), bool(trojan_password), bool(ss_password))
                    
                    # Проверяем, есть ли хотя бы один протокол для этой ноды
                    has_protocols = bool(vless_uuid or trojan_password or ss_password)
                    
                    if has_protocols:
                        # Добавляем кнопку для ноды
                        # Используем индекс вместо UUID для callback_data (лимит Telegram - 64 байта)
                        # Формат: unc:{user_uuid}:{node_index} (unc = user node configs)
                        # Сохраняем node_uuid для последующего использования
                        keyboard_rows.append([
                            InlineKeyboardButton(
                                text=f"🖥 {node_name}{country_display}",
                                callback_data=f"unc:{user_uuid}:{node_index}",
                            )
                        ])

        # Если конфигов нет, но есть доступные ноды, пробуем получить все ноды и сформировать конфиги
        if not subscription_links and not accessible_nodes:
            logger.info("No subscription links and no accessible nodes, trying to get all nodes")
            try:
                # Получаем все ноды и хосты один раз (из БД с fallback на API)
                all_nodes = await data_access.get_all_nodes()
                hosts = await data_access.get_all_hosts()
                
                # Создаем словарь хостов для быстрого поиска
                hosts_dict = {h.get("uuid"): h for h in hosts if isinstance(h, dict)}
                
                if isinstance(all_nodes, list) and len(all_nodes) > 0:
                    # Фильтруем только включенные ноды
                    enabled_nodes = [n for n in all_nodes if not n.get("isDisabled") and n.get("isConnected")]
                    if enabled_nodes:
                        logger.info("Found %s enabled and connected nodes, generating configs", len(enabled_nodes))
                        text_lines.append("")
                        text_lines.append(_("user.configs_by_nodes_title"))
                        
                        link_index = 0
                        vless_uuid = user_info.get("vlessUuid")
                        trojan_password = user_info.get("trojanPassword")
                        ss_password = user_info.get("ssPassword")
                        
                        # В fallback коде мы не можем использовать индексы из accessible_nodes,
                        # так как здесь используются все ноды. Поэтому просто не добавляем кнопки
                        # для этого случая - пользователь должен использовать accessible_nodes путь
                        for node in enabled_nodes[:20]:  # Ограничиваем до 20 нод
                            if not isinstance(node, dict):
                                continue
                            
                            node_name = node.get("name", node.get("remark", "Unknown"))
                            node_country = node.get("countryCode", node.get("country", ""))
                            # Получаем адрес и порт из хоста
                            host_uuid = node.get("hostUuid")
                            if not host_uuid:
                                continue
                            
                            host = hosts_dict.get(host_uuid)
                            if not host:
                                continue
                            
                            node_address = host.get("address", "")
                            node_port = host.get("port")
                            
                            if not node_address or not node_port:
                                continue
                            
                            country_display = f" ({node_country})" if node_country else ""
                            text_lines.append(f"\n<b>🖥 {_esc(node_name)}{country_display}</b>")
                            
                            # В fallback коде не добавляем кнопки, так как здесь используются все ноды,
                            # а не accessible_nodes, поэтому индексы не совпадут
            except Exception:
                logger.exception("Failed to get all nodes for config generation")
        
        logger.info("Final subscription_links count: %s, happ_crypto_link: %s", len(subscription_links), bool(happ_crypto_link))
        
        if not subscription_links and not happ_crypto_link:
            text_lines.append("")
            text_lines.append(_("user.no_subscription_links"))

        # Добавляем кнопку для Happ crypto link
        if happ_crypto_link:
            text_lines.append("")
            text_lines.append(_("user.happ_crypto_link_title"))
            # Для Happ crypto link используем callback, так как это не URL
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=_("user.happ_crypto_link_button"),
                        callback_data=f"uhapp:{user_uuid}",
                    )
                ]
            )

        text = "\n".join(text_lines)

        # Добавляем кнопку "Назад"
        keyboard_rows.append(nav_row(back_to))
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to fetch configs for user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("unc:"))
async def cb_user_node_configs(callback: CallbackQuery) -> None:
    """Обработчик для отображения протоколов конкретной ноды."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    user_uuid = parts[1]
    try:
        node_index = int(parts[2])
    except ValueError:
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(_get_user_detail_back_target(callback.from_user.id)))
        return
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        
        # Получаем доступные ноды
        nodes_data = await api_client.get_user_accessible_nodes(user_uuid)
        nodes_response = nodes_data.get("response", nodes_data)
        accessible_nodes = nodes_response.get("activeNodes", []) if isinstance(nodes_response, dict) else []
        
        # Получаем ноду по индексу
        if node_index >= len(accessible_nodes) or node_index < 0:
            await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
            return
        
        node_info = accessible_nodes[node_index]
        if not isinstance(node_info, dict):
            await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
            return
        
        node_name = node_info.get("nodeName", node_info.get("name", "Unknown"))
        node_country = node_info.get("countryCode", node_info.get("country", ""))
        node_uuid = node_info.get("uuid", "")
        
        # Получаем все ноды для получения адресов и портов (из БД с fallback на API)
        all_nodes = await data_access.get_all_nodes()
        nodes_dict = {n.get("uuid"): n for n in all_nodes if isinstance(n, dict)}
        
        node_details = nodes_dict.get(node_uuid)
        if not node_details:
            await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
            return
        
        node_address = node_details.get("address", "")
        node_port = node_details.get("port")
        
        if not node_address or not node_port:
            await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
            return
        
        # Получаем протоколы пользователя
        vless_uuid = user_info.get("vlessUuid")
        trojan_password = user_info.get("trojanPassword")
        ss_password = user_info.get("ssPassword")
        
        # Определяем доступные протоколы
        node_links = {}
        if vless_uuid:
            node_links["vless"] = True
        if trojan_password:
            node_links["trojan"] = True
        if ss_password:
            node_links["ss"] = True
        
        if not node_links:
            await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
            return
        
        # Формируем текст и кнопки
        country_display = f" ({node_country})" if node_country else ""
        text_lines = [
            f"<b>🖥 {_esc(node_name)}{country_display}</b>",
            "",
            "Выберите протокол:",
        ]
        
        keyboard_rows = []
        
        # Определяем индексы протоколов (0=vless, 1=trojan, 2=ss)
        protocol_index = 0
        if "vless" in node_links:
            text_lines.append("   🔷 VLESS")
            keyboard_rows.append([
                InlineKeyboardButton(
                    text="🔷 VLESS",
                    callback_data=f"usl:{user_uuid}:{node_index}:{protocol_index}",
                )
            ])
            protocol_index += 1
        
        if "trojan" in node_links:
            text_lines.append("   🔴 Trojan")
            keyboard_rows.append([
                InlineKeyboardButton(
                    text="🔴 Trojan",
                    callback_data=f"usl:{user_uuid}:{node_index}:{protocol_index}",
                )
            ])
            protocol_index += 1
        
        if "ss" in node_links:
            text_lines.append("   🔶 SS")
            keyboard_rows.append([
                InlineKeyboardButton(
                    text="🔶 SS",
                    callback_data=f"usl:{user_uuid}:{node_index}:{protocol_index}",
                )
            ])
            protocol_index += 1
        
        # Добавляем кнопку "Назад"
        keyboard_rows.append([InlineKeyboardButton(text=_("user.back_to_configs"), callback_data=f"ucfg:{user_uuid}")])
        keyboard_rows.append(nav_row(back_to))
        
        text = "\n".join(text_lines)
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
        
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to fetch node configs for user_uuid=%s node_index=%s actor_id=%s", user_uuid, node_index, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
    except Exception:
        logger.exception("Unexpected error in cb_user_node_configs")
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("usl:") | F.data.startswith("user_sub_link:"))
async def cb_user_sub_link(callback: CallbackQuery) -> None:
    """Обработчик для отображения подписной ссылки."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    user_uuid = parts[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        
        # Проверяем формат callback_data
        # Новый формат: usl:{user_uuid}:{node_index}:{protocol_index}
        # Старый формат: user_sub_link:{user_uuid}:{link_index} (для обратной совместимости)
        if len(parts) >= 4:
            # Новый формат - по индексу ноды и индексу протокола
            try:
                node_index = int(parts[2])
                protocol_index = int(parts[3])
            except ValueError:
                await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
                return
            
            # Получаем доступные ноды
            nodes_data = await api_client.get_user_accessible_nodes(user_uuid)
            nodes_response = nodes_data.get("response", nodes_data)
            accessible_nodes = nodes_response.get("activeNodes", []) if isinstance(nodes_response, dict) else []
            
            # Получаем ноду по индексу
            if node_index >= len(accessible_nodes) or node_index < 0:
                await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
                return
            
            node_info = accessible_nodes[node_index]
            if not isinstance(node_info, dict):
                await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
                return
            
            node_name = node_info.get("nodeName", node_info.get("name", "Unknown"))
            node_uuid = node_info.get("uuid", "")
            
            # Получаем все ноды для получения адресов и портов (из БД с fallback на API)
            all_nodes = await data_access.get_all_nodes()
            nodes_dict = {n.get("uuid"): n for n in all_nodes if isinstance(n, dict)}
            
            node_details = nodes_dict.get(node_uuid)
            if not node_details:
                await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
                return
            
            node_address = node_details.get("address", "")
            node_port = node_details.get("port")
            
            if not node_address or not node_port:
                await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
                return
            
            # Генерируем ссылку для конкретного протокола по индексу
            vless_uuid = user_info.get("vlessUuid")
            trojan_password = user_info.get("trojanPassword")
            ss_password = user_info.get("ssPassword")
            
            # Определяем протокол по индексу (0=vless, 1=trojan, 2=ss)
            protocols = []
            if vless_uuid:
                protocols.append("vless")
            if trojan_password:
                protocols.append("trojan")
            if ss_password:
                protocols.append("ss")
            
            if protocol_index >= len(protocols) or protocol_index < 0:
                await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
                return
            
            protocol = protocols[protocol_index]
            link = None
            link_type = ""
            
            if protocol == "vless":
                link = f"vless://{vless_uuid}@{node_address}:{node_port}?type=tcp&security=none#VLESS-{_esc(node_name)}"
                link_type = "🔷 VLESS"
            elif protocol == "trojan":
                link = f"trojan://{trojan_password}@{node_address}:{node_port}?type=tcp#Trojan-{_esc(node_name)}"
                link_type = "🔴 Trojan"
            elif protocol == "ss":
                ss_method = "aes-256-gcm"
                ss_encoded = base64.b64encode(f"{ss_method}:{ss_password}@{node_address}:{node_port}".encode()).decode()
                link = f"ss://{ss_encoded}#SS-{_esc(node_name)}"
                link_type = "🔶 SS"
            
            if not link:
                await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
                return
        else:
            # Старый формат - по индексу (для обратной совместимости)
            try:
                link_index = int(parts[2])
            except ValueError:
                await callback.message.edit_text(
                    _("errors.generic"), reply_markup=nav_keyboard(_get_user_detail_back_target(callback.from_user.id))
                )
                return
            
            short_uuid = user_info.get("shortUuid")
            
            # Собираем все ссылки (как в cb_user_configs)
            subscription_links = []
            
            # Получаем подписные ссылки из информации о подписке
            if short_uuid:
                try:
                    sub_info = await api_client.get_subscription_info(short_uuid)
                    sub_response = sub_info.get("response", sub_info)
                    
                    configs_by_node = sub_response.get("configsByNode", sub_response.get("nodes", []))
                    links_list = sub_response.get("links", sub_response.get("subscriptionLinks", []))
                    ss_conf_links = sub_response.get("ssConfLinks", {})
                    
                    # Обрабатываем ssConfLinks
                    if ss_conf_links and isinstance(ss_conf_links, dict) and ss_conf_links:
                        for key, value in ss_conf_links.items():
                            if isinstance(value, list):
                                subscription_links.extend([link for link in value if isinstance(link, str)])
                            elif isinstance(value, dict):
                                protocols = value.get("protocols", value.get("links", []))
                                if isinstance(protocols, list):
                                    for protocol in protocols:
                                        if isinstance(protocol, str):
                                            subscription_links.append(protocol)
                                        elif isinstance(protocol, dict):
                                            protocol_link = protocol.get("link", protocol.get("url", ""))
                                            if protocol_link:
                                                subscription_links.append(protocol_link)
                    
                    # Обрабатываем configs_by_node
                    if configs_by_node and isinstance(configs_by_node, list):
                        for node_config in configs_by_node:
                            if not isinstance(node_config, dict):
                                continue
                            node_protocols = node_config.get("protocols", node_config.get("links", []))
                            if isinstance(node_protocols, list):
                                for protocol in node_protocols:
                                    if isinstance(protocol, str):
                                        subscription_links.append(protocol)
                                    elif isinstance(protocol, dict):
                                        protocol_link = protocol.get("link", protocol.get("url", ""))
                                        if protocol_link:
                                            subscription_links.append(protocol_link)
                    
                    # Обрабатываем links_list
                    if links_list and isinstance(links_list, list):
                        subscription_links.extend([link for link in links_list if isinstance(link, str)])
                except Exception:
                    logger.exception("Failed to fetch subscription links for user %s", short_uuid)
            
            # Если ссылок нет, генерируем из доступных нод (как в cb_user_configs)
            if not subscription_links:
                try:
                    nodes_data = await api_client.get_user_accessible_nodes(user_uuid)
                    nodes_response = nodes_data.get("response", nodes_data)
                    accessible_nodes = nodes_response.get("activeNodes", []) if isinstance(nodes_response, dict) else []
                    
                    if accessible_nodes and isinstance(accessible_nodes, list):
                        # Получаем все ноды для получения адресов и портов (из БД с fallback на API)
                        all_nodes = await data_access.get_all_nodes()
                        nodes_dict = {n.get("uuid"): n for n in all_nodes if isinstance(n, dict)}
                        
                        vless_uuid = user_info.get("vlessUuid")
                        trojan_password = user_info.get("trojanPassword")
                        ss_password = user_info.get("ssPassword")
                        
                        for node in accessible_nodes:
                            if not isinstance(node, dict):
                                continue
                            
                            node_uuid = node.get("uuid", "")
                            node_info = nodes_dict.get(node_uuid)
                            if not node_info:
                                continue
                            
                            node_address = node_info.get("address", "")
                            node_port = node_info.get("port")
                            
                            if not node_address or not node_port:
                                continue
                            
                            # Генерируем ссылки для доступных протоколов
                            if vless_uuid:
                                vless_link = f"vless://{vless_uuid}@{node_address}:{node_port}?type=tcp&security=none#VLESS"
                                subscription_links.append(vless_link)
                            
                            if trojan_password:
                                trojan_link = f"trojan://{trojan_password}@{node_address}:{node_port}?type=tcp#Trojan"
                                subscription_links.append(trojan_link)
                            
                            if ss_password:
                                ss_method = "aes-256-gcm"
                                ss_encoded = base64.b64encode(f"{ss_method}:{ss_password}@{node_address}:{node_port}".encode()).decode()
                                ss_link = f"ss://{ss_encoded}#SS"
                                subscription_links.append(ss_link)
                except Exception:
                    logger.exception("Failed to generate links from accessible nodes")

            if link_index >= len(subscription_links):
                await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
                return

            link = subscription_links[link_index]
            
            # Определяем тип ссылки для заголовка
            protocol_type = _get_protocol_type(link)
            link_type = _get_protocol_name(protocol_type)

        # Отображаем ссылку
        text = f"{link_type}\n\n<code>{_esc(link)}</code>"
        
        # Определяем, откуда вернуться (к конфигам ноды или к списку нод)
        if len(parts) >= 4:
            # Новый формат - возвращаемся к протоколам ноды
            try:
                node_index = int(parts[2])
                back_button = InlineKeyboardButton(
                    text=_("actions.back"),
                    callback_data=f"unc:{user_uuid}:{node_index}"
                )
            except ValueError:
                back_button = InlineKeyboardButton(
                    text=_("user.back_to_configs"),
                    callback_data=f"ucfg:{user_uuid}"
                )
        else:
            # Старый формат - возвращаемся к списку конфигов
            back_button = InlineKeyboardButton(
                text=_("user.back_to_configs"),
                callback_data=f"ucfg:{user_uuid}"
            )
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [back_button],
                nav_row(back_to),
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception(
            "Failed to get subscription link for user_uuid=%s link_index=%s actor_id=%s",
            user_uuid,
            link_index,
            callback.from_user.id,
        )
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("user_happ_link:") | F.data.startswith("uhapp:"))
async def cb_user_happ_link(callback: CallbackQuery) -> None:
    """Обработчик для отображения Happ crypto link."""
    if await _not_admin(callback):
        return
    await callback.answer()
    # Поддерживаем оба формата для обратной совместимости
    if callback.data.startswith("uhapp:"):
        user_uuid = callback.data.split(":", 1)[1]
    else:
        user_uuid = callback.data.split(":", 1)[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        subscription_url = user_info.get("subscriptionUrl")

        if not subscription_url:
            await callback.message.edit_text(_("user.no_subscription_url"), reply_markup=nav_keyboard(back_to))
            return

        # Получаем Happ crypto link
        happ_response = await api_client.encrypt_happ_crypto_link(subscription_url)
        happ_crypto_link = happ_response.get("response", {}).get("encryptedLink")

        if not happ_crypto_link:
            await callback.message.edit_text(_("user.happ_crypto_link_error"), reply_markup=nav_keyboard(back_to))
            return

        # Отображаем Happ crypto link
        text = f"{_('user.happ_crypto_link_title')}\n\n<code>{_esc(happ_crypto_link)}</code>"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=_("user.back_to_configs"), callback_data=f"ucfg:{user_uuid}")],
                nav_row(back_to),
            ]
        )

        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get Happ crypto link for user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("user_traffic_nodes:"))
async def cb_user_traffic_nodes(callback: CallbackQuery) -> None:
    """Обработчик для быстрого доступа к статистике трафика по нодам."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    
    user_uuid = parts[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)
    
    try:
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        username = user_info.get("username", "n/a")
        
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Сохраняем user_uuid в контексте, чтобы использовать короткий callback_data
        user_id = callback.from_user.id
        PENDING_INPUT[user_id] = {
            "action": "user_traffic_nodes",
            "user_uuid": user_uuid,
            "back_to": back_to,
        }
        
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_("user.stats.period_today"),
                        callback_data=f"utn:today",
                    ),
                    InlineKeyboardButton(
                        text=_("user.stats.period_week"),
                        callback_data=f"utn:week",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=_("user.stats.period_month"),
                        callback_data=f"utn:month",
                    ),
                    InlineKeyboardButton(
                        text=_("user.stats.period_3months"),
                        callback_data=f"utn:3months",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text=_("user.stats.period_year"),
                        callback_data=f"utn:year",
                    ),
                ],
                [InlineKeyboardButton(text=_("user.back_to_actions"), callback_data=f"user_actions:{user_uuid}")],
                nav_row(back_to),
            ]
        )
        text = _("user.traffic_by_nodes_title").format(username=_esc(username))
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
        
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user traffic nodes menu user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("user_stats:"))
async def cb_user_stats(callback: CallbackQuery) -> None:
    """Обработчик статистики пользователя."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return

    # Формат: user_stats:{action}:{user_uuid} или user_stats:{user_uuid}
    if len(parts) == 2:
        # Только user_uuid, показываем меню
        user_uuid = parts[1]
        action = None
    else:
        action = parts[1]
        user_uuid = parts[2]

    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        if action == "sub_history":
            # История запросов подписки
            history_data = await api_client.get_user_subscription_request_history(user_uuid)
            history = history_data.get("response", {}).get("records", [])

            if not history:
                text = _("user.stats.subscription_history_title") + "\n\n" + _("user.stats.subscription_history_empty")
            else:
                lines = [_("user.stats.subscription_history_title"), ""]
                for i, record in enumerate(history[:20], 1):  # Ограничиваем до 20 записей
                    date = format_datetime(record.get("requestAt"))
                    user_agent = record.get("userAgent", "—")
                    request_ip = record.get("requestIp", "—")
                    lines.append(
                        _("user.stats.subscription_history_item").format(
                            index=i,
                            date=date,
                            userAgent=_esc(user_agent[:50]) if user_agent else "—",
                            ip=_esc(request_ip) if request_ip else "—",
                        )
                    )
                text = "\n".join(lines)

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
                ]
            )
            await _edit_text_safe(callback.message, text, reply_markup=keyboard, parse_mode="HTML")

        elif action == "traffic":
            # Статистика трафика - показываем меню выбора периода
            from datetime import datetime, timedelta

            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("user.stats.period_today"),
                            callback_data=f"ust:t:{user_uuid}:today",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_week"),
                            callback_data=f"ust:t:{user_uuid}:week",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text=_("user.stats.period_month"),
                            callback_data=f"ust:t:{user_uuid}:month",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_custom"),
                            callback_data=f"ust:t:{user_uuid}:custom",
                        ),
                    ],
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
                ]
            )
            await _edit_text_safe(callback.message, _("user.stats.select_period"), reply_markup=keyboard)

        elif action == "nodes":
            # Использование нод - показываем меню выбора периода
            from datetime import datetime, timedelta

            now = datetime.utcnow()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [
                        InlineKeyboardButton(
                            text=_("user.stats.period_today"),
                            callback_data=f"ust:n:{user_uuid}:today",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_week"),
                            callback_data=f"ust:n:{user_uuid}:week",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text=_("user.stats.period_month"),
                            callback_data=f"ust:n:{user_uuid}:month",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_custom"),
                            callback_data=f"ust:n:{user_uuid}:custom",
                        ),
                    ],
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:nodes:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
                ]
            )
            await _edit_text_safe(callback.message, _("user.stats.select_period"), reply_markup=keyboard)

        elif action == "hwid":
            # Статистика по устройствам
            hwid_data = await api_client.get_hwid_devices_stats()
            stats = hwid_data.get("response", {})

            total_devices = stats.get("totalDevices", 0)
            active_devices = stats.get("activeDevices", 0)
            inactive_devices = total_devices - active_devices
            by_user = stats.get("byUser", [])

            lines = [
                _("user.stats.hwid_title"),
                "",
                _("user.stats.hwid_total").format(total=total_devices),
                _("user.stats.hwid_active").format(active=active_devices),
                _("user.stats.hwid_inactive").format(inactive=inactive_devices),
            ]

            if by_user:
                lines.append("")
                lines.append(_("user.stats.hwid_by_user"))
                for user_stat in by_user[:10]:  # Ограничиваем до 10 пользователей
                    username = user_stat.get("username", "n/a")
                    count = user_stat.get("devicesCount", 0)
                    lines.append(_("user.stats.hwid_user_item").format(username=_esc(username), count=count))

            text = "\n".join(lines)
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
                ]
            )
            await _edit_text_safe(callback.message, text, reply_markup=keyboard, parse_mode="HTML")

        else:
            # Показываем меню статистики
            user = await data_access.get_user_by_uuid_wrapped(user_uuid)
            user_info = user.get("response", user)
            username = user_info.get("username", "n/a")
            text = _("user.stats_title").format(username=_esc(username))
            await _edit_text_safe(callback.message, text, reply_markup=user_stats_keyboard(user_uuid, back_to=back_to))

    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user stats user_uuid=%s action=%s actor_id=%s", user_uuid, action, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("utn:"))
async def cb_user_traffic_nodes_period(callback: CallbackQuery) -> None:
    """Обработчик выбора периода для статистики трафика по нодам (быстрый доступ)."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    
    period = parts[1]
    user_id = callback.from_user.id
    ctx = PENDING_INPUT.get(user_id, {})
    
    if ctx.get("action") != "user_traffic_nodes":
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return
    
    user_uuid = ctx.get("user_uuid")
    back_to = ctx.get("back_to", NavTarget.USERS_MENU)
    
    if not user_uuid:
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
        return
    
    try:
        from datetime import datetime, timedelta
        
        now = datetime.utcnow()
        # Убираем микросекунды для совместимости с API
        now = now.replace(microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # API для статистики пользователя ожидает формат только с датой (YYYY-MM-DD)
        # Для end используем следующий день, чтобы включить весь последний день периода
        def format_date_only(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%d")

        if period == "today":
            # Для "сегодня" используем сегодня и завтра
            start = format_date_only(today_start)
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "week":
            start = format_date_only(today_start - timedelta(days=7))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "month":
            start = format_date_only(today_start - timedelta(days=30))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "3months":
            start = format_date_only(today_start - timedelta(days=90))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "year":
            start = format_date_only(today_start - timedelta(days=365))
            end = format_date_only(today_start + timedelta(days=1))
        else:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
            return
        
        # Получаем статистику трафика
        traffic_data = await api_client.get_user_traffic_stats(user_uuid, start, end)
        response = traffic_data.get("response", {})
        total_traffic = response.get("totalTrafficBytes", 0)
        nodes_usage = response.get("nodesUsage", [])
        
        # Для отображения: если формат только дата (YYYY-MM-DD), показываем как есть
        # Для end показываем текущий день (end - 1 день), так как мы используем следующий день для API
        from datetime import datetime as dt
        if len(end) == 10:
            end_date = dt.strptime(end, "%Y-%m-%d")
            end_display = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            end_display = format_datetime(end.replace("Z", "+00:00"))
        start_display = start if len(start) == 10 else format_datetime(start.replace("Z", "+00:00"))
        
        lines = [
            _("user.stats.traffic_title"),
            "",
            _("user.stats.traffic_period").format(
                start=start_display,
                end=end_display,
            ),
            _("user.stats.traffic_total").format(total=format_bytes(total_traffic)),
        ]
        
        if nodes_usage:
            lines.append("")
            lines.append(_("user.stats.traffic_by_node"))
            for node in nodes_usage:
                node_name = node.get("nodeName", "n/a")
                country = node.get("countryCode", "—")
                traffic_bytes = node.get("trafficBytes", 0)
                lines.append(
                    _("user.stats.traffic_node_item").format(
                        nodeName=_esc(node_name), country=country, traffic=format_bytes(traffic_bytes)
                    )
                )
        
        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=_("user.back_to_actions"), callback_data=f"user_actions:{user_uuid}")],
                nav_row(back_to),
            ]
        )
        await _edit_text_safe(callback.message, text, reply_markup=keyboard, parse_mode="HTML")
        # Очищаем контекст после использования
        PENDING_INPUT.pop(user_id, None)
        
    except UnauthorizedError:
        PENDING_INPUT.pop(user_id, None)
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        PENDING_INPUT.pop(user_id, None)
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        PENDING_INPUT.pop(user_id, None)
        logger.exception("Failed to get user traffic stats user_uuid=%s period=%s actor_id=%s", user_uuid, period, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("ust:t:"))
async def cb_user_stats_traffic_period(callback: CallbackQuery) -> None:
    """Обработчик выбора периода для статистики трафика."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 4:
        return

    user_uuid = parts[2]
    period = parts[3]
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        # Убираем микросекунды для совместимости с API
        now = now.replace(microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # API для статистики пользователя ожидает формат только с датой (YYYY-MM-DD)
        # Для end используем следующий день, чтобы включить весь последний день периода
        def format_date_only(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%d")

        if period == "today":
            # Для "сегодня" используем сегодня и завтра
            start = format_date_only(today_start)
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "week":
            start = format_date_only(today_start - timedelta(days=7))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "month":
            start = format_date_only(today_start - timedelta(days=30))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "3months":
            start = format_date_only(today_start - timedelta(days=90))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "year":
            start = format_date_only(today_start - timedelta(days=365))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "custom":
            # Для произвольного периода нужно будет добавить ввод дат
            await callback.message.edit_text(
                _("user.stats.custom_period_not_implemented"),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:traffic:{user_uuid}")],
                        [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                        [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
                    ]
                ),
            )
            return
        else:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
            return

        # Получаем статистику трафика
        traffic_data = await api_client.get_user_traffic_stats(user_uuid, start, end)
        
        # Логируем структуру ответа для отладки
        logger.info("User traffic stats API response: type=%s, keys=%s", type(traffic_data).__name__, list(traffic_data.keys()) if isinstance(traffic_data, dict) else "N/A")
        if isinstance(traffic_data, dict):
            logger.info("User traffic stats content (first 500 chars): %s", str(traffic_data)[:500])
        
        # API может возвращать данные в разных форматах
        response = traffic_data.get("response", traffic_data)
        if not isinstance(response, dict):
            response = {}
        
        # Пробуем разные поля для общего трафика
        total_traffic = response.get("totalTrafficBytes", response.get("total", 0))
        
        # Пробуем разные поля для использования нод
        nodes_usage = response.get("nodesUsage", response.get("topNodes", response.get("nodes", [])))
        if not isinstance(nodes_usage, list):
            nodes_usage = []
        
        logger.info("Parsed traffic stats: total_traffic=%s, nodes_usage_count=%s", total_traffic, len(nodes_usage))

        # Для отображения: если формат только дата (YYYY-MM-DD), показываем как есть
        # Для end показываем текущий день (end - 1 день), так как мы используем следующий день для API
        from datetime import datetime as dt
        if len(end) == 10:
            end_date = dt.strptime(end, "%Y-%m-%d")
            end_display = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            end_display = format_datetime(end.replace("Z", "+00:00"))
        start_display = start if len(start) == 10 else format_datetime(start.replace("Z", "+00:00"))
        
        lines = [
            _("user.stats.traffic_title"),
            "",
            _("user.stats.traffic_period").format(
                start=start_display,
                end=end_display,
            ),
            _("user.stats.traffic_total").format(total=format_bytes(total_traffic)),
        ]

        if nodes_usage and isinstance(nodes_usage, list):
            lines.append("")
            lines.append(_("user.stats.traffic_by_node"))
            for node in nodes_usage:
                if not isinstance(node, dict):
                    continue
                # Пробуем разные поля для имени ноды
                node_name = node.get("nodeName", node.get("name", "n/a"))
                # Пробуем разные поля для страны
                country = node.get("countryCode", node.get("country", "—"))
                # Пробуем разные поля для трафика
                traffic_bytes = node.get("trafficBytes", node.get("traffic", node.get("total", 0)))
                if traffic_bytes > 0:
                    lines.append(
                        _("user.stats.traffic_node_item").format(
                            nodeName=_esc(node_name), country=country, traffic=format_bytes(traffic_bytes)
                        )
                    )

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:traffic:{user_uuid}")],
                [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
            ]
        )
        await _edit_text_safe(callback.message, text, reply_markup=keyboard, parse_mode="HTML")

    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user traffic stats user_uuid=%s period=%s actor_id=%s", user_uuid, period, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("ust:n:"))
async def cb_user_stats_nodes_period(callback: CallbackQuery) -> None:
    """Обработчик выбора периода для использования нод."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 4:
        return

    user_uuid = parts[2]
    period = parts[3]
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе для получения доступных нод
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)

        # Получаем доступные ноды пользователя
        nodes_data = await api_client.get_user_accessible_nodes(user_uuid)
        nodes = nodes_data.get("response", {}).get("nodes", [])

        if not nodes:
            text = _("user.stats.nodes_usage_title") + "\n\n" + _("user.stats.nodes_usage_empty")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:nodes:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                    [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
                ]
            )
            await callback.message.edit_text(text, reply_markup=keyboard)
            return

        # Вычисляем период
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        # Убираем микросекунды для совместимости с API
        now = now.replace(microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # API для статистики пользователя ожидает формат только с датой (YYYY-MM-DD)
        # Для end используем следующий день, чтобы включить весь последний день периода
        def format_date_only(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%d")

        if period == "today":
            # Для "сегодня" используем сегодня и завтра
            start = format_date_only(today_start)
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "week":
            start = format_date_only(today_start - timedelta(days=7))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "month":
            start = format_date_only(today_start - timedelta(days=30))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "custom":
            # Для произвольного периода нужно будет добавить ввод дат
            await callback.message.edit_text(
                _("user.stats.custom_period_not_implemented"),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:nodes:{user_uuid}")],
                        [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                        [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
                    ]
                ),
            )
            return
        else:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
            return

        # Получаем статистику использования нод
        node_uuids = [n.get("uuid") for n in nodes if n.get("uuid")]
        
        # Для отображения: если формат только дата (YYYY-MM-DD), показываем как есть
        # Для end показываем текущий день (end - 1 день), так как мы используем следующий день для API
        from datetime import datetime as dt
        if len(end) == 10:
            end_date = dt.strptime(end, "%Y-%m-%d")
            end_display = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            end_display = format_datetime(end.replace("Z", "+00:00"))
        start_display = start if len(start) == 10 else format_datetime(start.replace("Z", "+00:00"))
        
        lines = [
            _("user.stats.nodes_usage_title"),
            "",
            _("user.stats.nodes_usage_period").format(
                start=start_display,
                end=end_display,
            ),
        ]

        if not node_uuids:
            lines.append(_("user.stats.nodes_usage_empty"))
        else:
            # Получаем статистику для каждой ноды
            for node_uuid in node_uuids[:10]:  # Ограничиваем до 10 нод
                try:
                    # Используем больший лимит, чтобы гарантированно получить данные пользователя
                    node_usage_data = await api_client.get_node_users_usage(node_uuid, start, end, top_users_limit=50)
                    
                    # Логируем структуру ответа для отладки
                    logger.debug("Node usage API response for node %s: type=%s, keys=%s", node_uuid, type(node_usage_data).__name__, list(node_usage_data.keys()) if isinstance(node_usage_data, dict) else "N/A")
                    
                    # API может возвращать данные в разных форматах
                    node_usage_response = node_usage_data.get("response", node_usage_data)
                    if not isinstance(node_usage_response, dict):
                        node_usage_response = {}
                    
                    top_users = node_usage_response.get("topUsers", node_usage_response.get("users", []))
                    
                    logger.debug("Parsed node usage: top_users_count=%s", len(top_users) if isinstance(top_users, list) else 0)

                    # Находим текущего пользователя в топе
                    user_traffic = 0
                    if isinstance(top_users, list):
                        for top_user in top_users:
                            if not isinstance(top_user, dict):
                                continue
                            # Пробуем разные поля для UUID пользователя
                            top_user_uuid = top_user.get("userUuid", top_user.get("uuid", ""))
                            if top_user_uuid == user_uuid:
                                # Пробуем разные поля для трафика
                                user_traffic = top_user.get("trafficBytes", top_user.get("traffic", top_user.get("total", 0)))
                                break
                    
                    logger.debug("User traffic for node %s: %s bytes", node_uuid, user_traffic)

                    # Получаем информацию о ноде
                    node_info = next((n for n in nodes if n.get("uuid") == node_uuid), {})
                    node_name = node_info.get("name", "n/a")
                    country = node_info.get("countryCode", "—")

                    if user_traffic > 0:
                        lines.append(
                            _("user.stats.traffic_node_item").format(
                                nodeName=_esc(node_name), country=country, traffic=format_bytes(user_traffic)
                            )
                        )
                except Exception:
                    logger.debug("Failed to get usage for node %s", node_uuid)
                    continue

        if len(lines) == 3:  # Только заголовок, период и пусто
            lines.append(_("user.stats.nodes_usage_empty"))

        text = "\n".join(lines)
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:nodes:{user_uuid}")],
                [InlineKeyboardButton(text=_("actions.back"), callback_data=f"user:{user_uuid}")],
                [InlineKeyboardButton(text=_("actions.main_menu"), callback_data="nav:home")],
            ]
        )
        await _edit_text_safe(callback.message, text, reply_markup=keyboard, parse_mode="HTML")

    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user nodes usage user_uuid=%s period=%s actor_id=%s", user_uuid, period, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("user_hwid_menu:"))
async def cb_user_hwid_menu(callback: CallbackQuery) -> None:
    """Обработчик меню управления HWID."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    
    user_uuid = parts[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)
    
    try:
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        info = user.get("response", user)
        username = info.get("username", "n/a")
        hwid_limit = info.get("hwidDeviceLimit")
        hwid_limit_display = _("hwid.unlimited") if not hwid_limit else str(hwid_limit)
        
        # Получаем устройства пользователя
        devices_data = await api_client.get_user_hwid_devices(user_uuid)
        devices = devices_data.get("response", {}).get("devices", [])
        
        lines = [
            f"<b>{_('user.hwid_management')}</b>",
            "",
            f"👤 <b>{_esc(username)}</b>",
            f"📊 Лимит: <code>{_esc(hwid_limit_display)}</code>",
            f"📱 Устройств: <code>{len(devices)}/{hwid_limit_display}</code>",
        ]

        # Показываем краткую информацию об устройствах (до 3 штук)
        if devices:
            lines.append("")
            lines.append("<b>📲 Устройства:</b>")
            for device in devices[:3]:
                platform = device.get("platform", "unknown")
                os_version = device.get("osVersion", "")
                platform_names = {"android": "Android", "ios": "iOS", "windows": "Windows", "macos": "macOS", "linux": "Linux"}
                platform_display = platform_names.get(platform.lower() if platform else "unknown", platform or "Unknown")
                device_str = platform_display
                if os_version:
                    device_str += f" {os_version}"
                lines.append(f"   • {_esc(device_str)}")
            if len(devices) > 3:
                lines.append(f"   <i>... и ещё {len(devices) - 3}</i>")

        text = "\n".join(lines)
        
        await callback.message.edit_text(
            text,
            reply_markup=hwid_management_keyboard(user_uuid, back_to=back_to),
            parse_mode="HTML",
        )
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user HWID menu user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("user_hwid:"))
async def cb_user_hwid_devices(callback: CallbackQuery) -> None:
    """Обработчик просмотра HWID устройств пользователя."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    
    user_uuid = parts[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)
    
    try:
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        username = user_info.get("username", "n/a")
        hwid_limit = user_info.get("hwidDeviceLimit")
        hwid_limit_display = _("hwid.unlimited") if not hwid_limit else str(hwid_limit)
        
        # Получаем устройства пользователя
        devices_data = await api_client.get_user_hwid_devices(user_uuid)
        devices = devices_data.get("response", {}).get("devices", [])
        
        lines = [
            f"<b>{_('hwid.title')}</b>",
            "",
            _("hwid.user_info").format(
                username=_esc(username),
                limit=_esc(hwid_limit_display),
                count=len(devices)
            ),
        ]
        
        if not devices:
            lines.append("")
            lines.append(_("hwid.no_devices"))
        else:
            lines.append("")
            lines.append(f"<b>{_('hwid.devices_list')}</b>")
            lines.append("")
            lines.append(f"<i>{_('hwid.click_to_delete')}</i>")
            # Используем форматтер для красивого отображения устройств
            device_lines = format_hwid_devices_list(devices, max_devices=10)
            for line in device_lines:
                lines.append(f"   {_esc(line)}")
        
        text = "\n".join(lines)
        await callback.message.edit_text(
            text,
            reply_markup=hwid_devices_keyboard(user_uuid, devices, back_to=back_to),
            parse_mode="HTML"
        )
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user HWID devices user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("hwid_delete_idx:"))
async def cb_hwid_delete(callback: CallbackQuery) -> None:
    """Обработчик удаления конкретного HWID устройства по индексу."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    
    user_uuid = parts[1]
    try:
        device_idx = int(parts[2])
    except ValueError:
        await callback.answer(_("errors.generic"), show_alert=True)
        return
    
    back_to = _get_user_detail_back_target(callback.from_user.id)
    
    try:
        # Получаем список устройств, чтобы найти HWID по индексу
        devices_data = await api_client.get_user_hwid_devices(user_uuid)
        devices = devices_data.get("response", {}).get("devices", [])
        
        if device_idx < 0 or device_idx >= len(devices):
            await callback.answer(_("hwid.device_not_found"), show_alert=True)
            return
        
        hwid = devices[device_idx].get("hwid")
        if not hwid:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
        
        await api_client.delete_user_hwid_device(user_uuid, hwid)
        await callback.answer(_("hwid.deleted"), show_alert=True)
        # Обновляем список устройств - вызываем функцию напрямую
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        username = user_info.get("username", "n/a")
        hwid_limit = user_info.get("hwidDeviceLimit")
        hwid_limit_display = _("hwid.unlimited") if not hwid_limit else str(hwid_limit)
        
        # Получаем обновленный список устройств
        devices_data = await api_client.get_user_hwid_devices(user_uuid)
        devices = devices_data.get("response", {}).get("devices", [])
        
        lines = [
            f"<b>{_('hwid.title')}</b>",
            "",
            _("hwid.user_info").format(
                username=_esc(username),
                limit=_esc(hwid_limit_display),
                count=len(devices)
            ),
        ]
        
        if not devices:
            lines.append("")
            lines.append(_("hwid.no_devices"))
        else:
            lines.append("")
            lines.append(f"<b>{_('hwid.devices_list')}</b>")
            # Используем форматтер для красивого отображения устройств
            device_lines = format_hwid_devices_list(devices, max_devices=10)
            for line in device_lines:
                lines.append(f"   {_esc(line)}")

        text = "\n".join(lines)
        await callback.message.edit_text(
            text,
            reply_markup=hwid_devices_keyboard(user_uuid, devices, back_to=back_to),
            parse_mode="HTML"
        )
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("hwid.device_not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to delete HWID device user_uuid=%s device_idx=%s actor_id=%s", user_uuid, device_idx, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("hwid_delete_all:"))
async def cb_hwid_delete_all(callback: CallbackQuery) -> None:
    """Обработчик удаления всех HWID устройств пользователя."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    
    user_uuid = parts[1]
    back_to = _get_user_detail_back_target(callback.from_user.id)
    
    try:
        await api_client.delete_all_user_hwid_devices(user_uuid)
        await callback.answer(_("hwid.all_deleted"), show_alert=True)
        # Обновляем список устройств - вызываем функцию напрямую
        # Получаем информацию о пользователе
        user = await data_access.get_user_by_uuid_wrapped(user_uuid)
        user_info = user.get("response", user)
        username = user_info.get("username", "n/a")
        hwid_limit = user_info.get("hwidDeviceLimit")
        hwid_limit_display = _("hwid.unlimited") if not hwid_limit else str(hwid_limit)
        
        # Получаем обновленный список устройств
        devices_data = await api_client.get_user_hwid_devices(user_uuid)
        devices = devices_data.get("response", {}).get("devices", [])
        
        lines = [
            f"<b>{_('hwid.title')}</b>",
            "",
            _("hwid.user_info").format(
                username=_esc(username),
                limit=_esc(hwid_limit_display),
                count=len(devices)
            ),
        ]
        
        if not devices:
            lines.append("")
            lines.append(_("hwid.no_devices"))
        else:
            lines.append("")
            lines.append(f"<b>{_('hwid.devices_list')}</b>")
            # Используем форматтер для красивого отображения устройств
            device_lines = format_hwid_devices_list(devices, max_devices=10)
            for line in device_lines:
                lines.append(f"   {_esc(line)}")

        text = "\n".join(lines)
        await callback.message.edit_text(
            text,
            reply_markup=hwid_devices_keyboard(user_uuid, devices, back_to=back_to),
            parse_mode="HTML"
        )
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to delete all HWID devices user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


