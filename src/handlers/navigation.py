"""Обработчики навигации и общих callback'ов."""
from math import ceil

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _clear_user_state, _get_target_user_id, _not_admin, _send_clean_message
from src.handlers.state import (
    PENDING_INPUT,
    SUBS_PAGE_BY_USER,
    SUBS_PAGE_SIZE,
    USER_DETAIL_BACK_TARGET,
    USER_SEARCH_CONTEXT,
)
from src.keyboards.billing_menu import billing_menu_keyboard
from src.keyboards.billing_nodes_menu import billing_nodes_menu_keyboard
from src.keyboards.hosts_menu import hosts_menu_keyboard
from src.keyboards.main_menu import (
    billing_overview_keyboard,
    bulk_menu_keyboard,
    main_menu_keyboard,
    nodes_menu_keyboard,
    resources_menu_keyboard,
    system_menu_keyboard,
    users_menu_keyboard,
)
from src.keyboards.navigation import NavTarget, nav_keyboard, nav_row
from src.keyboards.providers_menu import providers_menu_keyboard
from src.services.api_client import ApiClientError, NotFoundError, UnauthorizedError, api_client
from src.utils.logger import logger

# Импорты из соответствующих модулей
from src.handlers.billing import _fetch_billing_nodes_text, _fetch_billing_text, _fetch_providers_text
from src.handlers.hosts import _fetch_hosts_text
from src.handlers.nodes import _fetch_nodes_text
from src.handlers.resources import _fetch_configs_text, _fetch_snippets_text, _send_templates, _show_tokens
from src.handlers.users import _format_user_choice, _send_user_summary, _show_user_search_results, _start_user_search_flow
from src.keyboards.subscription_actions import subscription_keyboard
from src.utils.formatters import build_subscription_summary

async def _fetch_main_menu_text() -> str:
    """Получает текст для главного меню с краткой статистикой."""
    from aiogram import Bot
    from aiogram.fsm.context import FSMContext
    
    panel_status = "🟢"
    panel_status_text = ""
    
    # Проверяем статус панели через health checker, если доступен
    try:
        # Пытаемся получить health checker из контекста диспетчера
        # Это работает только если бот уже запущен
        from src.services.api_client import ApiClientError
        try:
            await api_client.get_health()
            panel_status = "🟢"
        except ApiClientError:
            panel_status = "🔴"
            panel_status_text = f"\n{_('panel.unavailable_warning')}"
    except Exception:
        # Если не можем проверить, показываем нейтральный статус
        panel_status = "🟡"
    
    try:
        # Получаем основную статистику системы
        data = await api_client.get_stats()
        res = data.get("response", {})
        users = res.get("users", {})
        online = res.get("onlineStats", {})
        nodes = res.get("nodes", {})

        total_users = users.get("totalUsers", 0)
        online_now = online.get("onlineNow", 0)

        # Получаем количество хостов
        try:
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            total_hosts = len(hosts)
            enabled_hosts = sum(1 for h in hosts if not h.get("isDisabled"))
        except Exception:
            total_hosts = "—"
            enabled_hosts = "—"

        # Получаем количество нод
        try:
            nodes_data = await api_client.get_nodes()
            nodes_list = nodes_data.get("response", [])
            total_nodes = len(nodes_list)
            enabled_nodes = sum(1 for n in nodes_list if not n.get("isDisabled"))
            # Правильно считаем онлайн ноды из списка нод, а не из статистики API
            nodes_online = sum(1 for n in nodes_list if n.get("isConnected"))
        except Exception:
            total_nodes = "—"
            enabled_nodes = "—"
            nodes_online = "—"

        lines = [
            _("bot.menu"),
            "",
            f"{panel_status} {_('panel.status')}{panel_status_text}",
            "",
            _("bot.menu_stats").format(
                users=total_users,
                online=online_now,
                nodes=total_nodes,
                nodes_enabled=enabled_nodes,
                nodes_online=nodes_online,
                hosts=total_hosts,
                hosts_enabled=enabled_hosts,
            ),
        ]

        return "\n".join(lines)
    except Exception:
        # Если не удалось получить статистику, возвращаем простое меню
        logger.exception("Failed to fetch main menu stats")
        return _("bot.menu")

router = Router(name="navigation")


def _get_subs_page(user_id: int | None) -> int:
    """Получает текущую страницу подписок для пользователя."""
    if user_id is None:
        return 0
    return max(SUBS_PAGE_BY_USER.get(user_id, 0), 0)


