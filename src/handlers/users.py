"""Обработчики для работы с пользователями."""
from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _get_target_user_id, _not_admin, _send_clean_message
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
from src.services.api_client import ApiClientError, NotFoundError, UnauthorizedError, api_client
from src.utils.formatters import (
    _esc,
    build_created_user,
    build_user_summary,
    format_bytes,
    format_datetime,
)
from src.utils.logger import logger
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
    """Получает пользователя по запросу (username или telegram_id)."""
    if query.isdigit():
        return await api_client.get_user_by_telegram_id(int(query))
    return await api_client.get_user_by_username(query)


async def _search_users(query: str) -> list[dict]:
    """Ищет пользователей по запросу."""
    search_term = query.strip()
    if not search_term:
        return []
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
    PENDING_INPUT[message.from_user.id] = {"action": "user_search"}
    if not query:
        await _send_clean_message(message, _("user.search_prompt"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return
    await _run_user_search(message, query)


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
    
    # Отправляем уведомление о создании пользователя
    try:
        bot = target.bot if isinstance(target, Message) else target.message.bot
        await send_user_notification(bot, "created", user)
    except Exception:
        logger.exception("Failed to send user creation notification")


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

    # Получаем информацию о скваде
    active_squads = info.get("activeInternalSquads", [])
    squad_display = t("user.not_set")
    if active_squads:
        # Пытаемся получить имя сквада (если доступно в ответе)
        squad_info = info.get("internalSquads", [])
        if squad_info:
            squad_display = squad_info[0].get("name", active_squads[0]) if isinstance(squad_info, list) and len(squad_info) > 0 else active_squads[0]
        else:
            squad_display = active_squads[0] if len(active_squads) > 0 else t("user.not_set")

    return "\n".join(
        [
            t("user.edit_prompt"),
            t("user.current").format(value=""),
            f"• {t('user.edit_status_label')}: {info.get('status', 'UNKNOWN')}",
            f"• {t('user.edit_traffic_limit')}: {format_bytes(traffic_limit)}",
            f"• {t('user.edit_strategy')}: {strategy or t('user.not_set')}",
            f"• {t('user.edit_expire')}: {expire}",
            f"• {t('user.edit_hwid')}: {hwid if hwid is not None else t('user.not_set')}",
            f"• {t('user.edit_tag')}: {tag}",
            f"• {t('user.edit_telegram')}: {telegram_id}",
            f"• {t('user.edit_email')}: {email}",
            f"• {t('user.edit_description')}: {description}",
            f"• {t('user.edit_squad')}: {squad_display}",
        ]
    )


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
            old_user = await api_client.get_user_by_uuid(user_uuid)
        except Exception:
            logger.debug("Failed to get old user data for notification user_uuid=%s", user_uuid)
        
        await api_client.update_user(user_uuid, **payload)
        user = await api_client.get_user_by_uuid(user_uuid)
        info = user.get("response", user)
        text = _format_user_edit_snapshot(info, _)
        markup = user_edit_keyboard(user_uuid, back_to=back_to)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup)
        else:
            await _send_clean_message(target, text, reply_markup=markup)
        
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
        if strategy not in {"NO_RESET", "DAY", "WEEK", "MONTH"}:
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
            return
        data["username"] = text.split()[0]
        ctx["stage"] = "description"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_description"), user_create_description_keyboard(), ctx=ctx
        )
        return

    if stage == "description":
        data["description"] = text
        ctx["stage"] = "expire"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_expire"), user_create_expire_keyboard(), ctx=ctx
        )
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
            return
        data["expire_at"] = text
        ctx["stage"] = "traffic"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_traffic"), user_create_traffic_keyboard(), ctx=ctx
        )
        return

    if stage == "traffic":
        try:
            gb = float(text)
        except ValueError:
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                message, _("user.invalid_traffic"), user_create_traffic_keyboard(), ctx=ctx
            )
            return
        data["traffic_limit_bytes"] = int(gb * 1024 * 1024 * 1024)
        ctx["stage"] = "hwid"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(message, _("user.prompt_hwid"), user_create_hwid_keyboard(), ctx=ctx)
        return

    if stage == "hwid":
        try:
            hwid = int(text)
        except ValueError:
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                message, _("user.invalid_hwid"), user_create_hwid_keyboard(), ctx=ctx
            )
            return
        data["hwid_limit"] = hwid
        ctx["stage"] = "telegram"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _("user.prompt_telegram"), user_create_telegram_keyboard(), ctx=ctx
        )
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
        return

    if stage == "squad":
        data["squad_uuid"] = text or None
        ctx["stage"] = "confirm"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _build_user_create_preview(data), user_create_confirm_keyboard(), ctx=ctx
        )
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
    squads: list[dict] = []
    squad_source = "internal"
    try:
        res = await api_client.get_internal_squads()
        squads = res.get("response", {}).get("internalSquads", [])
        logger.info("📥 Loaded %s internal squads for user_id=%s", len(squads), target.from_user.id)
    except UnauthorizedError:
        await _send_user_create_prompt(target, _("errors.unauthorized"), users_menu_keyboard(), ctx=ctx)
        return
    except ApiClientError as exc:
        logger.warning("⚠️ Failed to load internal squads: %s", exc)
    except Exception:
        logger.exception("⚠️ Unexpected error while loading internal squads")

    if not squads:
        try:
            res = await api_client.get_external_squads()
            squads = res.get("response", {}).get("externalSquads", [])
            squad_source = "external"
            logger.info("📥 Loaded %s external squads for user_id=%s", len(squads), target.from_user.id)
        except UnauthorizedError:
            await _send_user_create_prompt(target, _("errors.unauthorized"), users_menu_keyboard(), ctx=ctx)
            return
        except ApiClientError as exc:
            logger.warning("⚠️ Failed to load external squads: %s", exc)
        except Exception:
            logger.exception("⚠️ Unexpected error while loading external squads")

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
    squad_type = "internal"  # По умолчанию внутренние сквады
    
    try:
        res = await api_client.get_internal_squads()
        squads = res.get("response", {}).get("internalSquads", [])
        logger.info("📥 Loaded %s internal squads for edit user_id=%s", len(squads), callback.from_user.id)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))
        return
    except ApiClientError as exc:
        logger.warning("⚠️ Failed to load internal squads: %s", exc)
    except Exception:
        logger.exception("⚠️ Unexpected error while loading internal squads")

    if not squads:
        try:
            res = await api_client.get_external_squads()
            squads = res.get("response", {}).get("externalSquads", [])
            squad_type = "external"
            logger.info("📥 Loaded %s external squads for edit user_id=%s", len(squads), callback.from_user.id)
        except UnauthorizedError:
            await callback.message.edit_text(_("errors.unauthorized"), reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))
            return
        except ApiClientError as exc:
            logger.warning("⚠️ Failed to load external squads: %s", exc)
        except Exception:
            logger.exception("⚠️ Unexpected error while loading external squads")

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
        user = await api_client.get_user_by_uuid(user_uuid)
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
    """Обработчик действий с пользователем (enable, disable, reset, revoke)."""
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, user_uuid, action = callback.data.split(":")
    back_to = _get_user_detail_back_target(callback.from_user.id)
    try:
        if action == "enable":
            await api_client.enable_user(user_uuid)
        elif action == "disable":
            await api_client.disable_user(user_uuid)
        elif action == "reset":
            await api_client.reset_user_traffic(user_uuid)
        elif action == "revoke":
            await api_client.revoke_user_subscription(user_uuid)
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
        user = await api_client.get_user_by_uuid(user_uuid)
        summary = build_user_summary(user, _)
        status = user.get("response", user).get("status", "UNKNOWN")
        await callback.message.edit_text(
            summary, reply_markup=user_actions_keyboard(user_uuid, status, back_to=back_to)
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
        user = await api_client.get_user_by_uuid(user_uuid)
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
    back_to = _get_user_detail_back_target(callback.from_user.id)
    try:
        user = await api_client.get_user_by_uuid(user_uuid)
        info = user.get("response", user)
        header = _format_user_edit_snapshot(info, _)
        await callback.message.edit_text(
            header,
            reply_markup=user_edit_keyboard(user_uuid, back_to=back_to),
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
        user = await api_client.get_user_by_uuid(user_uuid)
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


@router.callback_query(F.data.startswith("user_configs:"))
async def cb_user_configs(callback: CallbackQuery) -> None:
    """Обработчик просмотра конфигураций пользователя (подписные ссылки)."""
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, user_uuid = callback.data.split(":")
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе
        user = await api_client.get_user_by_uuid(user_uuid)
        user_info = user.get("response", user)
        short_uuid = user_info.get("shortUuid")
        subscription_url = user_info.get("subscriptionUrl")

        subscription_links = []
        happ_crypto_link = None

        # Получаем подписные ссылки из информации о подписке
        if short_uuid:
            try:
                sub_info = await api_client.get_subscription_info(short_uuid)
                sub_response = sub_info.get("response", {})
                subscription_links = sub_response.get("links", [])
            except Exception:
                logger.debug("Failed to fetch subscription links for user %s", short_uuid)

        # Получаем Happ crypto link, если есть subscriptionUrl
        if subscription_url:
            try:
                happ_response = await api_client.encrypt_happ_crypto_link(subscription_url)
                happ_crypto_link = happ_response.get("response", {}).get("encryptedLink")
            except Exception:
                logger.debug("Failed to encrypt Happ crypto link for user %s", short_uuid)

        # Формируем текст и клавиатуру
        text_lines = [_("user.configs_title")]

        if not subscription_links and not happ_crypto_link:
            text_lines.append("")
            text_lines.append(_("user.no_subscription_links"))

        keyboard_rows: list[list[InlineKeyboardButton]] = []

        # Добавляем кнопки для подписных ссылок
        if subscription_links:
            text_lines.append("")
            text_lines.append(_("user.subscription_links_title"))
            for i, link in enumerate(subscription_links[:10]):  # Ограничиваем до 10 ссылок
                # Определяем тип ссылки по префиксу для текста кнопки
                if link.startswith("vless://"):
                    button_text = f"🔷 VLESS {i+1}"
                elif link.startswith("ss://"):
                    button_text = f"🔶 SS {i+1}"
                elif link.startswith("trojan://"):
                    button_text = f"🔴 Trojan {i+1}"
                elif link.startswith("vmess://"):
                    button_text = f"🟣 VMess {i+1}"
                else:
                    button_text = f"🔗 Link {i+1}"

                # Используем callback кнопку, так как Telegram не поддерживает нестандартные протоколы в URL
                keyboard_rows.append(
                    [
                        InlineKeyboardButton(
                            text=button_text,
                            callback_data=f"user_sub_link:{user_uuid}:{i}",
                        )
                    ]
                )

        # Добавляем кнопку для Happ crypto link
        if happ_crypto_link:
            text_lines.append("")
            text_lines.append(_("user.happ_crypto_link_title"))
            # Для Happ crypto link используем callback, так как это не URL
            keyboard_rows.append(
                [
                    InlineKeyboardButton(
                        text=_("user.happ_crypto_link_button"),
                        callback_data=f"user_happ_link:{user_uuid}",
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


@router.callback_query(F.data.startswith("user_sub_link:"))
async def cb_user_sub_link(callback: CallbackQuery) -> None:
    """Обработчик для отображения подписной ссылки."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    user_uuid = parts[1]
    try:
        link_index = int(parts[2])
    except ValueError:
        await callback.message.edit_text(
            _("errors.generic"), reply_markup=nav_keyboard(_get_user_detail_back_target(callback.from_user.id))
        )
        return
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе
        user = await api_client.get_user_by_uuid(user_uuid)
        user_info = user.get("response", user)
        short_uuid = user_info.get("shortUuid")

        if not short_uuid:
            await callback.message.edit_text(_("user.no_subscription_url"), reply_markup=nav_keyboard(back_to))
            return

        # Получаем подписные ссылки
        sub_info = await api_client.get_subscription_info(short_uuid)
        sub_response = sub_info.get("response", {})
        subscription_links = sub_response.get("links", [])

        if link_index >= len(subscription_links):
            await callback.message.edit_text(_("user.link_not_found"), reply_markup=nav_keyboard(back_to))
            return

        link = subscription_links[link_index]

        # Определяем тип ссылки для заголовка
        if link.startswith("vless://"):
            link_type = "🔷 VLESS"
        elif link.startswith("ss://"):
            link_type = "🔶 SS"
        elif link.startswith("trojan://"):
            link_type = "🔴 Trojan"
        elif link.startswith("vmess://"):
            link_type = "🟣 VMess"
        else:
            link_type = "🔗 Link"

        # Отображаем ссылку
        text = f"{link_type}\n\n<code>{_esc(link)}</code>"
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text=_("user.back_to_configs"), callback_data=f"user_configs:{user_uuid}")],
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


@router.callback_query(F.data.startswith("user_happ_link:"))
async def cb_user_happ_link(callback: CallbackQuery) -> None:
    """Обработчик для отображения Happ crypto link."""
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, user_uuid = callback.data.split(":")
    back_to = _get_user_detail_back_target(callback.from_user.id)

    try:
        # Получаем информацию о пользователе
        user = await api_client.get_user_by_uuid(user_uuid)
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
                [InlineKeyboardButton(text=_("user.back_to_configs"), callback_data=f"user_configs:{user_uuid}")],
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
        user = await api_client.get_user_by_uuid(user_uuid)
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
                    nav_row(back_to),
                ]
            )
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

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
                            callback_data=f"user_stats:traffic_period:{user_uuid}:today",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_week"),
                            callback_data=f"user_stats:traffic_period:{user_uuid}:week",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text=_("user.stats.period_month"),
                            callback_data=f"user_stats:traffic_period:{user_uuid}:month",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_custom"),
                            callback_data=f"user_stats:traffic_period:{user_uuid}:custom",
                        ),
                    ],
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:{user_uuid}")],
                    nav_row(back_to),
                ]
            )
            await callback.message.edit_text(_("user.stats.select_period"), reply_markup=keyboard)

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
                            callback_data=f"user_stats:nodes_period:{user_uuid}:today",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_week"),
                            callback_data=f"user_stats:nodes_period:{user_uuid}:week",
                        ),
                    ],
                    [
                        InlineKeyboardButton(
                            text=_("user.stats.period_month"),
                            callback_data=f"user_stats:nodes_period:{user_uuid}:month",
                        ),
                        InlineKeyboardButton(
                            text=_("user.stats.period_custom"),
                            callback_data=f"user_stats:nodes_period:{user_uuid}:custom",
                        ),
                    ],
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:nodes:{user_uuid}")],
                    nav_row(back_to),
                ]
            )
            await callback.message.edit_text(_("user.stats.select_period"), reply_markup=keyboard)

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
                    nav_row(back_to),
                ]
            )
            await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

        else:
            # Показываем меню статистики
            user = await api_client.get_user_by_uuid(user_uuid)
            user_info = user.get("response", user)
            username = user_info.get("username", "n/a")
            text = _("user.stats_title").format(username=_esc(username))
            await callback.message.edit_text(text, reply_markup=user_stats_keyboard(user_uuid, back_to=back_to))

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
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        if period == "today":
            start = today_start.isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "week":
            start = (today_start - timedelta(days=7)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "month":
            start = (today_start - timedelta(days=30)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "3months":
            start = (today_start - timedelta(days=90)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "year":
            start = (today_start - timedelta(days=365)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        else:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
            return
        
        # Получаем статистику трафика
        traffic_data = await api_client.get_user_traffic_stats(user_uuid, start, end)
        response = traffic_data.get("response", {})
        total_traffic = response.get("totalTrafficBytes", 0)
        nodes_usage = response.get("nodesUsage", [])
        
        lines = [
            _("user.stats.traffic_title"),
            "",
            _("user.stats.traffic_period").format(
                start=format_datetime(start.replace("Z", "+00:00")),
                end=format_datetime(end.replace("Z", "+00:00")),
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
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
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


@router.callback_query(F.data.startswith("user_stats:traffic_period:"))
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
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == "today":
            start = today_start.isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "week":
            start = (today_start - timedelta(days=7)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "month":
            start = (today_start - timedelta(days=30)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "3months":
            start = (today_start - timedelta(days=90)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "year":
            start = (today_start - timedelta(days=365)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "custom":
            # Для произвольного периода нужно будет добавить ввод дат
            await callback.message.edit_text(
                _("user.stats.custom_period_not_implemented"),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:traffic:{user_uuid}")],
                        nav_row(back_to),
                    ]
                ),
            )
            return
        else:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
            return

        # Получаем статистику трафика
        traffic_data = await api_client.get_user_traffic_stats(user_uuid, start, end)
        response = traffic_data.get("response", {})
        total_traffic = response.get("totalTrafficBytes", 0)
        nodes_usage = response.get("nodesUsage", [])

        lines = [
            _("user.stats.traffic_title"),
            "",
            _("user.stats.traffic_period").format(
                start=format_datetime(start.replace("Z", "+00:00")),
                end=format_datetime(end.replace("Z", "+00:00")),
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
                [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:traffic:{user_uuid}")],
                nav_row(back_to),
            ]
        )
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user traffic stats user_uuid=%s period=%s actor_id=%s", user_uuid, period, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("user_stats:nodes_period:"))
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
        user = await api_client.get_user_by_uuid(user_uuid)
        user_info = user.get("response", user)

        # Получаем доступные ноды пользователя
        nodes_data = await api_client.get_user_accessible_nodes(user_uuid)
        nodes = nodes_data.get("response", {}).get("nodes", [])

        if not nodes:
            text = _("user.stats.nodes_usage_title") + "\n\n" + _("user.stats.nodes_usage_empty")
            keyboard = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:nodes:{user_uuid}")],
                    nav_row(back_to),
                ]
            )
            await callback.message.edit_text(text, reply_markup=keyboard)
            return

        # Вычисляем период
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == "today":
            start = today_start.isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "week":
            start = (today_start - timedelta(days=7)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "month":
            start = (today_start - timedelta(days=30)).isoformat() + "Z"
            end = now.isoformat() + "Z"
        elif period == "custom":
            # Для произвольного периода нужно будет добавить ввод дат
            await callback.message.edit_text(
                _("user.stats.custom_period_not_implemented"),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [InlineKeyboardButton(text=_("user.back_to_stats"), callback_data=f"user_stats:nodes:{user_uuid}")],
                        nav_row(back_to),
                    ]
                ),
            )
            return
        else:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
            return

        # Получаем статистику использования нод
        node_uuids = [n.get("uuid") for n in nodes if n.get("uuid")]
        lines = [
            _("user.stats.nodes_usage_title"),
            "",
            _("user.stats.nodes_usage_period").format(
                start=format_datetime(start.replace("Z", "+00:00")),
                end=format_datetime(end.replace("Z", "+00:00")),
            ),
        ]

        if not node_uuids:
            lines.append(_("user.stats.nodes_usage_empty"))
        else:
            # Получаем статистику для каждой ноды
            for node_uuid in node_uuids[:10]:  # Ограничиваем до 10 нод
                try:
                    node_usage_data = await api_client.get_stats_node_users_usage(node_uuid, start, end, top_users_limit=1)
                    node_usage_response = node_usage_data.get("response", {})
                    top_users = node_usage_response.get("topUsers", [])

                    # Находим текущего пользователя в топе
                    user_traffic = 0
                    for top_user in top_users:
                        if top_user.get("userUuid") == user_uuid:
                            user_traffic = top_user.get("trafficBytes", 0)
                            break

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
                nav_row(back_to),
            ]
        )
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")

    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get user nodes usage user_uuid=%s period=%s actor_id=%s", user_uuid, period, callback.from_user.id)
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
        user = await api_client.get_user_by_uuid(user_uuid)
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
            for idx, device in enumerate(devices[:10], 1):  # Показываем до 10 устройств
                hwid = device.get("hwid", "n/a")
                created_at = device.get("createdAt")
                created_str = format_datetime(created_at) if created_at else "—"
                lines.append(
                    _("hwid.device_item").format(
                        index=idx,
                        hwid=_esc(hwid[:40] + "..." if len(hwid) > 40 else hwid),
                        created=_esc(created_str)
                    )
                )
        
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
        user = await api_client.get_user_by_uuid(user_uuid)
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
            for idx, device in enumerate(devices[:10], 1):
                device_hwid = device.get("hwid", "n/a")
                created_at = device.get("createdAt")
                created_str = format_datetime(created_at) if created_at else "—"
                lines.append(
                    _("hwid.device_item").format(
                        index=idx,
                        hwid=_esc(device_hwid[:40] + "..." if len(device_hwid) > 40 else device_hwid),
                        created=_esc(created_str)
                    )
                )
        
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
        user = await api_client.get_user_by_uuid(user_uuid)
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
            for idx, device in enumerate(devices[:10], 1):
                device_hwid = device.get("hwid", "n/a")
                created_at = device.get("createdAt")
                created_str = format_datetime(created_at) if created_at else "—"
                lines.append(
                    _("hwid.device_item").format(
                        index=idx,
                        hwid=_esc(device_hwid[:40] + "..." if len(device_hwid) > 40 else device_hwid),
                        created=_esc(created_str)
                    )
                )
        
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


