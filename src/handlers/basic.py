import asyncio
import re
from typing import Callable

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _
from aiogram.exceptions import TelegramBadRequest
from datetime import datetime, timedelta
from math import ceil

from src.keyboards.main_menu import (
    main_menu_keyboard,
    system_menu_keyboard,
    users_menu_keyboard,
    nodes_menu_keyboard,
    resources_menu_keyboard,
    billing_overview_keyboard,
    bulk_menu_keyboard,
)
from src.keyboards.navigation import NavTarget, nav_keyboard, nav_row, input_keyboard
from src.keyboards.user_create import (
    user_create_description_keyboard,
    user_create_expire_keyboard,
    user_create_traffic_keyboard,
    user_create_hwid_keyboard,
    user_create_telegram_keyboard,
    user_create_squad_keyboard,
    user_create_confirm_keyboard,
)
from src.keyboards.host_actions import host_actions_keyboard
from src.keyboards.node_actions import node_actions_keyboard
from src.keyboards.token_actions import token_actions_keyboard
from src.keyboards.template_actions import template_actions_keyboard
from src.keyboards.snippet_actions import snippet_actions_keyboard
from src.keyboards.config_actions import config_actions_keyboard
from src.keyboards.bulk_users import bulk_users_keyboard
from src.keyboards.template_menu import template_menu_keyboard, template_list_keyboard
from src.keyboards.bulk_hosts import bulk_hosts_keyboard
from src.keyboards.system_nodes import system_nodes_keyboard
from src.keyboards.stats_menu import stats_menu_keyboard
from src.keyboards.subscription_actions import subscription_keyboard
from src.keyboards.user_actions import user_actions_keyboard, user_edit_keyboard, user_edit_strategy_keyboard, user_edit_squad_keyboard
from src.keyboards.billing_menu import billing_menu_keyboard
from src.keyboards.billing_nodes_menu import billing_nodes_menu_keyboard
from src.keyboards.providers_menu import providers_menu_keyboard
from src.services.api_client import (
    ApiClientError,
    NotFoundError,
    UnauthorizedError,
    api_client,
)
from src.utils.auth import is_admin
from src.utils.formatters import (
    format_bytes,
    build_host_summary,
    build_node_summary,
    build_user_summary,
    build_created_user,
    format_datetime,
    format_bytes,
    format_uptime,
    build_subscription_summary,
    build_tokens_list,
    build_created_token,
    escape_markdown,
    build_token_line,
    build_templates_list,
    build_template_summary,
    build_snippets_list,
    build_snippet_detail,
    build_nodes_realtime_usage,
    build_nodes_usage_range,
    build_config_profiles_list,
    build_config_profile_detail,
    build_billing_history,
    build_infra_providers,
    build_billing_nodes,
    build_bandwidth_stats,
)
from src.utils.logger import logger

router = Router(name="basic")
PENDING_INPUT: dict[int, dict] = {}
LAST_BOT_MESSAGES: dict[int, int] = {}
USER_SEARCH_CONTEXT: dict[int, dict] = {}
USER_DETAIL_BACK_TARGET: dict[int, str] = {}
SUBS_PAGE_BY_USER: dict[int, int] = {}
ADMIN_COMMAND_DELETE_DELAY = 2.0
SEARCH_PAGE_SIZE = 100
MAX_SEARCH_RESULTS = 10
SUBS_PAGE_SIZE = 8


async def _cleanup_message(message: Message, delay: float = 0.0) -> None:
    if not isinstance(message, Message):
        return
    try:
        if delay > 0:
            await asyncio.sleep(delay)
        await message.delete()
    except Exception as exc:
        logger.warning(
            "🧹 Failed to delete message chat_id=%s message_id=%s err=%s",
            message.chat.id,
            getattr(message, "message_id", None),
            exc,
        )


async def _not_admin(message: Message | CallbackQuery) -> bool:
    user_id = message.from_user.id if hasattr(message, "from_user") else None
    if user_id is None or not is_admin(user_id):
        text = _("errors.unauthorized")
        if isinstance(message, CallbackQuery):
            await message.answer(text, show_alert=True)
        else:
            await _send_clean_message(message, text)
        return True
    if isinstance(message, Message):
        is_command = bool(getattr(message, "text", "") and message.text.startswith("/"))
        delay = ADMIN_COMMAND_DELETE_DELAY if is_command else 0.0
        asyncio.create_task(_cleanup_message(message, delay=delay))
    return False


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if await _not_admin(message):
        return

    await _send_clean_message(message, _("bot.welcome"))
    await _send_clean_message(message, _("bot.menu"), reply_markup=main_menu_keyboard())