async def _send_subscriptions_page(target: Message | CallbackQuery, page: int = 0) -> None:
    """Отправляет страницу со списком подписок."""
    user_id = _get_target_user_id(target)
    page = max(page, 0)
    start = page * SUBS_PAGE_SIZE
    try:
        data = await api_client.get_users(start=start, size=SUBS_PAGE_SIZE)
        payload = data.get("response", data)
        total = payload.get("total", 0) or 0
        total_pages = max(ceil(total / SUBS_PAGE_SIZE), 1)
        page = min(page, total_pages - 1)
        if page != start // SUBS_PAGE_SIZE:
            start = page * SUBS_PAGE_SIZE
            data = await api_client.get_users(start=start, size=SUBS_PAGE_SIZE)
            payload = data.get("response", data)
        users = payload.get("users") or []
    except UnauthorizedError:
        await _send_clean_message(target, _("errors.unauthorized"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return
    except ApiClientError:
        logger.exception("Subscriptions list fetch failed page=%s actor_id=%s", page, user_id)
        await _send_clean_message(target, _("errors.generic"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return

    if user_id is not None:
        SUBS_PAGE_BY_USER[user_id] = page

    if not users:
        await _send_clean_message(target, _("sub.list_empty"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return

    total = payload.get("total", len(users)) or len(users)
    total_pages = max(ceil(total / SUBS_PAGE_SIZE), 1)
    rows: list[list[InlineKeyboardButton]] = []
    for user in users:
        info = user.get("response", user)
        uuid = info.get("uuid")
        if not uuid:
            continue
        rows.append([InlineKeyboardButton(text=_format_user_choice(info), callback_data=f"subs:view:{uuid}")])

    if total_pages > 1:
        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(text=_("sub.prev_page"), callback_data=f"subs:page:{page-1}"))
        if page + 1 < total_pages:
            nav_buttons.append(InlineKeyboardButton(text=_("sub.next_page"), callback_data=f"subs:page:{page+1}"))
        if nav_buttons:
            rows.append(nav_buttons)

    # Добавляем кнопку поиска
    rows.append([InlineKeyboardButton(text=_("sub.search"), callback_data="subs:search")])
    rows.append(nav_row(NavTarget.USERS_MENU))
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    title = _("sub.list_title").format(page=page + 1, pages=total_pages, total=total)
    await _send_clean_message(target, title, reply_markup=keyboard)


async def _navigate(target: Message | CallbackQuery, destination: str) -> None:
    """Навигация между меню."""
    user_id = _get_target_user_id(target)
    keep_search = destination in {NavTarget.USER_SEARCH_PROMPT, NavTarget.USER_SEARCH_RESULTS}
    keep_subs = destination == NavTarget.SUBS_LIST
    _clear_user_state(user_id, keep_search=keep_search, keep_subs=keep_subs)

    if destination == NavTarget.MAIN_MENU:
        menu_text = await _fetch_main_menu_text()
        await _send_clean_message(target, menu_text, reply_markup=main_menu_keyboard(), parse_mode="HTML")
        return
    if destination == NavTarget.USERS_MENU:
        await _send_clean_message(target, _("bot.menu"), reply_markup=users_menu_keyboard())
        return
    if destination == NavTarget.USER_SEARCH_PROMPT:
        await _start_user_search_flow(target)
        return
    if destination == NavTarget.USER_SEARCH_RESULTS:
        ctx = USER_SEARCH_CONTEXT.get(user_id, {})
        query = ctx.get("query", "")
        results = ctx.get("results", [])
        if results:
            await _show_user_search_results(target, query, results)
        else:
            await _start_user_search_flow(target)
        return
    if destination == NavTarget.NODES_MENU:
        await _send_clean_message(target, _("bot.menu"), reply_markup=nodes_menu_keyboard())
        return
    if destination == NavTarget.NODES_LIST:
        text = await _fetch_nodes_text()
        from src.keyboards.nodes_menu import nodes_list_keyboard

        await _send_clean_message(target, text, reply_markup=nodes_list_keyboard())
        return
    if destination == NavTarget.HOSTS_MENU:
        text = await _fetch_hosts_text()
        await _send_clean_message(target, text, reply_markup=hosts_menu_keyboard())
        return
    if destination == NavTarget.CONFIGS_MENU:
        text = await _fetch_configs_text()
        await _send_clean_message(target, text, reply_markup=nodes_menu_keyboard())
        return
    if destination == NavTarget.RESOURCES_MENU:
        await _send_clean_message(target, _("bot.menu"), reply_markup=resources_menu_keyboard())
        return
    if destination == NavTarget.TOKENS_MENU:
        await _show_tokens(target, reply_markup=resources_menu_keyboard())
        return
    if destination == NavTarget.TEMPLATES_MENU:
        await _send_templates(target)
        return
    if destination == NavTarget.SNIPPETS_MENU:
        text = await _fetch_snippets_text()
        await _send_clean_message(target, text, reply_markup=resources_menu_keyboard())
        return
    if destination == NavTarget.BILLING_OVERVIEW:
        await _send_clean_message(target, _("bot.menu"), reply_markup=billing_overview_keyboard())
        return
    if destination == NavTarget.BILLING_MENU:
        text = await _fetch_billing_text()
        await _send_clean_message(target, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        return
    if destination == NavTarget.BILLING_NODES_MENU:
        text = await _fetch_billing_nodes_text()
        await _send_clean_message(target, text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        return
    if destination == NavTarget.PROVIDERS_MENU:
        text = await _fetch_providers_text()
        await _send_clean_message(target, text, reply_markup=providers_menu_keyboard())
        return
    if destination == NavTarget.BULK_MENU:
        await _send_clean_message(target, _("bot.menu"), reply_markup=bulk_menu_keyboard())
        return
    if destination == NavTarget.SYSTEM_MENU:
        await _send_clean_message(target, _("bot.menu"), reply_markup=system_menu_keyboard())
        return
    if destination == NavTarget.STATS_MENU:
        from src.keyboards.stats_menu import stats_menu_keyboard
        text = _("stats.menu_title")
        await _send_clean_message(target, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")
        return
    if destination == NavTarget.SUBS_LIST:
        await _send_subscriptions_page(target, page=_get_subs_page(user_id))
        return
    
    # Обработка специальных случаев навигации (например, user:{uuid})
    if destination.startswith("user:"):
        # Возврат в профиль пользователя
        user_uuid = destination.split(":", 1)[1]
        from src.handlers.users import _send_user_summary
        from src.handlers.state import USER_DETAIL_BACK_TARGET
        
        back_to = USER_DETAIL_BACK_TARGET.get(user_id, NavTarget.USERS_MENU)
        try:
            user = await api_client.get_user_by_uuid(user_uuid)
            await _send_user_summary(target, user, back_to=back_to)
        except Exception:
            logger.exception("Failed to navigate to user profile user_uuid=%s", user_uuid)
            await _send_clean_message(target, _("errors.generic"), reply_markup=main_menu_keyboard())
        return

    await _send_clean_message(target, _("bot.menu"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data == "nav:home")
async def cb_nav_home(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Главное меню'."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.MAIN_MENU)


@router.callback_query(F.data.startswith("nav:back:"))
async def cb_nav_back(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Назад'."""
    if await _not_admin(callback):
        return
    await callback.answer()
    target = callback.data.split(":", 2)[2]
    await _navigate(callback, target)


@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Назад' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.MAIN_MENU)


@router.callback_query(F.data == "menu:section:users")
async def cb_section_users(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Пользователи' в главном меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.USERS_MENU)


@router.callback_query(F.data == "menu:section:nodes")
async def cb_section_nodes(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Ноды/Хосты/Профили' в главном меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.NODES_MENU)


@router.callback_query(F.data == "menu:section:resources")
async def cb_section_resources(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Ресурсы' в главном меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.RESOURCES_MENU)


@router.callback_query(F.data == "menu:section:billing")
async def cb_section_billing(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Биллинг' в главном меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.BILLING_OVERVIEW)


@router.callback_query(F.data == "menu:section:bulk")
async def cb_section_bulk(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Массовые операции' в главном меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.BULK_MENU)


@router.callback_query(F.data == "menu:section:system")
async def cb_section_system(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Система' в главном меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.SYSTEM_MENU)


@router.callback_query(F.data == "menu:subs")
async def cb_subs(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Подписки' в меню пользователей."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.SUBS_LIST)


@router.callback_query(F.data == "subs:search")
async def cb_subs_search(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Поиск' в списке подписок."""
    if await _not_admin(callback):
        return
    await callback.answer()
    
    from src.handlers.state import PENDING_INPUT
    from src.handlers.common import _get_target_user_id
    
    user_id = _get_target_user_id(callback)
    if user_id is not None:
        # Устанавливаем PENDING_INPUT для поиска подписок
        PENDING_INPUT[user_id] = {"action": "subs_search"}
        logger.info("cb_subs_search: set PENDING_INPUT for user_id=%s", user_id)
    
    await _send_clean_message(
        callback,
        _("sub.search_prompt"),
        reply_markup=nav_keyboard(NavTarget.SUBS_LIST)
    )


async def _handle_subs_search_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод поискового запроса для подписок."""
    from src.handlers.users import _search_users, _send_user_summary, _format_user_choice
    from src.handlers.state import MAX_SEARCH_RESULTS, PENDING_INPUT
    from src.handlers.common import _cleanup_message
    from src.utils.formatters import _esc
    import asyncio
    
    query = (message.text or "").strip()
    user_id = message.from_user.id
    
    # Удаляем из PENDING_INPUT только после начала обработки
    if user_id in PENDING_INPUT:
        PENDING_INPUT.pop(user_id)
    
    if not query:
        await _send_clean_message(message, _("sub.search_prompt"), reply_markup=nav_keyboard(NavTarget.SUBS_LIST))
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return
    
    # Выполняем поиск пользователей (подписки - это те же пользователи)
    try:
        matches = await _search_users(query)
    except UnauthorizedError:
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=nav_keyboard(NavTarget.SUBS_LIST))
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return
    except ApiClientError:
        logger.exception("Subs search failed query=%s actor_id=%s", query, user_id)
        await _send_clean_message(message, _("errors.generic"), reply_markup=nav_keyboard(NavTarget.SUBS_LIST))
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return
    
    if not matches:
        await _send_clean_message(
            message,
            _("sub.search_no_results").format(query=_esc(query)),
            reply_markup=nav_keyboard(NavTarget.SUBS_LIST),
        )
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return
    
    if len(matches) == 1:
        # Если найден один пользователь, показываем его подписку
        await _send_user_summary(message, matches[0], back_to=NavTarget.SUBS_LIST)
        asyncio.create_task(_cleanup_message(message, delay=0.5))
        return
    
    # Показываем результаты поиска
    rows = []
    for user in matches[:MAX_SEARCH_RESULTS]:
        info = user.get("response", user)
        uuid = info.get("uuid")
        if not uuid:
            continue
        rows.append([InlineKeyboardButton(text=_format_user_choice(info), callback_data=f"subs:view:{uuid}")])
    
    rows.append(nav_row(NavTarget.SUBS_LIST))
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    
    extra_line = ""
    if len(matches) > MAX_SEARCH_RESULTS:
        extra_line = _("sub.search_results_limited").format(shown=MAX_SEARCH_RESULTS, total=len(matches))
    
    text = _("sub.search_results").format(count=len(matches), query=_esc(query))
    if extra_line:
        text = f"{text}\n{extra_line}"
    
    await _send_clean_message(message, text, reply_markup=keyboard)
    asyncio.create_task(_cleanup_message(message, delay=0.5))


@router.callback_query(F.data.startswith("subs:page:"))
async def cb_subs_page(callback: CallbackQuery) -> None:
    """Обработчик пагинации списка подписок."""
    if await _not_admin(callback):
        return
    await callback.answer()
    try:
        page = int(callback.data.split(":", 2)[2])
    except ValueError:
        page = 0
    await _send_subscriptions_page(callback, page=max(page, 0))


@router.callback_query(F.data.startswith("subs:view:"))
async def cb_subs_view(callback: CallbackQuery) -> None:
    """Обработчик просмотра пользователя из списка подписок."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    user_uuid = parts[2]
    back_to = NavTarget.SUBS_LIST
    try:
        user = await api_client.get_user_by_uuid(user_uuid)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
        return
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=nav_keyboard(back_to))
        return
    except ApiClientError:
        logger.exception("User view from subs failed user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
        return

    await _send_user_summary(callback, user, back_to=back_to)


async def _send_subscription_detail(target: Message | CallbackQuery, short_uuid: str) -> None:
    """Отправляет детальную информацию о подписке."""
    try:
        sub = await api_client.get_subscription_info(short_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        text = _("sub.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("⚠️ API client error while fetching subscription short_uuid=%s", short_uuid)
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    summary = build_subscription_summary(sub, _)
    sub_url = sub.get("response", sub).get("subscriptionUrl")
    keyboard = subscription_keyboard(sub_url)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await _send_clean_message(target, summary, reply_markup=keyboard)