@router.message(F.text & ~F.text.startswith("/"))
async def handle_pending(message: Message) -> None:
    if await _not_admin(message):
        return
    user_id = message.from_user.id
    if user_id not in PENDING_INPUT:
        return
    ctx = PENDING_INPUT.pop(user_id)
    action = ctx.get("action")
    if action == "user_search":
        await _handle_user_search_input(message, ctx)
    elif action == "template_create":
        await _handle_template_create_input(message, ctx)
    elif action == "template_update_json":
        await _handle_template_update_json_input(message, ctx)
    elif action == "template_reorder":
        await _handle_template_reorder_input(message, ctx)
    elif action.startswith("provider_"):
        await _handle_provider_input(message, ctx)
    elif action.startswith("billing_history_"):
        await _handle_billing_history_input(message, ctx)
    elif action.startswith("billing_nodes_"):
        await _handle_billing_nodes_input(message, ctx)
    elif action == "user_create":
        await _handle_user_create_input(message, ctx)
    elif action == "user_edit":
        await _handle_user_edit_input(message, ctx)
    elif action.startswith("bulk_users_"):
        await _handle_bulk_users_input(message, ctx)
    elif action == "node_create":
        await _handle_node_create_input(message, ctx)
    else:
        await _send_clean_message(message, _("errors.generic"))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if await _not_admin(message):
        return

    await _send_clean_message(message, _("bot.help"))


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    if await _not_admin(message):
        return
    await _send_clean_message(message, await _fetch_health_text(), reply_markup=system_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if await _not_admin(message):
        return
    text = _("stats.menu_title")
    await _send_clean_message(message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("bandwidth"))
async def cmd_bandwidth(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_bandwidth_text()
    await _send_clean_message(message, text, reply_markup=system_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("billing"))
async def cmd_billing(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_billing_text()
    await _send_clean_message(message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("providers"))
async def cmd_providers(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_providers_text()
    await _send_clean_message(message, text, reply_markup=providers_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("billing_nodes"))
async def cmd_billing_nodes(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_billing_nodes_text()
    await _send_clean_message(message, text, reply_markup=billing_nodes_menu_keyboard())


@router.message(Command("bulk"))
async def cmd_bulk(message: Message) -> None:
    if await _not_admin(message):
        return
    await _send_clean_message(message, _("bulk.title"), reply_markup=bulk_menu_keyboard())


@router.message(Command("bulk_delete_status"))
async def cmd_bulk_delete_status(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("bulk.usage_delete_status"))
        return
    status = parts[1].strip()
    await _run_bulk_action(message, action="delete_status", status=status)


@router.message(Command("bulk_delete"))
async def cmd_bulk_delete(message: Message) -> None:
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await _send_clean_message(message, _("bulk.usage_delete"))
        return
    await _run_bulk_action(message, action="delete", uuids=uuids)


@router.message(Command("bulk_revoke"))
async def cmd_bulk_revoke(message: Message) -> None:
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await _send_clean_message(message, _("bulk.usage_revoke"))
        return
    await _run_bulk_action(message, action="revoke", uuids=uuids)


@router.message(Command("bulk_reset"))
async def cmd_bulk_reset(message: Message) -> None:
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await _send_clean_message(message, _("bulk.usage_reset"))
        return
    await _run_bulk_action(message, action="reset", uuids=uuids)


@router.message(Command("bulk_extend"))
async def cmd_bulk_extend(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await _send_clean_message(message, _("bulk.usage_extend"))
        return
    try:
        days = int(parts[1])
    except ValueError:
        await _send_clean_message(message, _("bulk.usage_extend"))
        return
    uuids = parts[2:]
    if not uuids:
        await _send_clean_message(message, _("bulk.usage_extend"))
        return
    await _run_bulk_action(message, action="extend", uuids=uuids, days=days)


@router.message(Command("bulk_extend_all"))
async def cmd_bulk_extend_all(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await _send_clean_message(message, _("bulk.usage_extend_all"))
        return
    try:
        days = int(parts[1])
    except ValueError:
        await _send_clean_message(message, _("bulk.usage_extend_all"))
        return
    await _run_bulk_action(message, action="extend_all", days=days)


@router.message(Command("bulk_status"))
async def cmd_bulk_status(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await _send_clean_message(message, _("bulk.usage_status"))
        return
    status = parts[1]
    uuids = parts[2:]
    await _run_bulk_action(message, action="status", status=status, uuids=uuids)


@router.message(Command("user"))
async def cmd_user(message: Message) -> None:
    if await _not_admin(message):
        return

    parts = message.text.split(maxsplit=1)
    preset_query = parts[1].strip() if len(parts) > 1 else ""
    await _start_user_search_flow(message, preset_query or None)


@router.message(Command("user_create"))
async def cmd_user_create(message: Message) -> None:
    if await _not_admin(message):
        return

    parts = message.text.split()
    if len(parts) >= 3:
        data = {
            "username": parts[1],
            "expire_at": parts[2],
            "telegram_id": parts[3] if len(parts) > 3 else None,
        }
        await _create_user(message, data)
        return

    user_id = message.from_user.id
    ctx = {"action": "user_create", "stage": "username", "data": {}}
    PENDING_INPUT[user_id] = ctx
    await _send_user_create_prompt(message, _("user.prompt_username"), ctx=ctx)


@router.message(Command("nodes"))
async def cmd_nodes(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_nodes_text()
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("nodes_usage"))
async def cmd_nodes_usage(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_nodes_realtime_text()
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("nodes_range"))
async def cmd_nodes_range(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await _send_clean_message(message, _("node_stats.usage_range_usage"))
        return
    start, end = parts[1], parts[2]
    text = await _fetch_nodes_range_text(start, end)
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("node"))
async def cmd_node(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("node.usage"))
        return
    node_uuid = parts[1].strip()
    await _send_node_detail(message, node_uuid)


@router.message(Command("hosts"))
async def cmd_hosts(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_hosts_text()
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("host"))
async def cmd_host(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("host.usage"))
        return
    host_uuid = parts[1].strip()
    await _send_host_detail(message, host_uuid)


@router.message(Command("sub"))
async def cmd_sub(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("sub.usage"))
        return
    short_uuid = parts[1].strip()
    await _send_subscription_detail(message, short_uuid)


@router.message(Command("tokens"))
async def cmd_tokens(message: Message) -> None:
    if await _not_admin(message):
        return
    await _show_tokens(message, reply_markup=resources_menu_keyboard())


@router.message(Command("token"))
async def cmd_token_create(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("token.usage"))
        return
    name = parts[1].strip()
    await _create_token(message, name)


@router.message(Command("templates"))
async def cmd_templates(message: Message) -> None:
    if await _not_admin(message):
        return
    await _send_templates(message)


@router.message(Command("template"))
async def cmd_template(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("template.usage"))
        return
    tpl_uuid = parts[1].strip()
    await _send_template_detail(message, tpl_uuid)


@router.message(Command("snippets"))
async def cmd_snippets(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_snippets_text()
    await _send_clean_message(message, text, reply_markup=resources_menu_keyboard())


@router.message(Command("snippet"))
async def cmd_snippet(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("snippet.usage"))
        return
    name = parts[1].strip()
    await _send_snippet_detail(message, name)


@router.message(Command("snippet_add"))
async def cmd_snippet_add(message: Message) -> None:
    if await _not_admin(message):
        return
    await _upsert_snippet(message, action="create")


@router.message(Command("snippet_update"))
async def cmd_snippet_update(message: Message) -> None:
    if await _not_admin(message):
        return
    await _upsert_snippet(message, action="update")


@router.message(Command("configs"))
async def cmd_configs(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_configs_text()
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("config"))
async def cmd_config(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("config.usage"))
        return
    config_uuid = parts[1].strip()
    await _send_config_detail(message, config_uuid)


@router.callback_query(F.data == "menu:section:users")
async def cb_section_users(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.menu"), reply_markup=users_menu_keyboard())


@router.callback_query(F.data == "menu:create_user")
async def cb_create_user(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    logger.info("🚀 User create flow started by user_id=%s", callback.from_user.id)
    ctx = {"action": "user_create", "stage": "username", "data": {}}
    PENDING_INPUT[callback.from_user.id] = ctx
    await _send_user_create_prompt(callback, _("user.prompt_username"), ctx=ctx)


@router.callback_query(F.data.startswith("user_create:"))
async def cb_user_create_flow(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    logger.info("🔄 User create callback action=%s user_id=%s", callback.data, callback.from_user.id)
    await _handle_user_create_callback(callback)


@router.callback_query(F.data == "menu:section:nodes")
async def cb_section_nodes(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.menu"), reply_markup=nodes_menu_keyboard())


@router.callback_query(F.data == "menu:section:resources")
async def cb_section_resources(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.menu"), reply_markup=resources_menu_keyboard())


@router.callback_query(F.data == "menu:section:billing")
async def cb_section_billing(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.menu"), reply_markup=billing_overview_keyboard())


@router.callback_query(F.data == "menu:section:bulk")
async def cb_section_bulk(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.menu"), reply_markup=bulk_menu_keyboard())


@router.callback_query(F.data == "menu:section:system")
async def cb_section_system(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.menu"), reply_markup=system_menu_keyboard())


@router.callback_query(F.data == "menu:health")
async def cb_health(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_health_text()
    await _edit_text_safe(callback.message, text, reply_markup=system_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "menu:stats")
async def cb_stats(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = _("stats.menu_title")
    await _edit_text_safe(callback.message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("stats:"))
async def cb_stats_type(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    stats_type = callback.data.split(":")[-1]
    
    if stats_type == "panel":
        text = await _fetch_panel_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")
    elif stats_type == "server":
        text = await _fetch_server_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")
    else:
        await callback.answer(_("errors.generic"), show_alert=True)


@router.callback_query(F.data == "menu:find_user")
async def cb_find_user(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _start_user_search_flow(callback)


@router.callback_query(F.data.startswith("user_search:view:"))
async def cb_user_search_view(callback: CallbackQuery) -> None:
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
        logger.exception("в?? User search selection failed user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))
        return

    PENDING_INPUT[callback.from_user.id] = {"action": "user_search"}
    await _send_user_summary(callback, user, back_to=back_to)


@router.callback_query(F.data == "menu:nodes")
async def cb_nodes(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_nodes_text()
    await callback.message.edit_text(text, reply_markup=nodes_menu_keyboard())


@router.callback_query(F.data.startswith("nodes:") | F.data.startswith("node_create:"))
async def cb_nodes_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    # Обрабатываем как nodes:action, так и node_create:action
    if callback.data.startswith("node_create:"):
        action = parts[1] if len(parts) > 1 else None
    else:
        action = parts[1] if len(parts) > 1 else None
    
    if action == "create":
        # Начинаем создание ноды
        PENDING_INPUT[callback.from_user.id] = {
            "action": "node_create",
            "stage": "name",
            "data": {}
        }
        await callback.message.edit_text(
            _("node.prompt_name"),
            reply_markup=input_keyboard("node_create"),
            parse_mode="Markdown"
        )
    elif action == "select_profile":
        # Выбор профиля конфигурации
        if len(parts) < 3:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_menu_keyboard())
            return
        profile_uuid = parts[2]
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        
        try:
            # Получаем информацию о профиле и его инбаундах
            profile_data = await api_client.get_config_profile_computed(profile_uuid)
            profile_info = profile_data.get("response", profile_data)
            inbounds = profile_info.get("inbounds", [])
            
            if not inbounds:
                await callback.message.edit_text(
                    _("node.no_inbounds"),
                    reply_markup=input_keyboard("node_create"),
                    parse_mode="Markdown"
                )
                return
            
            data["config_profile_uuid"] = profile_uuid
            data["profile_name"] = profile_info.get("name", "n/a")
            data["available_inbounds"] = inbounds
            data["selected_inbounds"] = []
            ctx["stage"] = "inbounds"
            PENDING_INPUT[user_id] = ctx
            
            # Показываем список инбаундов для выбора
            keyboard = _node_inbounds_keyboard(inbounds, [])
            await callback.message.edit_text(
                _("node.prompt_inbounds").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    profile_name=escape_markdown(data["profile_name"])
                ),
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "toggle_inbound":
        # Переключение выбора инбаунда
        if len(parts) < 3:
            return
        inbound_uuid = parts[2]
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        selected = data.get("selected_inbounds", [])
        available = data.get("available_inbounds", [])
        
        if inbound_uuid in selected:
            selected.remove(inbound_uuid)
        else:
            selected.append(inbound_uuid)
        
        data["selected_inbounds"] = selected
        PENDING_INPUT[user_id] = ctx
        
        # Обновляем клавиатуру
        keyboard = _node_inbounds_keyboard(available, selected)
        await callback.message.edit_text(
            _("node.prompt_inbounds").format(
                name=escape_markdown(data.get("name", "")),
                address=escape_markdown(data.get("address", "")),
                profile_name=escape_markdown(data.get("profile_name", ""))
            ),
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    elif action == "confirm_inbounds":
        # Подтверждение выбора инбаундов
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        selected = data.get("selected_inbounds", [])
        
        if not selected:
            await callback.answer(_("node.no_inbounds"), show_alert=True)
            return
        
        ctx["stage"] = "port"
        PENDING_INPUT[user_id] = ctx
        
        await callback.message.edit_text(
            _("node.prompt_port").format(
                name=escape_markdown(data.get("name", "")),
                address=escape_markdown(data.get("address", "")),
                profile_name=escape_markdown(data.get("profile_name", "")),
                inbounds_count=len(selected)
            ),
            reply_markup=input_keyboard("node_create", allow_skip=True, skip_callback="input:skip:node_create:port"),
            parse_mode="Markdown"
        )
    elif action == "select_provider":
        # Выбор провайдера
        if len(parts) < 3:
            return
        provider_uuid = parts[2] if parts[2] != "none" else None
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        data["provider_uuid"] = provider_uuid
        ctx["stage"] = "traffic_tracking"
        PENDING_INPUT[user_id] = ctx
        
        provider_name = "—" if not provider_uuid else "—"  # Можно получить имя провайдера
        await callback.message.edit_text(
            _("node.prompt_traffic_tracking").format(
                name=escape_markdown(data.get("name", "")),
                address=escape_markdown(data.get("address", "")),
                port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                country=escape_markdown(data.get("country_code", "—") or "—"),
                provider=escape_markdown(provider_name),
                profile_name=escape_markdown(data.get("profile_name", "")),
                inbounds_count=len(data.get("selected_inbounds", []))
            ),
            reply_markup=_node_yes_no_keyboard("node_create", "traffic_tracking"),
            parse_mode="Markdown"
        )
    elif action == "toggle_traffic_tracking":
        # Переключение отслеживания трафика
        if len(parts) < 3:
            return
        value = parts[2]  # yes или no
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        data["is_traffic_tracking_active"] = (value == "yes")
        ctx["stage"] = "traffic_limit"
        PENDING_INPUT[user_id] = ctx
        
        tracking_display = _("node.yes") if data["is_traffic_tracking_active"] else _("node.no")
        await callback.message.edit_text(
            _("node.prompt_traffic_limit").format(
                name=escape_markdown(data.get("name", "")),
                address=escape_markdown(data.get("address", "")),
                port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                country=escape_markdown(data.get("country_code", "—") or "—"),
                provider=escape_markdown(data.get("provider_name", "—") or "—"),
                profile_name=escape_markdown(data.get("profile_name", "")),
                inbounds_count=len(data.get("selected_inbounds", [])),
                tracking=tracking_display
            ),
            reply_markup=input_keyboard("node_create", allow_skip=True, skip_callback="input:skip:node_create:traffic_limit"),
            parse_mode="Markdown"
        )


@router.callback_query(F.data == "menu:hosts")
async def cb_hosts(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_hosts_text()
    await callback.message.edit_text(text, reply_markup=nodes_menu_keyboard())


@router.callback_query(F.data == "menu:subs")
async def cb_subs(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _send_subscriptions_page(callback, page=0)


@router.callback_query(F.data == "menu:tokens")
async def cb_tokens(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _show_tokens(callback, reply_markup=resources_menu_keyboard())


@router.callback_query(F.data == "menu:templates")
async def cb_templates(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _send_templates(callback)


@router.callback_query(F.data == "menu:snippets")
async def cb_snippets(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_snippets_text()
    await _edit_text_safe(callback.message, text, reply_markup=resources_menu_keyboard())


@router.callback_query(F.data == "menu:configs")
async def cb_configs(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_configs_text()
    await callback.message.edit_text(text, reply_markup=nodes_menu_keyboard())


@router.callback_query(F.data == "menu:providers")
async def cb_providers(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_providers_text()
    await _edit_text_safe(callback.message, text, reply_markup=providers_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "menu:billing")
async def cb_billing(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_billing_text()
    await _edit_text_safe(callback.message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "menu:billing_nodes")
async def cb_billing_nodes(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_billing_nodes_text()
    await _edit_text_safe(callback.message, text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "menu:bulk_hosts")
async def cb_bulk_hosts(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("bulk_hosts.overview"), reply_markup=bulk_hosts_keyboard())


@router.callback_query(F.data == "menu:system_nodes")
async def cb_system_nodes(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("system_nodes.overview"), reply_markup=system_nodes_keyboard())


@router.callback_query(F.data == "menu:bulk_users")
async def cb_bulk_users(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("bulk.overview"), reply_markup=bulk_users_keyboard())


@router.callback_query(F.data.startswith("input:skip:"))
async def cb_input_skip(callback: CallbackQuery) -> None:
    """Обработчик пропуска шага ввода."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 4:
        return
    
    action = parts[2]  # provider_create, provider_update и т.д.
    stage = parts[3]   # favicon, login_url, name и т.д.
    user_id = callback.from_user.id
    
    if user_id not in PENDING_INPUT:
        return
    
    ctx = PENDING_INPUT[user_id]
    data = ctx.setdefault("data", {})
    
    # Обрабатываем пропуск шага
    if action == "provider_create":
        if stage == "favicon":
            data["favicon"] = "—"
            ctx["stage"] = "login_url"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("provider.prompt_login_url").format(name=data.get("name", ""), favicon="—"),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:login_url"),
                parse_mode="Markdown"
            )
        elif stage == "login_url":
            data["login_url"] = None
            # Создаем провайдера
            await api_client.create_infra_provider(
                name=data["name"],
                favicon_link=None,
                login_url=None
            )
            PENDING_INPUT.pop(user_id, None)
            await callback.message.edit_text(_("provider.created"), reply_markup=providers_menu_keyboard())
    
    elif action == "provider_update":
        if stage == "name":
            # Оставляем текущее имя
            data["name"] = data.get("current_name", "")
            ctx["stage"] = "favicon"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("provider.prompt_update_favicon").format(
                    current_name=data["name"],
                    current_favicon=data.get("current_favicon", "—") or "—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:favicon"),
                parse_mode="Markdown"
            )
        elif stage == "favicon":
            # Оставляем текущий favicon
            data["favicon"] = data.get("current_favicon") or None
            ctx["stage"] = "login_url"
            PENDING_INPUT[user_id] = ctx
            favicon_display = data["favicon"] if data["favicon"] else "—"
            await callback.message.edit_text(
                _("provider.prompt_update_login_url").format(
                    current_name=data.get("name", ""),
                    current_favicon=favicon_display,
                    current_login_url=data.get("current_login_url", "—") or "—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:login_url"),
                parse_mode="Markdown"
            )
        elif stage == "login_url":
            # Оставляем текущий login_url
            data["login_url"] = data.get("current_login_url") or None
            # Обновляем провайдера
            provider_uuid = ctx.get("provider_uuid")
            current_name = data.get("current_name", "")
            current_favicon = data.get("current_favicon") or ""
            current_login_url = data.get("current_login_url") or ""
            
            # Определяем, что изменилось
            name = None
            if data.get("name") and data.get("name") != current_name:
                name = data.get("name")
            
            favicon = None
            new_favicon_val = data.get("favicon") or ""
            if new_favicon_val != current_favicon:
                favicon = new_favicon_val if new_favicon_val else None
            
            login_url = None
            new_login_url_val = data.get("login_url") or ""
            if new_login_url_val != current_login_url:
                login_url = new_login_url_val if new_login_url_val else None
            
            await api_client.update_infra_provider(
                provider_uuid,
                name=name,
                favicon_link=favicon,
                login_url=login_url
            )
            PENDING_INPUT.pop(user_id, None)
            await callback.message.edit_text(_("provider.updated"), reply_markup=providers_menu_keyboard())
    
    elif action == "node_create":
        # Обработка пропуска шагов при создании ноды
        if stage == "port":
            data["port"] = None
            ctx["stage"] = "country"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_country").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port="—",
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", []))
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:country"),
                parse_mode="Markdown"
            )
        elif stage == "country":
            data["country_code"] = None
            ctx["stage"] = "provider"
            PENDING_INPUT[user_id] = ctx
            # Показываем список провайдеров
            try:
                providers_data = await api_client.get_infra_providers()
                providers = providers_data.get("response", {}).get("providers", [])
                keyboard = _node_providers_keyboard(providers) if providers else input_keyboard(action, allow_skip=True, skip_callback="nodes:select_provider:none")
                await callback.message.edit_text(
                    _("node.prompt_provider").format(
                        name=escape_markdown(data.get("name", "")),
                        address=escape_markdown(data.get("address", "")),
                        port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                        country="—",
                        profile_name=escape_markdown(data.get("profile_name", "")),
                        inbounds_count=len(data.get("selected_inbounds", []))
                    ),
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            except Exception:
                data["provider_uuid"] = None
                ctx["stage"] = "traffic_tracking"
                PENDING_INPUT[user_id] = ctx
                await callback.message.edit_text(
                    _("node.prompt_traffic_tracking").format(
                        name=escape_markdown(data.get("name", "")),
                        address=escape_markdown(data.get("address", "")),
                        port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                        country="—",
                        provider="—",
                        profile_name=escape_markdown(data.get("profile_name", "")),
                        inbounds_count=len(data.get("selected_inbounds", []))
                    ),
                    reply_markup=_node_yes_no_keyboard("node_create", "traffic_tracking"),
                    parse_mode="Markdown"
                )
        elif stage == "traffic_limit":
            data["traffic_limit_bytes"] = None
            ctx["stage"] = "notify_percent"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_notify_percent").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:notify_percent"),
                parse_mode="Markdown"
            )
        elif stage == "notify_percent":
            data["notify_percent"] = None
            ctx["stage"] = "traffic_reset_day"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_traffic_reset_day").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=escape_markdown(format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—"),
                    notify_percent="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:traffic_reset_day"),
                parse_mode="Markdown"
            )
        elif stage == "traffic_reset_day":
            data["traffic_reset_day"] = None
            ctx["stage"] = "consumption_multiplier"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_consumption_multiplier").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=escape_markdown(format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—"),
                    notify_percent=escape_markdown(str(data["notify_percent"]) if data.get("notify_percent") is not None else "—"),
                    reset_day="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:consumption_multiplier"),
                parse_mode="Markdown"
            )
        elif stage == "consumption_multiplier":
            data["consumption_multiplier"] = None
            ctx["stage"] = "tags"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_tags").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=escape_markdown(format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—"),
                    notify_percent=escape_markdown(str(data["notify_percent"]) if data.get("notify_percent") is not None else "—"),
                    reset_day=escape_markdown(str(data["traffic_reset_day"]) if data.get("traffic_reset_day") else "—"),
                    multiplier="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:tags"),
                parse_mode="Markdown"
            )
        elif stage == "tags":
            data["tags"] = None
            # Создаем ноду
            try:
                await api_client.create_node(
                    name=data["name"],
                    address=data["address"],
                    config_profile_uuid=data["config_profile_uuid"],
                    active_inbounds=data["selected_inbounds"],
                    port=data.get("port"),
                    country_code=data.get("country_code"),
                    provider_uuid=data.get("provider_uuid"),
                    is_traffic_tracking_active=data.get("is_traffic_tracking_active", False),
                    traffic_limit_bytes=data.get("traffic_limit_bytes"),
                    notify_percent=data.get("notify_percent"),
                    traffic_reset_day=data.get("traffic_reset_day"),
                    consumption_multiplier=data.get("consumption_multiplier"),
                    tags=data.get("tags"),
                )
                PENDING_INPUT.pop(user_id, None)
                nodes_text = await _fetch_nodes_text()
                await callback.message.edit_text(nodes_text, reply_markup=nodes_menu_keyboard())
            except UnauthorizedError:
                PENDING_INPUT.pop(user_id, None)
                await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nodes_menu_keyboard())
            except ApiClientError:
                PENDING_INPUT.pop(user_id, None)
                logger.exception("❌ Node creation failed")
                await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_menu_keyboard())


@router.callback_query(F.data.startswith("providers:"))
async def cb_providers_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else None
    
    if action == "create":
        PENDING_INPUT[callback.from_user.id] = {"action": "provider_create", "stage": "name", "data": {}}
        await callback.message.edit_text(_("provider.prompt_name"), reply_markup=input_keyboard("provider_create"), parse_mode="Markdown")
    elif action == "update":
        # Показываем список провайдеров для выбора
        try:
            providers_data = await api_client.get_infra_providers()
            providers = providers_data.get("response", {}).get("providers", [])
            if not providers:
                await callback.message.edit_text(_("provider.empty"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
                return
            keyboard = _providers_select_keyboard(providers, "update")
            await callback.message.edit_text(_("provider.select_update"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
    elif action == "update_select":
        # Начинаем редактирование выбранного провайдера
        if len(parts) < 3:
            await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
            return
        provider_uuid = parts[2]
        try:
            # Получаем данные провайдера
            provider_data = await api_client.get_infra_provider(provider_uuid)
            provider_info = provider_data.get("response", {})
            current_name = provider_info.get("name", "")
            current_favicon = provider_info.get("faviconLink") or ""
            current_login_url = provider_info.get("loginUrl") or ""
            
            # Начинаем пошаговое редактирование
            PENDING_INPUT[callback.from_user.id] = {
                "action": "provider_update",
                "stage": "name",
                "provider_uuid": provider_uuid,
                "data": {
                    "current_name": current_name,
                    "current_favicon": current_favicon,
                    "current_login_url": current_login_url,
                }
            }
            await callback.message.edit_text(
                _("provider.prompt_update_name").format(current_name=current_name),
                reply_markup=input_keyboard("provider_update", allow_skip=True, skip_callback="input:skip:provider_update:name"),
                parse_mode="Markdown"
            )
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete":
        PENDING_INPUT[callback.from_user.id] = {"action": "provider_delete"}
        await callback.message.edit_text(_("provider.prompt_delete"), reply_markup=providers_menu_keyboard())
    else:
        await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard())


@router.callback_query(F.data.startswith("billing:"))
async def cb_billing_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        return
    
    action = parts[1]  # Вторая часть после "billing:"
    
    if action == "stats":
        text = await _fetch_billing_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "create":
        # Показываем список провайдеров для выбора
        try:
            providers_data = await api_client.get_infra_providers()
            providers = providers_data.get("response", {}).get("providers", [])
            if not providers:
                await _edit_text_safe(callback.message, _("billing.no_providers"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
                return
            keyboard = _billing_providers_keyboard(providers, "billing_history_create")
            await _edit_text_safe(callback.message, _("billing.select_provider"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete":
        # Показываем список записей для удаления
        try:
            billing_data = await api_client.get_infra_billing_history()
            records = billing_data.get("response", {}).get("records", [])
            if not records:
                await _edit_text_safe(callback.message, _("billing.empty"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
                return
            rows: list[list[InlineKeyboardButton]] = []
            for rec in records[:10]:
                provider = rec.get("provider", {})
                amount = rec.get("amount", "—")
                date = format_datetime(rec.get("billedAt"))
                record_uuid = rec.get("uuid", "")
                label = f"{amount} — {provider.get('name', '—')} ({date})"
                rows.append([InlineKeyboardButton(text=label, callback_data=f"billing:delete_confirm:{record_uuid}")])
            rows.append(nav_row(NavTarget.BILLING_MENU))
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            await _edit_text_safe(callback.message, _("billing.select_delete"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete_confirm":
        # Подтверждение удаления записи биллинга
        if len(parts) < 3:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
            return
        record_uuid = parts[2]
        try:
            await api_client.delete_infra_billing_record(record_uuid)
            text = await _fetch_billing_text()
            await _edit_text_safe(callback.message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        except ApiClientError:
            logger.exception("❌ Billing record delete failed")
            await _edit_text_safe(callback.message, _("billing.invalid"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "provider":
        # Обработка выбора провайдера
        if len(parts) < 4:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
            return
        provider_action = parts[2]  # billing_history_create или billing_nodes_create
        provider_uuid = parts[3]
        
        if provider_action == "billing_history_create":
            # Для создания записи биллинга запрашиваем сумму, затем дату
            try:
                provider_data = await api_client.get_infra_provider(provider_uuid)
                provider_name = provider_data.get("response", {}).get("name", "—")
            except Exception:
                provider_name = "—"
            PENDING_INPUT[callback.from_user.id] = {
                "action": "billing_history_create",
                "stage": "amount",
                "provider_uuid": provider_uuid,
                "provider_name": provider_name,
                "data": {},
            }
            await _edit_text_safe(callback.message, _("billing.prompt_amount"), reply_markup=input_keyboard("billing_history_create"), parse_mode="Markdown")
        elif provider_action == "billing_nodes_create":
            # Для создания биллинга ноды нужно показать все ноды системы
            # (можно создать биллинг для любой ноды с указанным провайдером)
            try:
                nodes_data = await api_client.get_nodes()
                all_nodes = nodes_data.get("response", {}).get("nodes", [])
                if not all_nodes:
                    await _edit_text_safe(callback.message, _("billing_nodes.no_nodes"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                    return
                keyboard = _billing_nodes_keyboard(all_nodes, "billing_nodes_create", provider_uuid)
                await _edit_text_safe(callback.message, _("billing_nodes.select_node"), reply_markup=keyboard, parse_mode="Markdown")
            except Exception:
                await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        else:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    else:
        await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("billing_nodes:"))
async def cb_billing_nodes_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else None
    
    if action == "create":
        # Сначала выбираем провайдера
        try:
            providers_data = await api_client.get_infra_providers()
            providers = providers_data.get("response", {}).get("providers", [])
            if not providers:
                await _edit_text_safe(callback.message, _("billing_nodes.no_providers"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                return
            keyboard = _billing_providers_keyboard(providers, "billing_nodes_create", NavTarget.BILLING_NODES_MENU)
            await _edit_text_safe(callback.message, _("billing_nodes.select_provider"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "node":
        # Обработка выбора ноды после выбора провайдера
        if len(parts) < 4:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            return
        node_action = parts[2]  # billing_nodes:node:action:uuid:provider_uuid
        node_uuid = parts[3]
        provider_uuid = parts[4] if len(parts) > 4 else None
        
        if node_action == "billing_nodes_create" and provider_uuid:
            # Запрашиваем дату следующей оплаты (опционально)
            PENDING_INPUT[callback.from_user.id] = {
                "action": "billing_nodes_create_confirm",
                "provider_uuid": provider_uuid,
                "node_uuid": node_uuid,
            }
            await _edit_text_safe(callback.message, _("billing_nodes.prompt_date_optional"), reply_markup=input_keyboard("billing_nodes_create_confirm"), parse_mode="Markdown")
        elif node_action == "billing_nodes_update":
            # Находим UUID записи биллинга для этой ноды
            try:
                nodes_data = await api_client.get_infra_billing_nodes()
                billing_nodes = nodes_data.get("response", {}).get("billingNodes", [])
                record_uuid = None
                for item in billing_nodes:
                    if item.get("node", {}).get("uuid") == node_uuid:
                        record_uuid = item.get("uuid")
                        break
                if not record_uuid:
                    await _edit_text_safe(callback.message, _("billing_nodes.not_found"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                    return
                # Запрашиваем новую дату оплаты
                PENDING_INPUT[callback.from_user.id] = {
                    "action": "billing_nodes_update_date",
                    "record_uuid": record_uuid,
                }
                await _edit_text_safe(callback.message, _("billing_nodes.prompt_new_date"), reply_markup=input_keyboard("billing_nodes_update_date"), parse_mode="Markdown")
            except Exception:
                await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        else:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete_confirm":
        # Подтверждение удаления записи биллинга ноды
        if len(parts) < 3:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            return
        record_uuid = parts[2]  # billing_nodes:delete_confirm:uuid
        try:
            await api_client.delete_infra_billing_node(record_uuid)
            text = await _fetch_billing_nodes_text()
            await _edit_text_safe(callback.message, text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        except ApiClientError:
            logger.exception("❌ Billing node delete failed")
            await _edit_text_safe(callback.message, _("billing_nodes.invalid"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "update":
        # Показываем список нод с биллингом для обновления
        try:
            nodes_data = await api_client.get_infra_billing_nodes()
            billing_nodes = nodes_data.get("response", {}).get("billingNodes", [])
            if not billing_nodes:
                await _edit_text_safe(callback.message, _("billing_nodes.empty"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                return
            # Создаем список нод для выбора
            nodes_list = [item.get("node", {}) for item in billing_nodes if item.get("node")]
            keyboard = _billing_nodes_keyboard(nodes_list, "billing_nodes_update")
            await _edit_text_safe(callback.message, _("billing_nodes.select_nodes_update"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "stats":
        # Показываем статистику биллинга нод
        text = await _fetch_billing_nodes_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete":
        # Показываем список нод с биллингом для удаления
        try:
            nodes_data = await api_client.get_infra_billing_nodes()
            billing_nodes = nodes_data.get("response", {}).get("billingNodes", [])
            if not billing_nodes:
                await _edit_text_safe(callback.message, _("billing_nodes.empty"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                return
            # Создаем список записей биллинга для удаления
            rows: list[list[InlineKeyboardButton]] = []
            for item in billing_nodes[:10]:
                node = item.get("node", {})
                record_uuid = item.get("uuid", "")
                name = node.get("name", "n/a")
                country = node.get("countryCode", "")
                label = f"{name} ({country})" if country else name
                rows.append([InlineKeyboardButton(text=label, callback_data=f"billing_nodes:delete_confirm:{record_uuid}")])
            rows.append(nav_row(NavTarget.BILLING_NODES_MENU))
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            await _edit_text_safe(callback.message, _("billing_nodes.select_delete"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    else:
        await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "nav:home")
async def cb_nav_home(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.MAIN_MENU)


@router.callback_query(F.data.startswith("nav:back:"))
async def cb_nav_back(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    target = callback.data.split(":", 2)[2]
    await _navigate(callback, target)


@router.callback_query(F.data.startswith("subs:page:"))
async def cb_subs_page(callback: CallbackQuery) -> None:
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

    SUBS_PAGE_BY_USER[callback.from_user.id] = _get_subs_page(callback.from_user.id)
    await _send_user_summary(callback, user, back_to=back_to)


@router.callback_query(F.data.startswith("user_configs:"))
async def cb_user_configs(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, user_uuid = callback.data.split(":")
    back_to = _get_user_detail_back_target(callback.from_user.id)
    try:
        data = await api_client.get_config_profiles()
        profiles = data.get("response", {}).get("configProfiles", [])
        text = _("user.configs_title").format(count=len(profiles)) + "\n" + build_config_profiles_list(profiles, _)
    except UnauthorizedError:
        text = _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Failed to fetch configs for user_uuid=%s actor_id=%s", user_uuid, callback.from_user.id)
        text = _("errors.generic")
    await callback.message.edit_text(text, reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await _navigate(callback, NavTarget.MAIN_MENU)


@router.callback_query(F.data.startswith("user:"))
async def cb_user_actions(callback: CallbackQuery) -> None:
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


@router.callback_query(F.data.startswith("user_edit:"))
async def cb_user_edit_menu(callback: CallbackQuery) -> None:
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

@router.callback_query(F.data.startswith("node:"))
async def cb_node_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, node_uuid, action = callback.data.split(":")
    try:
        if action == "enable":
            await api_client.enable_node(node_uuid)
        elif action == "disable":
            await api_client.disable_node(node_uuid)
        elif action == "restart":
            await api_client.restart_node(node_uuid)
        elif action == "reset":
            await api_client.reset_node_traffic(node_uuid)
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
        await _send_node_detail(callback, node_uuid, from_callback=True)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("node.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Node action failed action=%s node_uuid=%s actor_id=%s", action, node_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("host:"))
async def cb_host_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, host_uuid, action = callback.data.split(":")
    try:
        if action == "enable":
            await api_client.enable_hosts([host_uuid])
        elif action == "disable":
            await api_client.disable_hosts([host_uuid])
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
        await _send_host_detail(callback, host_uuid, from_callback=True)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("host.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Host action failed action=%s host_uuid=%s actor_id=%s", action, host_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("token:"))
async def cb_token_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, token_uuid, action = callback.data.split(":")
    try:
        if action == "delete":
            await api_client.delete_token(token_uuid)
            await callback.message.edit_text(_("token.deleted"), reply_markup=main_menu_keyboard())
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("token.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Token action failed action=%s token_uuid=%s actor_id=%s", action, token_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("template:"))
async def cb_template_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if parts[1] == "create":
        PENDING_INPUT[callback.from_user.id] = {"action": "template_create"}
        await callback.message.edit_text(_("template.prompt_create"), reply_markup=template_menu_keyboard())
        return
    if parts[1] == "reorder":
        PENDING_INPUT[callback.from_user.id] = {"action": "template_reorder"}
        await callback.message.edit_text(_("template.prompt_reorder"), reply_markup=template_menu_keyboard())
        return

    _prefix, tpl_uuid, action = parts
    try:
        if action == "delete":
            await api_client.delete_template(tpl_uuid)
            await _send_templates(callback)
        elif action == "update_json":
            PENDING_INPUT[callback.from_user.id] = {"action": "template_update_json", "uuid": tpl_uuid}
            await callback.message.edit_text(_("template.prompt_update_json"), reply_markup=template_actions_keyboard(tpl_uuid))
            return
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("template.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Template action failed action=%s template_uuid=%s actor_id=%s", action, tpl_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("tplview:"))
async def cb_template_view(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, tpl_uuid = callback.data.split(":")
    try:
        data = await api_client.get_template(tpl_uuid)
        template = data.get("response", data)
        text = build_template_summary(template, _)
        await _edit_text_safe(callback.message, text, reply_markup=template_actions_keyboard(tpl_uuid))
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("template.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Template view failed template_uuid=%s actor_id=%s", tpl_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())

@router.callback_query(F.data.startswith("snippet:"))
async def cb_snippet_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, name, action = callback.data.split(":")
    try:
        if action == "delete":
            await api_client.delete_snippet(name)
            await callback.message.edit_text(_("snippet.deleted"), reply_markup=main_menu_keyboard())
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("snippet.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Snippet action failed action=%s name=%s actor_id=%s", action, name, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("bulk:users:"))
async def cb_bulk_users_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[2] if len(parts) > 2 else None
    try:
        if action == "reset":
            await api_client.bulk_reset_traffic_all_users()
            await _edit_text_safe(callback.message, _("bulk.done"), reply_markup=bulk_users_keyboard())
        elif action == "delete" and len(parts) > 3:
            status = parts[3]
            await api_client.bulk_delete_users_by_status(status)
            await _edit_text_safe(callback.message, _("bulk.done"), reply_markup=bulk_users_keyboard())
        elif action == "extend_all" and len(parts) > 3:
            try:
                days = int(parts[3])
            except ValueError:
                await callback.answer(_("errors.generic"), show_alert=True)
                return
            await api_client.bulk_extend_all_users(days)
            await _edit_text_safe(callback.message, _("bulk.done"), reply_markup=bulk_users_keyboard())
        elif action == "extend_active":
            # Запрашиваем количество дней
            PENDING_INPUT[callback.from_user.id] = {"action": "bulk_users_extend_active"}
            await _edit_text_safe(callback.message, _("bulk.prompt_extend_active"), reply_markup=bulk_users_keyboard())
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_users_keyboard())
    except ApiClientError:
        logger.exception("❌ Bulk users action failed action=%s", action)
        await _edit_text_safe(callback.message, _("bulk.error"), reply_markup=bulk_users_keyboard())




@router.callback_query(F.data.startswith("bulk:hosts:"))
async def cb_bulk_hosts_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    action = callback.data.split(":")[-1]
    if action == "list":
        text = await _fetch_hosts_text()
        await _edit_text_safe(callback.message, text, reply_markup=bulk_hosts_keyboard())
        return
    try:
        if action == "enable_all":
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            uuids = [h.get("uuid") for h in hosts if h.get("uuid")]
            if uuids:
                await api_client.bulk_enable_hosts(uuids)
            await _edit_text_safe(callback.message, _("bulk_hosts.done"), reply_markup=bulk_hosts_keyboard())
        elif action == "disable_all":
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            uuids = [h.get("uuid") for h in hosts if h.get("uuid")]
            if uuids:
                await api_client.bulk_disable_hosts(uuids)
            await _edit_text_safe(callback.message, _("bulk_hosts.done"), reply_markup=bulk_hosts_keyboard())
        elif action == "delete_disabled":
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            uuids = [h.get("uuid") for h in hosts if h.get("uuid") and h.get("isDisabled")]
            if uuids:
                await api_client.bulk_delete_hosts(uuids)
            await _edit_text_safe(callback.message, _("bulk_hosts.done"), reply_markup=bulk_hosts_keyboard())
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_hosts_keyboard())
    except ApiClientError:
        logger.exception("❌ Bulk hosts action failed action=%s", action)
        await _edit_text_safe(callback.message, _("bulk_hosts.error"), reply_markup=bulk_hosts_keyboard())


@router.callback_query(F.data.startswith("system:nodes:"))
async def cb_system_nodes_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[-1]
    
    if action == "list":
        text = await _fetch_nodes_text()
        await _edit_text_safe(callback.message, text, reply_markup=system_nodes_keyboard())
        return
    
    if action == "assign_profile":
        try:
            data = await api_client.get_config_profiles()
            profiles = data.get("response", {}).get("configProfiles", [])
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=system_nodes_keyboard())
            return
        except ApiClientError:
            logger.exception("❌ System nodes fetch profiles failed")
            await _edit_text_safe(callback.message, _("system_nodes.error"), reply_markup=system_nodes_keyboard())
            return

        if not profiles:
            await _edit_text_safe(callback.message, _("system_nodes.no_profiles"), reply_markup=system_nodes_keyboard())
            return

        await _edit_text_safe(
            callback.message,
            _("system_nodes.select_profile"),
            reply_markup=_system_nodes_profiles_keyboard(profiles),
        )
        return

    if len(parts) >= 4 and parts[2] == "profile":
        profile_uuid = parts[3]
        try:
            profile = await api_client.get_config_profile_computed(profile_uuid)
            info = profile.get("response", profile)
            inbounds = info.get("inbounds", [])
            inbound_uuids = [i.get("uuid") for i in inbounds if i.get("uuid")]

            nodes_data = await api_client.get_nodes()
            nodes = nodes_data.get("response", [])
            uuids = [n.get("uuid") for n in nodes if n.get("uuid")]

            if not uuids:
                await _edit_text_safe(callback.message, _("system_nodes.no_nodes"), reply_markup=system_nodes_keyboard())
                return

            await api_client.bulk_nodes_profile_modification(uuids, profile_uuid, inbound_uuids)
            await _edit_text_safe(callback.message, _("system_nodes.done_assign"), reply_markup=system_nodes_keyboard())
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=system_nodes_keyboard())
        except ApiClientError:
            logger.exception("❌ System nodes assign profile failed profile_uuid=%s", profile_uuid)
            await _edit_text_safe(callback.message, _("system_nodes.error"), reply_markup=system_nodes_keyboard())
        return
    
    try:
        # Получаем все ноды
        nodes_data = await api_client.get_nodes()
        nodes = nodes_data.get("response", [])
        uuids = [n.get("uuid") for n in nodes if n.get("uuid")]
        
        if not uuids:
            await _edit_text_safe(callback.message, _("system_nodes.no_nodes"), reply_markup=system_nodes_keyboard())
            return
        
        # Выполняем операцию для каждой ноды
        success_count = 0
        error_count = 0
        
        if action == "enable_all":
            for uuid in uuids:
                try:
                    await api_client.enable_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "disable_all":
            for uuid in uuids:
                try:
                    await api_client.disable_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "restart_all":
            for uuid in uuids:
                try:
                    await api_client.restart_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "reset_traffic_all":
            for uuid in uuids:
                try:
                    await api_client.reset_node_traffic(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
        
        if error_count > 0:
            result_text = _("system_nodes.done_partial").format(success=success_count, errors=error_count)
        else:
            result_text = _("system_nodes.done").format(count=success_count)
        
        await _edit_text_safe(callback.message, result_text, reply_markup=system_nodes_keyboard())
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=system_nodes_keyboard())
    except ApiClientError:
        logger.exception("❌ System nodes action failed action=%s", action)
        await _edit_text_safe(callback.message, _("system_nodes.error"), reply_markup=system_nodes_keyboard())


# Bulk helpers
ALLOWED_STATUSES = {"ACTIVE", "DISABLED", "LIMITED", "EXPIRED"}


def _parse_uuids(text: str, expected_min: int = 1) -> list[str]:
    parts = text.split()
    if len(parts) <= expected_min:
        return []
    return parts[expected_min:]


async def _run_bulk_action(
    target: Message | CallbackQuery,
    action: str,
    uuids: list[str] | None = None,
    status: str | None = None,
    days: int | None = None,
) -> None:
    try:
        if action == "reset":
            await api_client.bulk_reset_traffic_users(uuids or [])
        elif action == "delete":
            await api_client.bulk_delete_users(uuids or [])
        elif action == "delete_status":
            if status not in ALLOWED_STATUSES:
                await _reply(target, _("bulk.usage_delete_status"))
                return
            await api_client.bulk_delete_users_by_status(status)
        elif action == "revoke":
            await api_client.bulk_revoke_subscriptions(uuids or [])
        elif action == "extend":
            if days is None:
                await _reply(target, _("bulk.usage_extend"))
                return
            await api_client.bulk_extend_users(uuids or [], days)
        elif action == "extend_all":
            if days is None:
                await _reply(target, _("bulk.usage_extend_all"))
                return
            await api_client.bulk_extend_all_users(days)
        elif action == "status":
            if status not in ALLOWED_STATUSES:
                await _reply(target, _("bulk.usage_status"))
                return
            await api_client.bulk_update_users_status(uuids or [], status)
        else:
            await _reply(target, _("errors.generic"))
            return
        await _reply(target, _("bulk.done"), back=False)
    except UnauthorizedError:
        await _reply(target, _("errors.unauthorized"))
    except ApiClientError:
        logger.exception("❌ Bulk users action failed action=%s", action)
        await _reply(target, _("bulk.error"))


async def _reply(target: Message | CallbackQuery, text: str, back: bool = False) -> None:
    markup = bulk_users_keyboard() if back else None
    if isinstance(target, CallbackQuery):
        await _edit_text_safe(target.message, text, reply_markup=markup)
    else:
        await _send_clean_message(target, text, reply_markup=markup)


@router.callback_query(F.data.startswith("config:"))
async def cb_config_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, config_uuid, action = callback.data.split(":")
    if action != "view":
        await callback.answer(_("errors.generic"), show_alert=True)
        return
    await _send_config_detail(callback, config_uuid)


# Helpers
async def _send_user_detail(
    target: Message | CallbackQuery, query: str, back_to: str = NavTarget.USERS_MENU
) -> None:
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


def _store_user_detail_back_target(user_id: int, back_to: str) -> None:
    USER_DETAIL_BACK_TARGET[user_id] = back_to


def _get_user_detail_back_target(user_id: int) -> str:
    return USER_DETAIL_BACK_TARGET.get(user_id, NavTarget.USERS_MENU)


def _get_subs_page(user_id: int | None) -> int:
    if user_id is None:
        return 0
    return max(SUBS_PAGE_BY_USER.get(user_id, 0), 0)


async def _send_node_detail(target: Message | CallbackQuery, node_uuid: str, from_callback: bool = False) -> None:
    try:
        node = await api_client.get_node(node_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        text = _("node.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("⚠️ API client error while fetching node node_uuid=%s", node_uuid)
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    info = node.get("response", node)
    summary = build_node_summary(node, _)
    is_disabled = bool(info.get("isDisabled"))
    keyboard = node_actions_keyboard(info.get("uuid", node_uuid), is_disabled)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await _send_clean_message(target, summary, reply_markup=keyboard)


async def _send_host_detail(target: Message | CallbackQuery, host_uuid: str, from_callback: bool = False) -> None:
    try:
        host = await api_client.get_host(host_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        text = _("host.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("⚠️ API client error while fetching host host_uuid=%s", host_uuid)
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    info = host.get("response", host)
    summary = build_host_summary(host, _)
    is_disabled = bool(info.get("isDisabled"))
    keyboard = host_actions_keyboard(info.get("uuid", host_uuid), is_disabled)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await _send_clean_message(target, summary, reply_markup=keyboard)


async def _send_subscription_detail(target: Message | CallbackQuery, short_uuid: str) -> None:
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


async def _send_template_detail(target: Message | CallbackQuery, tpl_uuid: str) -> None:
    try:
        tpl = await api_client.get_template(tpl_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        text = _("template.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("⚠️ API client error while fetching template")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    summary = build_template_summary(tpl, _)
    keyboard = template_actions_keyboard(tpl_uuid)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await _send_clean_message(target, summary, reply_markup=keyboard)


async def _handle_template_create_input(message: Message, ctx: dict) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await _send_clean_message(message, _("template.prompt_create"), reply_markup=template_menu_keyboard())
        return
    name, tpl_type = parts[0], parts[1].strip().upper()
    allowed = {"XRAY_JSON", "XRAY_BASE64", "MIHOMO", "STASH", "CLASH", "SINGBOX"}
    if tpl_type not in allowed:
        await _send_clean_message(message, _("template.invalid_type"), reply_markup=template_menu_keyboard())
        return
    try:
        await api_client.create_template(name, tpl_type)
        await _send_clean_message(message, _("template.created"), reply_markup=template_menu_keyboard())
    except UnauthorizedError:
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=template_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Template create failed")
        await _send_clean_message(message, _("template.invalid_payload"), reply_markup=template_menu_keyboard())


async def _handle_template_update_json_input(message: Message, ctx: dict) -> None:
    tpl_uuid = ctx.get("uuid")
    try:
        import json

        payload = json.loads(message.text)
    except Exception:
        await _send_clean_message(message, _("template.invalid_payload"), reply_markup=template_actions_keyboard(tpl_uuid))
        return
    try:
        await api_client.update_template(tpl_uuid, template_json=payload)
        await _send_clean_message(message, _("template.updated"), reply_markup=template_actions_keyboard(tpl_uuid))
    except UnauthorizedError:
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=template_actions_keyboard(tpl_uuid))
    except ApiClientError:
        logger.exception("❌ Template update failed")
        await _send_clean_message(message, _("template.invalid_payload"), reply_markup=template_actions_keyboard(tpl_uuid))


async def _handle_template_reorder_input(message: Message, ctx: dict) -> None:
    uuids = message.text.split()
    if not uuids:
        await _send_clean_message(message, _("template.prompt_reorder"), reply_markup=template_menu_keyboard())
        return
    try:
        await api_client.reorder_templates(uuids)
        await _send_clean_message(message, _("template.reordered"), reply_markup=template_menu_keyboard())
    except UnauthorizedError:
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=template_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Template reorder failed")
        await _send_clean_message(message, _("template.invalid_payload"), reply_markup=template_menu_keyboard())


async def _handle_provider_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action")
    user_id = message.from_user.id
    text = message.text.strip()
    data = ctx.setdefault("data", {})
    stage = ctx.get("stage", None)
    
    try:
        if action == "provider_create":
            # Пошаговый ввод для создания провайдера
            if stage == "name":
                if not text:
                    await _send_clean_message(message, _("provider.prompt_name"), reply_markup=input_keyboard(action), parse_mode="Markdown")
                    PENDING_INPUT[user_id] = ctx
                    return
                data["name"] = text
                ctx["stage"] = "favicon"
                PENDING_INPUT[user_id] = ctx
                await _send_clean_message(
                    message,
                    _("provider.prompt_favicon").format(name=data["name"]),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:favicon"),
                    parse_mode="Markdown"
                )
                return
            
            elif stage == "favicon":
                favicon = text if text else None
                data["favicon"] = favicon if favicon else "—"
                ctx["stage"] = "login_url"
                PENDING_INPUT[user_id] = ctx
                favicon_display = favicon if favicon else "—"
                await _send_clean_message(
                    message,
                    _("provider.prompt_login_url").format(name=data["name"], favicon=favicon_display),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:login_url"),
                    parse_mode="Markdown"
                )
                return
            
            elif stage == "login_url":
                login_url = text if text else None
                data["login_url"] = login_url
                # Создаем провайдера
                await api_client.create_infra_provider(
                    name=data["name"],
                    favicon_link=data.get("favicon") if data.get("favicon") != "—" else None,
                    login_url=login_url
                )
                PENDING_INPUT.pop(user_id, None)
                await _send_clean_message(message, _("provider.created"), reply_markup=providers_menu_keyboard())
                return
        
        elif action == "provider_update":
            # Пошаговый ввод для обновления провайдера
            if stage == "name":
                # Обновляем имя
                new_name = text if text else None
                if new_name:
                    data["name"] = new_name
                else:
                    data["name"] = data.get("current_name", "")
                ctx["stage"] = "favicon"
                PENDING_INPUT[user_id] = ctx
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_favicon").format(
                        current_name=data["name"],
                        current_favicon=data.get("current_favicon", "—") or "—"
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:favicon"),
                    parse_mode="Markdown"
                )
                return
            
            elif stage == "favicon":
                # Обновляем favicon
                new_favicon = text if text else None
                if new_favicon:
                    data["favicon"] = new_favicon
                else:
                    data["favicon"] = data.get("current_favicon") or None
                ctx["stage"] = "login_url"
                PENDING_INPUT[user_id] = ctx
                favicon_display = data["favicon"] if data["favicon"] else "—"
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_login_url").format(
                        current_name=data.get("name", ""),
                        current_favicon=favicon_display,
                        current_login_url=data.get("current_login_url", "—") or "—"
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:login_url"),
                    parse_mode="Markdown"
                )
                return
            
            elif stage == "login_url":
                # Обновляем login_url
                new_login_url = text if text else None
                if new_login_url:
                    data["login_url"] = new_login_url
                else:
                    # Оставляем текущее значение
                    data["login_url"] = data.get("current_login_url") or None
                
                # Обновляем провайдера - передаем только измененные значения
                provider_uuid = ctx.get("provider_uuid")
                current_name = data.get("current_name", "")
                current_favicon = data.get("current_favicon") or ""
                current_login_url = data.get("current_login_url") or ""
                
                # Определяем, что изменилось
                name = None
                if data.get("name") and data.get("name") != current_name:
                    name = data.get("name")
                
                favicon = None
                new_favicon_val = data.get("favicon") or ""
                if new_favicon_val != current_favicon:
                    favicon = new_favicon_val if new_favicon_val else None
                
                login_url = None
                new_login_url_val = data.get("login_url") or ""
                if new_login_url_val != current_login_url:
                    login_url = new_login_url_val if new_login_url_val else None
                
                await api_client.update_infra_provider(
                    provider_uuid,
                    name=name,
                    favicon_link=favicon,
                    login_url=login_url
                )
                PENDING_INPUT.pop(user_id, None)
                await _send_clean_message(message, _("provider.updated"), reply_markup=providers_menu_keyboard())
                return
        elif action == "provider_delete":
            parts = text.split()
            if len(parts) != 1:
                raise ValueError
            await api_client.delete_infra_provider(parts[0])
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, _("provider.deleted"), reply_markup=providers_menu_keyboard())
        else:
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, _("errors.generic"), reply_markup=providers_menu_keyboard())
            return
    except ValueError:
        if action == "provider_create" and stage:
            # Сохраняем контекст для повторного запроса
            PENDING_INPUT[user_id] = ctx
            if stage == "name":
                await _send_clean_message(message, _("provider.prompt_name"), reply_markup=input_keyboard(action), parse_mode="Markdown")
            elif stage == "favicon":
                await _send_clean_message(
                    message,
                    _("provider.prompt_favicon").format(name=data.get("name", "")),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:favicon"),
                    parse_mode="Markdown"
                )
            elif stage == "login_url":
                await _send_clean_message(
                    message,
                    _("provider.prompt_login_url").format(name=data.get("name", ""), favicon=data.get("favicon", "—")),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:login_url"),
                    parse_mode="Markdown"
                )
        elif action == "provider_update" and stage:
            # Сохраняем контекст для повторного запроса
            PENDING_INPUT[user_id] = ctx
            if stage == "name":
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_name").format(current_name=data.get("current_name", "")),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:name"),
                    parse_mode="Markdown"
                )
            elif stage == "favicon":
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_favicon").format(
                        current_name=data.get("name", data.get("current_name", "")),
                        current_favicon=data.get("current_favicon", "—") or "—"
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:favicon"),
                    parse_mode="Markdown"
                )
            elif stage == "login_url":
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_login_url").format(
                        current_name=data.get("name", data.get("current_name", "")),
                        current_favicon=data.get("favicon", data.get("current_favicon", "—")) or "—",
                        current_login_url=data.get("current_login_url", "—") or "—"
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:login_url"),
                    parse_mode="Markdown"
                )
        elif action == "provider_delete":
            prompt_key = "provider.prompt_delete"
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _(prompt_key), reply_markup=input_keyboard(action))
        else:
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("errors.generic"), reply_markup=input_keyboard(action))
    except UnauthorizedError:
        PENDING_INPUT.pop(user_id, None)
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=providers_menu_keyboard())
    except ApiClientError:
        PENDING_INPUT.pop(user_id, None)
        logger.exception("❌ Provider action failed: %s", action)
        await _send_clean_message(message, _("provider.invalid"), reply_markup=providers_menu_keyboard())


async def _handle_billing_history_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action")
    text = message.text.strip()
    user_id = message.from_user.id
    data = ctx.setdefault("data", {})
    stage = ctx.get("stage", None)
    
    try:
        if action == "billing_history_create":
            # Пошаговый ввод для создания записи биллинга
            if stage == "amount":
                try:
                    amount = float(text)
                except ValueError:
                    PENDING_INPUT[user_id] = ctx
                    await _send_clean_message(message, _("billing.prompt_amount"), reply_markup=input_keyboard(action), parse_mode="Markdown")
                    return
                data["amount"] = amount
                ctx["stage"] = "billed_at"
                PENDING_INPUT[user_id] = ctx
                provider_name = ctx.get("provider_name", "—")
                await _send_clean_message(message, _("billing.prompt_billed_at").format(provider_name=provider_name, amount=amount), reply_markup=input_keyboard(action), parse_mode="Markdown")
                return
            
            elif stage == "billed_at":
                if not text:
                    PENDING_INPUT[user_id] = ctx
                    provider_name = ctx.get("provider_name", "—")
                    amount = data.get("amount", 0)
                    await _send_clean_message(message, _("billing.prompt_billed_at").format(provider_name=provider_name, amount=amount), reply_markup=input_keyboard(action), parse_mode="Markdown")
                    return
                # Создаем запись биллинга
                provider_uuid = ctx.get("provider_uuid")
                amount = data.get("amount")
                await api_client.create_infra_billing_record(provider_uuid, amount, text)
                billing_text = await _fetch_billing_text()
                PENDING_INPUT.pop(user_id, None)
                await _send_clean_message(message, billing_text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
                return
        
        elif action == "billing_history_create_amount":
            # Старый формат для обратной совместимости
            parts = text.split()
            if len(parts) < 2:
                raise ValueError
            provider_uuid = ctx.get("provider_uuid")
            amount = float(parts[0])
            billed_at = parts[1]
            await api_client.create_infra_billing_record(provider_uuid, amount, billed_at)
            billing_text = await _fetch_billing_text()
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, billing_text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        elif action == "billing_history_delete":
            parts = text.split()
            if len(parts) != 1:
                raise ValueError
            await api_client.delete_infra_billing_record(parts[0])
            billing_text = await _fetch_billing_text()
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, billing_text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        else:
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
            return
    except ValueError:
        if action == "billing_history_create" and stage:
            PENDING_INPUT[user_id] = ctx
            if stage == "amount":
                await _send_clean_message(message, _("billing.prompt_amount"), reply_markup=input_keyboard(action), parse_mode="Markdown")
            elif stage == "billed_at":
                provider_name = ctx.get("provider_name", "—")
                amount = data.get("amount", 0)
                await _send_clean_message(message, _("billing.prompt_billed_at").format(provider_name=provider_name, amount=amount), reply_markup=input_keyboard(action), parse_mode="Markdown")
        elif action == "billing_history_create_amount":
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing.prompt_amount_date"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        else:
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing.prompt_delete"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    except UnauthorizedError:
        PENDING_INPUT.pop(user_id, None)
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    except ApiClientError:
        PENDING_INPUT.pop(user_id, None)
        logger.exception("❌ Billing history action failed: %s", action)
        await _send_clean_message(message, _("billing.invalid"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


async def _handle_node_create_input(message: Message, ctx: dict) -> None:
    """Обработчик пошагового ввода для создания ноды."""
    action = ctx.get("action")
    user_id = message.from_user.id
    text = message.text.strip()
    data = ctx.setdefault("data", {})
    stage = ctx.get("stage", None)
    
    try:
        if stage == "name":
            if not text or len(text) < 3 or len(text) > 30:
                await _send_clean_message(message, _("node.prompt_name"), reply_markup=input_keyboard(action), parse_mode="Markdown")
                PENDING_INPUT[user_id] = ctx
                return
            data["name"] = text
            ctx["stage"] = "address"
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(
                message,
                _("node.prompt_address").format(name=escape_markdown(data["name"])),
                reply_markup=input_keyboard(action),
                parse_mode="Markdown"
            )
            return
        
        elif stage == "address":
            if not text or len(text) < 2:
                await _send_clean_message(
                    message,
                    _("node.prompt_address").format(name=escape_markdown(data.get("name", ""))),
                    reply_markup=input_keyboard(action),
                    parse_mode="Markdown"
                )
                PENDING_INPUT[user_id] = ctx
                return
            data["address"] = text
            ctx["stage"] = "config_profile"
            PENDING_INPUT[user_id] = ctx
            
            # Показываем список профилей конфигурации
            try:
                profiles_data = await api_client.get_config_profiles()
                profiles = profiles_data.get("response", {}).get("configProfiles", [])
                if not profiles:
                    await _send_clean_message(message, _("node.no_profiles"), reply_markup=nodes_menu_keyboard(), parse_mode="Markdown")
                    PENDING_INPUT.pop(user_id, None)
                    return
                keyboard = _node_config_profiles_keyboard(profiles)
                await _send_clean_message(
                    message,
                    _("node.prompt_config_profile").format(name=escape_markdown(data["name"]), address=escape_markdown(data["address"])),
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            except Exception:
                await _send_clean_message(message, _("errors.generic"), reply_markup=nodes_menu_keyboard(), parse_mode="Markdown")
                PENDING_INPUT.pop(user_id, None)
            return
        
        elif stage == "port":
            if text:
                try:
                    port = int(text)
                    if port < 1 or port > 65535:
                        raise ValueError
                    data["port"] = port
                except ValueError:
                    await _send_clean_message(
                        message,
                        _("node.invalid_port"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:port"),
                        parse_mode="Markdown"
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
            else:
                data["port"] = None
            ctx["stage"] = "country"
            PENDING_INPUT[user_id] = ctx
            port_display = str(data["port"]) if data.get("port") else "—"
            await _send_clean_message(
                message,
                _("node.prompt_country").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(port_display),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", []))
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:country"),
                parse_mode="Markdown"
            )
            return
        
        elif stage == "country":
            if text:
                if len(text) != 2:
                    await _send_clean_message(
                        message,
                        _("node.invalid_country"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:country"),
                        parse_mode="Markdown"
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
                data["country_code"] = text.upper()
            else:
                data["country_code"] = None
            ctx["stage"] = "provider"
            PENDING_INPUT[user_id] = ctx
            
            # Показываем список провайдеров
            try:
                providers_data = await api_client.get_infra_providers()
                providers = providers_data.get("response", {}).get("providers", [])
                keyboard = _node_providers_keyboard(providers) if providers else input_keyboard(action, allow_skip=True, skip_callback="nodes:select_provider:none")
                country_display = data.get("country_code", "—") or "—"
                await _send_clean_message(
                    message,
                    _("node.prompt_provider").format(
                        name=escape_markdown(data.get("name", "")),
                        address=escape_markdown(data.get("address", "")),
                        port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                        country=escape_markdown(country_display),
                        profile_name=escape_markdown(data.get("profile_name", "")),
                        inbounds_count=len(data.get("selected_inbounds", []))
                    ),
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            except Exception:
                # Если провайдеры недоступны, пропускаем
                data["provider_uuid"] = None
                ctx["stage"] = "traffic_tracking"
                PENDING_INPUT[user_id] = ctx
                country_display = data.get("country_code", "—") or "—"
                await _send_clean_message(
                    message,
                    _("node.prompt_traffic_tracking").format(
                        name=escape_markdown(data.get("name", "")),
                        address=escape_markdown(data.get("address", "")),
                        port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                        country=escape_markdown(country_display),
                        provider="—",
                        profile_name=escape_markdown(data.get("profile_name", "")),
                        inbounds_count=len(data.get("selected_inbounds", []))
                    ),
                    reply_markup=_node_yes_no_keyboard("node_create", "traffic_tracking"),
                    parse_mode="Markdown"
                )
            return
        
        elif stage == "traffic_limit":
            if text:
                try:
                    limit = int(text)
                    if limit < 0:
                        raise ValueError
                    data["traffic_limit_bytes"] = limit
                except ValueError:
                    await _send_clean_message(
                        message,
                        _("node.invalid_traffic_limit"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:traffic_limit"),
                        parse_mode="Markdown"
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
            else:
                data["traffic_limit_bytes"] = None
            ctx["stage"] = "notify_percent"
            PENDING_INPUT[user_id] = ctx
            limit_display = format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—"
            await _send_clean_message(
                message,
                _("node.prompt_notify_percent").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=escape_markdown(limit_display)
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:notify_percent"),
                parse_mode="Markdown"
            )
            return
        
        elif stage == "notify_percent":
            if text:
                try:
                    percent = int(text)
                    if percent < 0 or percent > 100:
                        raise ValueError
                    data["notify_percent"] = percent
                except ValueError:
                    await _send_clean_message(
                        message,
                        _("node.invalid_notify_percent"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:notify_percent"),
                        parse_mode="Markdown"
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
            else:
                data["notify_percent"] = None
            ctx["stage"] = "traffic_reset_day"
            PENDING_INPUT[user_id] = ctx
            percent_display = str(data["notify_percent"]) if data.get("notify_percent") is not None else "—"
            await _send_clean_message(
                message,
                _("node.prompt_traffic_reset_day").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=escape_markdown(format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—"),
                    notify_percent=escape_markdown(percent_display)
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:traffic_reset_day"),
                parse_mode="Markdown"
            )
            return
        
        elif stage == "traffic_reset_day":
            if text:
                try:
                    day = int(text)
                    if day < 1 or day > 31:
                        raise ValueError
                    data["traffic_reset_day"] = day
                except ValueError:
                    await _send_clean_message(
                        message,
                        _("node.invalid_reset_day"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:traffic_reset_day"),
                        parse_mode="Markdown"
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
            else:
                data["traffic_reset_day"] = None
            ctx["stage"] = "consumption_multiplier"
            PENDING_INPUT[user_id] = ctx
            day_display = str(data["traffic_reset_day"]) if data.get("traffic_reset_day") else "—"
            await _send_clean_message(
                message,
                _("node.prompt_consumption_multiplier").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=escape_markdown(format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—"),
                    notify_percent=escape_markdown(str(data["notify_percent"]) if data.get("notify_percent") is not None else "—"),
                    reset_day=escape_markdown(day_display)
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:consumption_multiplier"),
                parse_mode="Markdown"
            )
            return
        
        elif stage == "consumption_multiplier":
            if text:
                try:
                    multiplier = float(text)
                    if multiplier < 0.1:
                        raise ValueError
                    data["consumption_multiplier"] = multiplier
                except ValueError:
                    await _send_clean_message(
                        message,
                        _("node.invalid_multiplier"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:consumption_multiplier"),
                        parse_mode="Markdown"
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
            else:
                data["consumption_multiplier"] = None
            ctx["stage"] = "tags"
            PENDING_INPUT[user_id] = ctx
            multiplier_display = str(data["consumption_multiplier"]) if data.get("consumption_multiplier") else "—"
            await _send_clean_message(
                message,
                _("node.prompt_tags").format(
                    name=escape_markdown(data.get("name", "")),
                    address=escape_markdown(data.get("address", "")),
                    port=escape_markdown(str(data.get("port", "—")) if data.get("port") else "—"),
                    country=escape_markdown(data.get("country_code", "—") or "—"),
                    provider=escape_markdown(data.get("provider_name", "—") or "—"),
                    profile_name=escape_markdown(data.get("profile_name", "")),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=escape_markdown(format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—"),
                    notify_percent=escape_markdown(str(data["notify_percent"]) if data.get("notify_percent") is not None else "—"),
                    reset_day=escape_markdown(str(data["traffic_reset_day"]) if data.get("traffic_reset_day") else "—"),
                    multiplier=escape_markdown(multiplier_display)
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:tags"),
                parse_mode="Markdown"
            )
            return
        
        elif stage == "tags":
            if text:
                tags = [tag.strip().upper() for tag in text.split(",") if tag.strip()]
                # Проверяем формат тегов
                import re
                tag_pattern = re.compile(r"^[A-Z0-9_:]+$")
                if len(tags) > 10:
                    await _send_clean_message(
                        message,
                        _("node.invalid_tags"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:tags"),
                        parse_mode="Markdown"
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
                for tag in tags:
                    if not tag_pattern.match(tag) or len(tag) > 36:
                        await _send_clean_message(
                            message,
                            _("node.invalid_tags"),
                            reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:tags"),
                            parse_mode="Markdown"
                        )
                        PENDING_INPUT[user_id] = ctx
                        return
                data["tags"] = tags
            else:
                data["tags"] = None
            
            # Создаем ноду
            try:
                await api_client.create_node(
                    name=data["name"],
                    address=data["address"],
                    config_profile_uuid=data["config_profile_uuid"],
                    active_inbounds=data["selected_inbounds"],
                    port=data.get("port"),
                    country_code=data.get("country_code"),
                    provider_uuid=data.get("provider_uuid"),
                    is_traffic_tracking_active=data.get("is_traffic_tracking_active", False),
                    traffic_limit_bytes=data.get("traffic_limit_bytes"),
                    notify_percent=data.get("notify_percent"),
                    traffic_reset_day=data.get("traffic_reset_day"),
                    consumption_multiplier=data.get("consumption_multiplier"),
                    tags=data.get("tags"),
                )
                PENDING_INPUT.pop(user_id, None)
                nodes_text = await _fetch_nodes_text()
                await _send_clean_message(message, nodes_text, reply_markup=nodes_menu_keyboard())
            except UnauthorizedError:
                PENDING_INPUT.pop(user_id, None)
                await _send_clean_message(message, _("errors.unauthorized"), reply_markup=nodes_menu_keyboard())
            except ApiClientError:
                PENDING_INPUT.pop(user_id, None)
                logger.exception("❌ Node creation failed")
                await _send_clean_message(message, _("errors.generic"), reply_markup=nodes_menu_keyboard())
            return
    
    except Exception as e:
        logger.exception("❌ Node create input error")
        PENDING_INPUT.pop(user_id, None)
        await _send_clean_message(message, _("errors.generic"), reply_markup=nodes_menu_keyboard())


async def _handle_billing_nodes_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action")
    text = (message.text or "").strip()
    user_id = message.from_user.id
    
    try:
        if action == "billing_nodes_create_confirm":
            # Провайдер и нода уже выбраны, дата опциональна
            provider_uuid = ctx.get("provider_uuid")
            node_uuid = ctx.get("node_uuid")
            next_billing_at = text if text else None
            await api_client.create_infra_billing_node(provider_uuid, node_uuid, next_billing_at)
            billing_text = await _fetch_billing_nodes_text()
            await _send_clean_message(message, billing_text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            PENDING_INPUT.pop(user_id, None)
        elif action == "billing_nodes_update_date":
            # UUID записи биллинга уже в контексте
            if not text:
                raise ValueError
            record_uuid = ctx.get("record_uuid")
            if not record_uuid:
                await _send_clean_message(message, _("billing_nodes.not_found"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                PENDING_INPUT.pop(user_id, None)
                return
            await api_client.update_infra_billing_nodes([record_uuid], text)
            billing_text = await _fetch_billing_nodes_text()
            await _send_clean_message(message, billing_text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            PENDING_INPUT.pop(user_id, None)
        else:
            await _send_clean_message(message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            PENDING_INPUT.pop(user_id, None)
            return
    except ValueError:
        if action == "billing_nodes_update_date":
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing_nodes.prompt_new_date"), reply_markup=input_keyboard(action), parse_mode="Markdown")
        else:
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing_nodes.prompt_date_optional"), reply_markup=input_keyboard(action), parse_mode="Markdown")
    except UnauthorizedError:
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        PENDING_INPUT.pop(user_id, None)
    except ApiClientError:
        logger.exception("❌ Billing nodes action failed: %s", action)
        await _send_clean_message(message, _("billing_nodes.invalid"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        PENDING_INPUT.pop(user_id, None)


def _billing_providers_keyboard(providers: list[dict], action_prefix: str, nav_target: str = NavTarget.BILLING_MENU) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера в биллинге."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"billing:provider:{action_prefix}:{uuid}")])
    rows.append(nav_row(nav_target))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _providers_select_keyboard(providers: list[dict], action: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера для обновления или удаления."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"providers:{action}_select:{uuid}")])
    rows.append(nav_row(NavTarget.BILLING_OVERVIEW))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _billing_nodes_keyboard(nodes: list[dict], action_prefix: str, provider_uuid: str = "", nav_target: str = NavTarget.BILLING_NODES_MENU) -> InlineKeyboardMarkup:
    """Клавиатура для выбора ноды в биллинге."""
    rows: list[list[InlineKeyboardButton]] = []
    for node in sorted(nodes, key=lambda n: n.get("name", ""))[:10]:
        name = node.get("name", "n/a")
        uuid = node.get("uuid", "")
        country = node.get("countryCode", "")
        label = f"{name} ({country})" if country else name
        callback_data = f"billing_nodes:node:{action_prefix}:{uuid}"
        if provider_uuid:
            callback_data += f":{provider_uuid}"
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
    rows.append(nav_row(nav_target))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _system_nodes_profiles_keyboard(profiles: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        name = profile.get("name", "n/a")
        uuid = profile.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"system:nodes:profile:{uuid}")])
    rows.append(nav_row(NavTarget.SYSTEM_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _node_config_profiles_keyboard(profiles: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора профиля конфигурации при создании ноды."""
    rows: list[list[InlineKeyboardButton]] = []
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        name = profile.get("name", "n/a")
        uuid = profile.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"nodes:select_profile:{uuid}")])
    rows.append(nav_row(NavTarget.NODES_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _node_inbounds_keyboard(inbounds: list[dict], selected: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора инбаундов при создании ноды."""
    rows: list[list[InlineKeyboardButton]] = []
    for inbound in inbounds[:20]:  # Ограничиваем до 20 для удобства
        name = inbound.get("remark") or inbound.get("tag") or "n/a"
        uuid = inbound.get("uuid", "")
        is_selected = uuid in selected
        prefix = "✅ " if is_selected else "☐ "
        rows.append([InlineKeyboardButton(text=f"{prefix}{name}", callback_data=f"nodes:toggle_inbound:{uuid}")])
    
    # Кнопка подтверждения выбора
    if selected:
        rows.append([InlineKeyboardButton(text=_("node.select_inbounds_done").format(count=len(selected)), callback_data="nodes:confirm_inbounds")])
    
    rows.append(nav_row(NavTarget.NODES_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _node_providers_keyboard(providers: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера при создании ноды."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"nodes:select_provider:{uuid}")])
    rows.append([InlineKeyboardButton(text=_("actions.skip_step"), callback_data="nodes:select_provider:none")])
    rows.append(nav_row(NavTarget.NODES_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _node_yes_no_keyboard(action: str, field: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора Да/Нет."""
    rows = [
        [
            InlineKeyboardButton(text=_("node.yes"), callback_data=f"{action}:toggle_{field}:yes"),
            InlineKeyboardButton(text=_("node.no"), callback_data=f"{action}:toggle_{field}:no"),
        ]
    ]
    rows.append(nav_row(NavTarget.NODES_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)




async def _handle_bulk_users_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action", "")
    text = (message.text or "").strip()
    user_id = message.from_user.id

    def _reask(prompt_key: str) -> None:
        PENDING_INPUT[user_id] = ctx
        asyncio.create_task(_send_clean_message(message, _(prompt_key), reply_markup=bulk_users_keyboard()))

    if action == "bulk_users_extend_active":
        try:
            days = int(text)
            if days <= 0:
                _reask("bulk.prompt_extend_active")
                return
        except ValueError:
            _reask("bulk.prompt_extend_active")
            return
        
        try:
            # Получаем всех активных пользователей с пагинацией
            active_uuids: list[str] = []
            start = 0
            while True:
                users_data = await api_client.get_users(start=start, size=SEARCH_PAGE_SIZE)
                payload = users_data.get("response", users_data)
                users = payload.get("users", [])
                total = payload.get("total", len(users))
                
                # Фильтруем активных пользователей
                for user in users:
                    user_info = user.get("response", user)
                    if user_info.get("status") == "ACTIVE" and user_info.get("uuid"):
                        active_uuids.append(user_info.get("uuid"))
                
                start += SEARCH_PAGE_SIZE
                if start >= total or not users:
                    break
            
            if not active_uuids:
                await _send_clean_message(message, _("bulk.no_active_users"), reply_markup=bulk_users_keyboard())
                PENDING_INPUT.pop(user_id, None)
                return
            
            # Продлеваем активным
            await api_client.bulk_extend_users(active_uuids, days)
            result_text = _("bulk.done_extend_active").format(count=len(active_uuids), days=days)
            await _send_clean_message(message, result_text, reply_markup=bulk_users_keyboard())
            PENDING_INPUT.pop(user_id, None)
        except UnauthorizedError:
            await _send_clean_message(message, _("errors.unauthorized"), reply_markup=bulk_users_keyboard())
            PENDING_INPUT.pop(user_id, None)
        except ApiClientError:
            logger.exception("❌ Bulk extend active users failed")
            await _send_clean_message(message, _("bulk.error"), reply_markup=bulk_users_keyboard())
            PENDING_INPUT.pop(user_id, None)
        return

    await _send_clean_message(message, _("errors.generic"), reply_markup=bulk_users_keyboard())
async def _apply_user_update(target: Message | CallbackQuery, user_uuid: str, payload: dict, back_to: str) -> None:
    try:
        await api_client.update_user(user_uuid, **payload)
        user = await api_client.get_user_by_uuid(user_uuid)
        info = user.get("response", user)
        text = _format_user_edit_snapshot(info, _)
        markup = user_edit_keyboard(user_uuid, back_to=back_to)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup)
        else:
            await _send_clean_message(target, text, reply_markup=markup)
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


def _format_user_edit_snapshot(info: dict, t: Callable[[str], str]) -> str:
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

def _get_target_user_id(target: Message | CallbackQuery) -> int | None:
    if isinstance(target, CallbackQuery):
        return target.from_user.id
    return target.from_user.id if getattr(target, "from_user", None) else None


def _clear_user_state(user_id: int | None, keep_search: bool = False, keep_subs: bool = False) -> None:
    if user_id is None:
        return
    PENDING_INPUT.pop(user_id, None)
    if not keep_search:
        USER_SEARCH_CONTEXT.pop(user_id, None)
        USER_DETAIL_BACK_TARGET.pop(user_id, None)
        if not keep_subs:
            SUBS_PAGE_BY_USER.pop(user_id, None)


async def _navigate(target: Message | CallbackQuery, destination: str) -> None:
    user_id = _get_target_user_id(target)
    keep_search = destination in {NavTarget.USER_SEARCH_PROMPT, NavTarget.USER_SEARCH_RESULTS}
    keep_subs = destination == NavTarget.SUBS_LIST
    _clear_user_state(user_id, keep_search=keep_search, keep_subs=keep_subs)

    if destination == NavTarget.MAIN_MENU:
        await _send_clean_message(target, _("bot.menu"), reply_markup=main_menu_keyboard())
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
        await _send_clean_message(target, text, reply_markup=nodes_menu_keyboard())
        return
    if destination == NavTarget.HOSTS_MENU:
        text = await _fetch_hosts_text()
        await _send_clean_message(target, text, reply_markup=nodes_menu_keyboard())
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
    if destination == NavTarget.SUBS_LIST:
        await _send_subscriptions_page(target, page=_get_subs_page(user_id))
        return

    await _send_clean_message(target, _("bot.menu"), reply_markup=main_menu_keyboard())


async def _send_subscriptions_page(target: Message | CallbackQuery, page: int = 0) -> None:
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

    rows.append(nav_row(NavTarget.USERS_MENU))
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    title = _("sub.list_title").format(page=page + 1, pages=total_pages, total=total)
    await _send_clean_message(target, title, reply_markup=keyboard)


async def _start_user_search_flow(target: Message | CallbackQuery, preset_query: str | None = None) -> None:
    user_id = _get_target_user_id(target)
    _clear_user_state(user_id)
    if user_id is not None:
        PENDING_INPUT[user_id] = {"action": "user_search"}
    if preset_query:
        await _run_user_search(target, preset_query)
        return
    await _send_clean_message(target, _("user.search_prompt"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))


async def _handle_user_search_input(message: Message, ctx: dict) -> None:
    query = (message.text or "").strip()
    PENDING_INPUT[message.from_user.id] = {"action": "user_search"}
    if not query:
        await _send_clean_message(message, _("user.search_prompt"), reply_markup=nav_keyboard(NavTarget.USERS_MENU))
        return
    await _run_user_search(message, query)


async def _run_user_search(target: Message | CallbackQuery, query: str) -> None:
    user_id = _get_target_user_id(target)
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
            _("user.search_no_results").format(query=query),
            reply_markup=nav_keyboard(NavTarget.USERS_MENU),
        )
        return

    if len(matches) == 1:
        await _send_user_summary(target, matches[0], back_to=NavTarget.USER_SEARCH_PROMPT)
        return

    await _show_user_search_results(target, query, matches)


async def _show_user_search_results(target: Message | CallbackQuery, query: str, results: list[dict]) -> None:
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

    text = _("user.search_results").format(count=len(results), query=query)
    if extra_line:
        text = f"{text}\\n{extra_line}"
    await _send_clean_message(target, text, reply_markup=keyboard)


async def _search_users(query: str) -> list[dict]:
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


def _user_matches_query(user: dict, normalized_query: str) -> bool:
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


def _truncate(text: str, limit: int = 64) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."

async def _fetch_user(query: str) -> dict:
    if query.isdigit():
        return await api_client.get_user_by_telegram_id(int(query))
    return await api_client.get_user_by_username(query)


def _iso_from_days(days: int) -> str:
    now = datetime.utcnow()
    return (now + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


async def _delete_ctx_message(ctx: dict, bot) -> None:
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


async def _show_squad_selection_for_edit(callback: CallbackQuery, user_uuid: str, back_to: str) -> None:
    """Показывает список сквадов для выбора при редактировании пользователя."""
    squads: list[dict] = []
    try:
        res = await api_client.get_internal_squads()
        squads = res.get("response", {}).get("internalSquads", [])
        logger.info("📥 Loaded %s internal squads for edit user_id=%s", len(squads), callback.from_user.id)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))
        return
    except ApiClientError:
        logger.exception("⚠️ Failed to load internal squads")
    except Exception:
        logger.exception("⚠️ Unexpected error while loading internal squads")

    if not squads:
        try:
            res = await api_client.get_external_squads()
            squads = res.get("response", {}).get("externalSquads", [])
            logger.info("📥 Loaded %s external squads for edit user_id=%s", len(squads), callback.from_user.id)
        except UnauthorizedError:
            await callback.message.edit_text(_("errors.unauthorized"), reply_markup=user_edit_keyboard(user_uuid, back_to=back_to))
            return
        except ApiClientError:
            logger.exception("⚠️ Failed to load external squads")
        except Exception:
            logger.exception("⚠️ Unexpected error while loading external squads")

    if not squads:
        await callback.message.edit_text(
            _("user.squad_load_failed"),
            reply_markup=user_edit_keyboard(user_uuid, back_to=back_to)
        )
        return

    squads_sorted = sorted(squads, key=lambda s: s.get("viewPosition", 0))
    markup = user_edit_squad_keyboard(squads_sorted, user_uuid, back_to=back_to)
    text = _("user.edit_prompt_squad") if squads_sorted else _("user.squad_load_failed")
    await callback.message.edit_text(text, reply_markup=markup)


async def _send_squad_prompt(target: Message | CallbackQuery, ctx: dict) -> None:
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
    except ApiClientError:
        logger.exception("⚠️ Failed to load internal squads")
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
        except ApiClientError:
            logger.exception("⚠️ Failed to load external squads")
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


def _build_user_create_preview(data: dict) -> str:
    expire_at = format_datetime(data.get("expire_at"))
    traffic_limit = data.get("traffic_limit_bytes")
    hwid_limit = data.get("hwid_limit")
    traffic_display = _("user.unlimited") if traffic_limit in (None, 0) else format_bytes(traffic_limit)
    hwid_display = _("user.unlimited") if not hwid_limit else str(hwid_limit)
    telegram_id = data.get("telegram_id") or _("user.not_set")
    description = data.get("description") or _("user.not_set")
    squad = data.get("squad_uuid") or _("user.no_squad")

    return _(
        "user.create_preview"
    ).format(
        username=data.get("username", "n/a"),
        expire=expire_at,
        traffic=traffic_display,
        hwid=hwid_display,
        telegramId=telegram_id,
        description=description,
        squad=squad,
    )


async def _create_user(target: Message | CallbackQuery, data: dict) -> None:
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


async def _handle_user_create_input(message: Message, ctx: dict) -> None:
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


async def _fetch_health_text() -> str:
    try:
        data = await api_client.get_health()
        pm2 = data.get("response", {}).get("pm2Stats", [])
        if not pm2:
            return f"*{_('health.title')}*\n\n{_('health.empty')}"
        lines = [f"*{_('health.title')}*", ""]
        for proc in pm2:
            name = proc.get('name', 'n/a')
            cpu = proc.get('cpu', '—')
            memory = proc.get('memory', '—')
            lines.append(f"  • *{name}*")
            lines.append(f"    CPU: `{cpu}%` | RAM: `{memory}`")
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Health check failed")
        return _("errors.generic")


async def _fetch_panel_stats_text() -> str:
    """Статистика панели (пользователи, ноды, хосты, ресурсы)."""
    try:
        # Получаем основную статистику системы
        data = await api_client.get_stats()
        res = data.get("response", {})
        users = res.get("users", {})
        online = res.get("onlineStats", {})
        nodes = res.get("nodes", {})
        status_counts = users.get("statusCounts", {}) or {}
        status_str = ", ".join(f"`{k}`: *{v}*" for k, v in status_counts.items()) if status_counts else "—"
        
        lines = [
            f"*{_('stats.panel_title')}*",
            "",
            f"*{_('stats.users_section')}*",
            f"  {_('stats.users').format(total=users.get('totalUsers', '—'))}",
            f"  {_('stats.status_counts').format(counts=status_str)}",
            f"  {_('stats.online').format(now=online.get('onlineNow', '—'), day=online.get('lastDay', '—'), week=online.get('lastWeek', '—'))}",
            "",
            f"*{_('stats.infrastructure_section')}*",
            f"  {_('stats.nodes').format(online=nodes.get('totalOnline', '—'))}",
        ]
        
        # Добавляем статистику по хостам
        try:
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            total_hosts = len(hosts)
            enabled_hosts = sum(1 for h in hosts if not h.get("isDisabled"))
            disabled_hosts = total_hosts - enabled_hosts
            lines.append(f"  {_('stats.hosts').format(total=total_hosts, enabled=enabled_hosts, disabled=disabled_hosts)}")
        except Exception:
            lines.append(f"  {_('stats.hosts').format(total='—', enabled='—', disabled='—')}")
        
        # Добавляем статистику по нодам
        try:
            nodes_data = await api_client.get_nodes()
            nodes_list = nodes_data.get("response", [])
            total_nodes = len(nodes_list)
            enabled_nodes = sum(1 for n in nodes_list if not n.get("isDisabled"))
            disabled_nodes = total_nodes - enabled_nodes
            online_nodes = sum(1 for n in nodes_list if n.get("isConnected"))
            lines.append(f"  {_('stats.nodes_detailed').format(total=total_nodes, enabled=enabled_nodes, disabled=disabled_nodes, online=online_nodes)}")
        except Exception:
            lines.append(f"  {_('stats.nodes_detailed').format(total='—', enabled='—', disabled='—', online='—')}")
        
        # Добавляем статистику по ресурсам
        lines.append("")
        lines.append(f"*{_('stats.resources_section')}*")
        try:
            templates_data = await api_client.get_templates()
            templates = templates_data.get("response", {}).get("templates", [])
            lines.append(f"  {_('stats.templates').format(count=len(templates))}")
        except Exception:
            lines.append(f"  {_('stats.templates').format(count='—')}")
        
        try:
            tokens_data = await api_client.get_tokens()
            tokens = tokens_data.get("response", {}).get("apiKeys", [])
            lines.append(f"  {_('stats.tokens').format(count=len(tokens))}")
        except Exception:
            lines.append(f"  {_('stats.tokens').format(count='—')}")
        
        try:
            snippets_data = await api_client.get_snippets()
            snippets = snippets_data.get("response", {}).get("snippets", [])
            lines.append(f"  {_('stats.snippets').format(count=len(snippets))}")
        except Exception:
            lines.append(f"  {_('stats.snippets').format(count='—')}")
        
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Panel stats fetch failed")
        return _("errors.generic")


async def _fetch_server_stats_text() -> str:
    """Статистика сервера (CPU, RAM, нагрузка, системная информация)."""
    try:
        data = await api_client.get_stats()
        res = data.get("response", {})
        mem = res.get("memory", {})
        cpu = res.get("cpu", {})
        uptime = res.get("uptime", 0)
        
        # Вычисляем использование памяти в процентах
        mem_total = mem.get("total", 0)
        mem_used = mem.get("used", 0)
        mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0
        
        # Получаем дополнительную информацию о системе
        cpu_usage = cpu.get("usage")
        cpu_load = cpu.get("loadAverage") or cpu.get("load")
        
        lines = [
            f"*{_('stats.server_title')}*",
            "",
            f"*{_('stats.system_section')}*",
            f"  {_('stats.uptime').format(uptime=format_uptime(uptime))}",
            "",
            f"*{_('stats.cpu_section')}*",
            f"  {_('stats.cpu').format(cores=cpu.get('cores', '—'), physical=cpu.get('physicalCores', '—'))}",
        ]
        
        if cpu_usage is not None:
            try:
                usage_val = float(cpu_usage) if isinstance(cpu_usage, (int, float, str)) else cpu_usage
                if isinstance(usage_val, (int, float)):
                    lines.append(f"  {_('stats.cpu_usage').format(usage=f'{usage_val:.1f}')}")
                else:
                    lines.append(f"  {_('stats.cpu_usage').format(usage=cpu_usage)}")
            except (ValueError, TypeError):
                pass
        
        if cpu_load:
            try:
                if isinstance(cpu_load, list):
                    load_str = ", ".join(f"`{float(load):.2f}`" for load in cpu_load[:3] if load is not None)
                    if load_str:
                        lines.append(f"  {_('stats.cpu_load').format(load=load_str)}")
                elif isinstance(cpu_load, (int, float)):
                    lines.append(f"  {_('stats.cpu_load').format(load=f'`{float(cpu_load):.2f}`')}")
            except (ValueError, TypeError):
                pass
        
        lines.append("")
        lines.append(f"*{_('stats.memory_section')}*")
        lines.append(f"  {_('stats.memory').format(used=format_bytes(mem_used), total=format_bytes(mem_total))}")
        lines.append(f"  {_('stats.memory_percent').format(percent=f'{mem_percent:.1f}%')}")
        
        mem_free = mem_total - mem_used
        if mem_free > 0:
            lines.append(f"  {_('stats.memory_free').format(free=format_bytes(mem_free))}")
        
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Server stats fetch failed")
        return _("errors.generic")


async def _fetch_stats_text() -> str:
    try:
        # Получаем основную статистику системы
        data = await api_client.get_stats()
        res = data.get("response", {})
        mem = res.get("memory", {})
        cpu = res.get("cpu", {})
        users = res.get("users", {})
        online = res.get("onlineStats", {})
        nodes = res.get("nodes", {})
        status_counts = users.get("statusCounts", {}) or {}
        status_str = ", ".join(f"`{k}`: *{v}*" for k, v in status_counts.items()) if status_counts else "—"
        
        lines = [
            f"*{_('stats.title')}*",
            "",
            f"*{_('stats.system_section')}*",
            f"  {_('stats.uptime').format(uptime=format_uptime(res.get('uptime')))}",
            f"  {_('stats.cpu').format(cores=cpu.get('cores', '—'), physical=cpu.get('physicalCores', '—'))}",
            f"  {_('stats.memory').format(used=format_bytes(mem.get('used')), total=format_bytes(mem.get('total')))}",
            "",
            f"*{_('stats.users_section')}*",
            f"  {_('stats.users').format(total=users.get('totalUsers', '—'))}",
            f"  {_('stats.status_counts').format(counts=status_str)}",
            f"  {_('stats.online').format(now=online.get('onlineNow', '—'), day=online.get('lastDay', '—'), week=online.get('lastWeek', '—'))}",
            "",
            f"*{_('stats.infrastructure_section')}*",
            f"  {_('stats.nodes').format(online=nodes.get('totalOnline', '—'))}",
        ]
        
        # Добавляем статистику по хостам
        try:
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            total_hosts = len(hosts)
            enabled_hosts = sum(1 for h in hosts if not h.get("isDisabled"))
            disabled_hosts = total_hosts - enabled_hosts
            lines.append(f"  {_('stats.hosts').format(total=total_hosts, enabled=enabled_hosts, disabled=disabled_hosts)}")
        except Exception:
            lines.append(f"  {_('stats.hosts').format(total='—', enabled='—', disabled='—')}")
        
        # Добавляем статистику по нодам
        try:
            nodes_data = await api_client.get_nodes()
            nodes_list = nodes_data.get("response", [])
            total_nodes = len(nodes_list)
            enabled_nodes = sum(1 for n in nodes_list if not n.get("isDisabled"))
            disabled_nodes = total_nodes - enabled_nodes
            online_nodes = sum(1 for n in nodes_list if n.get("isConnected"))
            lines.append(f"  {_('stats.nodes_detailed').format(total=total_nodes, enabled=enabled_nodes, disabled=disabled_nodes, online=online_nodes)}")
        except Exception:
            lines.append(f"  {_('stats.nodes_detailed').format(total='—', enabled='—', disabled='—', online='—')}")
        
        # Добавляем статистику по ресурсам
        lines.append("")
        lines.append(f"*{_('stats.resources_section')}*")
        try:
            templates_data = await api_client.get_templates()
            templates = templates_data.get("response", {}).get("templates", [])
            lines.append(f"  {_('stats.templates').format(count=len(templates))}")
        except Exception:
            lines.append(f"  {_('stats.templates').format(count='—')}")
        
        try:
            tokens_data = await api_client.get_tokens()
            tokens = tokens_data.get("response", {}).get("apiKeys", [])
            lines.append(f"  {_('stats.tokens').format(count=len(tokens))}")
        except Exception:
            lines.append(f"  {_('stats.tokens').format(count='—')}")
        
        try:
            snippets_data = await api_client.get_snippets()
            snippets = snippets_data.get("response", {}).get("snippets", [])
            lines.append(f"  {_('stats.snippets').format(count=len(snippets))}")
        except Exception:
            lines.append(f"  {_('stats.snippets').format(count='—')}")
        
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Stats fetch failed")
        return _("errors.generic")


async def _fetch_bandwidth_text() -> str:
    try:
        data = await api_client.get_bandwidth_stats()
        return build_bandwidth_stats(data, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Bandwidth fetch failed")
        return _("errors.generic")


async def _fetch_billing_text() -> str:
    try:
        data = await api_client.get_infra_billing_history()
        records = data.get("response", {}).get("records", [])
        return build_billing_history(records, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing fetch failed")
        return _("errors.generic")


async def _fetch_providers_text() -> str:
    try:
        data = await api_client.get_infra_providers()
        providers = data.get("response", {}).get("providers", [])
        return build_infra_providers(providers, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Providers fetch failed")
        return _("errors.generic")


async def _fetch_billing_nodes_text() -> str:
    try:
        data = await api_client.get_infra_billing_nodes()
        return build_billing_nodes(data, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing nodes fetch failed")
        return _("errors.generic")


async def _fetch_billing_stats_text() -> str:
    """Статистика по биллингу (история платежей)."""
    try:
        data = await api_client.get_infra_billing_history()
        records = data.get("response", {}).get("records", [])
        
        if not records:
            return f"*{_('billing.stats_title')}*\n\n{_('billing.empty')}"
        
        # Вычисляем статистику
        total_amount = sum(float(rec.get("amount", 0)) for rec in records)
        total_records = len(records)
        
        # Группируем по провайдерам
        by_provider: dict[str, dict] = {}
        for rec in records:
            provider = rec.get("provider", {})
            provider_name = provider.get("name", "Unknown")
            amount = float(rec.get("amount", 0))
            if provider_name not in by_provider:
                by_provider[provider_name] = {"count": 0, "amount": 0.0}
            by_provider[provider_name]["count"] += 1
            by_provider[provider_name]["amount"] += amount
        
        # Сортируем по сумме
        sorted_providers = sorted(by_provider.items(), key=lambda x: x[1]["amount"], reverse=True)
        
        lines = [
            f"*{_('billing.stats_title')}*",
            "",
            f"*{_('billing.stats_summary')}*",
            f"  {_('billing.stats_total_amount').format(amount=f'*{total_amount:.2f}*')}",
            f"  {_('billing.stats_total_records').format(count=f'*{total_records}*')}",
            "",
            f"*{_('billing.stats_by_provider')}*",
        ]
        
        for provider_name, stats in sorted_providers[:10]:
            lines.append(
                f"  • *{provider_name}*: `{stats['count']}` записей, сумма `{stats['amount']:.2f}`"
            )
        
        if len(sorted_providers) > 10:
            lines.append("")
            lines.append(_("billing.more").format(count=len(sorted_providers) - 10))
        
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing stats fetch failed")
        return _("errors.generic")


async def _fetch_billing_nodes_stats_text() -> str:
    """Статистика по биллингу нод."""
    try:
        data = await api_client.get_infra_billing_nodes()
        resp = data.get("response", data) or {}
        nodes = resp.get("billingNodes", []) or []
        stats = resp.get("stats", {}) or {}
        
        if not nodes:
            return f"*{_('billing_nodes.stats_title')}*\n\n{_('billing_nodes.empty')}"
        
        # Группируем по провайдерам
        by_provider: dict[str, dict] = {}
        upcoming_count = 0
        from datetime import datetime
        
        for item in nodes:
            provider = item.get("provider", {})
            provider_name = provider.get("name", "Unknown")
            if provider_name not in by_provider:
                by_provider[provider_name] = {"count": 0}
            by_provider[provider_name]["count"] += 1
            
            # Проверяем ближайшие платежи (в течение 7 дней)
            next_billing = item.get("nextBillingAt")
            if next_billing:
                try:
                    billing_date = datetime.fromisoformat(next_billing.replace("Z", "+00:00"))
                    days_until = (billing_date - datetime.now(billing_date.tzinfo)).days
                    if 0 <= days_until <= 7:
                        upcoming_count += 1
                except Exception:
                    pass
        
        upcoming_val = stats.get("upcomingNodesCount", upcoming_count)
        month_val = stats.get("currentMonthPayments", "—")
        total_val = stats.get("totalSpent", "—")
        
        lines = [
            f"*{_('billing_nodes.stats_title')}*",
            "",
            f"*{_('billing_nodes.stats_summary')}*",
            f"  {_('billing_nodes.stats_text').format(upcoming=f'*{upcoming_val}*', month=f'`{month_val}`', total=f'*{total_val}*')}",
            "",
            f"*{_('billing_nodes.stats_by_provider')}*",
        ]
        
        # Сортируем по количеству нод
        sorted_providers = sorted(by_provider.items(), key=lambda x: x[1]["count"], reverse=True)
        for provider_name, provider_stats in sorted_providers[:10]:
            lines.append(f"  • *{provider_name}*: `{provider_stats['count']}` нод")
        
        if len(sorted_providers) > 10:
            lines.append("")
            lines.append(_("billing_nodes.more").format(count=len(sorted_providers) - 10))
        
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing nodes stats fetch failed")
        return _("errors.generic")


async def _fetch_nodes_text() -> str:
    try:
        data = await api_client.get_nodes()
        nodes = data.get("response", [])
        if not nodes:
            return _("node.list_empty")
        sorted_nodes = sorted(nodes, key=lambda n: n.get("viewPosition", 0))
        lines = [_("node.list_title").format(total=len(nodes))]
        for node in sorted_nodes[:10]:
            status = "DISABLED" if node.get("isDisabled") else ("ONLINE" if node.get("isConnected") else "OFFLINE")
            status_emoji = "🟢" if status == "ONLINE" else ("🟡" if status == "DISABLED" else "🔴")
            address = f"{node.get('address', 'n/a')}:{node.get('port') or '—'}"
            users_online = node.get("usersOnline", "—")
            line = _(
                "node.list_item"
            ).format(
                statusEmoji=status_emoji,
                name=node.get("name", "n/a"),
                address=address,
                users=users_online,
                traffic=format_bytes(node.get("trafficUsedBytes")),
            )
            lines.append(line)
        if len(nodes) > 10:
            lines.append(_("node.list_more").format(count=len(nodes) - 10))
        lines.append(_("node.list_hint"))
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Nodes fetch failed")
        return _("errors.generic")


async def _fetch_nodes_realtime_text() -> str:
    try:
        data = await api_client.get_nodes_realtime_usage()
        usages = data.get("response", [])
        return build_nodes_realtime_usage(usages, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Nodes realtime fetch failed")
        return _("errors.generic")


async def _fetch_nodes_range_text(start: str, end: str) -> str:
    try:
        data = await api_client.get_nodes_usage_range(start, end)
        usages = data.get("response", [])
        return build_nodes_usage_range(usages, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Nodes range fetch failed")
        return _("errors.generic")


async def _fetch_configs_text() -> str:
    try:
        data = await api_client.get_config_profiles()
        profiles = data.get("response", {}).get("configProfiles", [])
        return build_config_profiles_list(profiles, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Config profiles fetch failed")
        return _("errors.generic")


async def _send_config_detail(target: Message | CallbackQuery, config_uuid: str) -> None:
    try:
        profile = await api_client.get_config_profile_computed(config_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        text = _("config.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("⚠️ Config profile fetch failed")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    summary = build_config_profile_detail(profile, _)
    keyboard = config_actions_keyboard(config_uuid)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await _send_clean_message(target, summary, reply_markup=keyboard)


async def _fetch_hosts_text() -> str:
    try:
        data = await api_client.get_hosts()
        hosts = data.get("response", [])
        if not hosts:
            return _("host.list_empty")
        sorted_hosts = sorted(hosts, key=lambda h: h.get("viewPosition", 0))
        lines = [_("host.list_title").format(total=len(hosts))]
        for host in sorted_hosts[:10]:
            status = "DISABLED" if host.get("isDisabled") else "ENABLED"
            status_emoji = "🟡" if status == "DISABLED" else "🟢"
            address = f"{host.get('address', 'n/a')}:{host.get('port', '—')}"
            remark = host.get("remark", "—")
            line = _(
                "host.list_item"
            ).format(
                statusEmoji=status_emoji,
                remark=remark,
                address=address,
                tag=host.get("tag", "—"),
            )
            lines.append(line)
        if len(hosts) > 10:
            lines.append(_("host.list_more").format(count=len(hosts) - 10))
        lines.append(_("host.list_hint"))
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Hosts fetch failed")
        return _("errors.generic")


async def _fetch_tokens_text() -> str:
    try:
        data = await api_client.get_tokens()
        tokens = data.get("response", {}).get("apiKeys", [])
        return build_tokens_list(tokens, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Tokens fetch failed")
        return _("errors.generic")


async def _fetch_templates_text() -> str:
    try:
        data = await api_client.get_templates()
        templates = data.get("response", {}).get("templates", [])
        return build_templates_list(templates, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Templates fetch failed")
        return _("errors.generic")


async def _edit_text_safe(message: Message, text: str, reply_markup=None, parse_mode: str | None = None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc):
            return
        raise


async def _send_templates(target: Message | CallbackQuery) -> None:
    text = await _fetch_templates_text()
    try:
        data = await api_client.get_templates()
        templates = data.get("response", {}).get("templates", [])
    except Exception:
        templates = []
    keyboard = template_list_keyboard(templates)
    if isinstance(target, CallbackQuery):
        await _edit_text_safe(target.message, text, reply_markup=keyboard)
    else:
        await _send_clean_message(target, text, reply_markup=keyboard)


async def _fetch_snippets_text() -> str:
    try:
        data = await api_client.get_snippets()
        snippets = data.get("response", {}).get("snippets", [])
        return build_snippets_list(snippets, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Snippets fetch failed")
        return _("errors.generic")


async def _send_snippet_detail(target: Message | CallbackQuery, name: str) -> None:
    try:
        data = await api_client.get_snippets()
        snippets = data.get("response", {}).get("snippets", [])
        snippet = next((s for s in snippets if s.get("name") == name), None)
        if not snippet:
            raise NotFoundError()
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await _edit_text_safe(target.message, text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        text = _("snippet.not_found")
        if isinstance(target, CallbackQuery):
            await _edit_text_safe(target.message, text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("⚠️ API client error while fetching snippet")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await _edit_text_safe(target.message, text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    summary = build_snippet_detail(snippet, _)
    keyboard = snippet_actions_keyboard(name)
    if isinstance(target, CallbackQuery):
        await _edit_text_safe(target.message, summary, reply_markup=keyboard)
    else:
        await _send_clean_message(target, summary, reply_markup=keyboard)


async def _upsert_snippet(target: Message, action: str) -> None:
    parts = target.text.split(maxsplit=2)
    if len(parts) < 3:
        await _send_clean_message(target, _("snippet.usage"))
        return
    name = parts[1].strip()
    raw_json = parts[2].strip()
    try:
        import json

        snippet_body = json.loads(raw_json)
    except Exception:
        await _send_clean_message(target, _("snippet.invalid_json"))
        return

    try:
        if action == "create":
            res = await api_client.create_snippet(name, snippet_body)
        else:
            res = await api_client.update_snippet(name, snippet_body)
    except UnauthorizedError:
        await _send_clean_message(target, _("errors.unauthorized"))
        return
    except ApiClientError:
        logger.exception("❌ Snippet %s failed", action)
        await _send_clean_message(target, _("errors.generic"))
        return

    # Return detail
    content = res.get("response", res).get("snippet", snippet_body)
    detail = build_snippet_detail({"name": name, "snippet": content}, _)
    await _send_clean_message(target, detail, reply_markup=snippet_actions_keyboard(name))


async def _create_token(target: Message | CallbackQuery, name: str) -> None:
    try:
        token = await api_client.create_token(name)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("❌ Create token failed")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    summary = build_created_token(token, _)
    token_uuid = token.get("response", token).get("uuid", "")
    keyboard = token_actions_keyboard(token_uuid)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await _send_clean_message(target, summary, reply_markup=keyboard)


async def _show_tokens(
    target: Message | CallbackQuery, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    text = await _fetch_tokens_text()
    markup = reply_markup or main_menu_keyboard()
    if isinstance(target, CallbackQuery):
        await _edit_text_safe(target.message, text, reply_markup=markup)
    else:
        await _send_clean_message(target, text, reply_markup=markup)
async def _send_clean_message(
    target: Message | CallbackQuery,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = None,
) -> Message:
    msg = target.message if isinstance(target, CallbackQuery) else target
    bot = msg.bot
    chat_id = msg.chat.id

    prev_id = LAST_BOT_MESSAGES.get(chat_id)
    if prev_id:
        try:
            edited = await bot.edit_message_text(
                chat_id=chat_id, message_id=prev_id, text=text, reply_markup=reply_markup, parse_mode=parse_mode
            )
            return edited
        except Exception:
            try:
                await bot.delete_message(chat_id=chat_id, message_id=prev_id)
            except Exception:
                pass

    sent = await msg.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
    LAST_BOT_MESSAGES[chat_id] = sent.message_id
    return sent
