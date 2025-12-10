from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _
from datetime import datetime, timedelta

from src.keyboards.main_menu import (
    main_menu_keyboard,
    system_menu_keyboard,
    users_menu_keyboard,
    nodes_menu_keyboard,
    resources_menu_keyboard,
    billing_overview_keyboard,
    bulk_menu_keyboard,
)
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
from src.keyboards.template_menu import template_menu_keyboard
from src.keyboards.bulk_hosts import bulk_hosts_keyboard
from src.keyboards.bulk_nodes import bulk_nodes_keyboard
from src.keyboards.subscription_actions import subscription_keyboard
from src.keyboards.user_actions import user_actions_keyboard
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
)
from src.utils.logger import logger

router = Router(name="basic")
PENDING_INPUT: dict[int, dict] = {}


async def _not_admin(message: Message | CallbackQuery) -> bool:
    user_id = message.from_user.id if hasattr(message, "from_user") else None
    if user_id is None or not is_admin(user_id):
        text = _("errors.unauthorized")
        if isinstance(message, CallbackQuery):
            await message.answer(text, show_alert=True)
        else:
            await message.answer(text)
        return True
    return False


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    if await _not_admin(message):
        return

    await message.answer(_("bot.welcome"))
    await message.answer(_("bot.menu"), reply_markup=main_menu_keyboard())


@router.message(F.text & ~F.text.startswith("/"))
async def handle_pending(message: Message) -> None:
    if await _not_admin(message):
        return
    user_id = message.from_user.id
    if user_id not in PENDING_INPUT:
        return
    ctx = PENDING_INPUT.pop(user_id)
    action = ctx.get("action")
    if action == "template_create":
        await _handle_template_create_input(message, ctx)
    elif action == "template_update_json":
        await _handle_template_update_json_input(message, ctx)
    elif action == "template_reorder":
        await _handle_template_reorder_input(message, ctx)
    elif action.startswith("bulk_hosts_"):
        await _handle_bulk_hosts_input(message, ctx)
    elif action.startswith("bulk_nodes_"):
        await _handle_bulk_nodes_input(message, ctx)
    elif action.startswith("provider_"):
        await _handle_provider_input(message, ctx)
    elif action.startswith("billing_history_"):
        await _handle_billing_history_input(message, ctx)
    elif action.startswith("billing_nodes_"):
        await _handle_billing_nodes_input(message, ctx)
    elif action == "user_create":
        await _handle_user_create_input(message, ctx)
    else:
        await message.answer(_("errors.generic"))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if await _not_admin(message):
        return

    await message.answer(_("bot.help"))


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    if await _not_admin(message):
        return
    await message.answer(await _fetch_health_text(), reply_markup=system_menu_keyboard())


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if await _not_admin(message):
        return
    await message.answer(await _fetch_stats_text(), reply_markup=system_menu_keyboard())


@router.message(Command("bandwidth"))
async def cmd_bandwidth(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_bandwidth_text()
    await message.answer(text, reply_markup=system_menu_keyboard())


@router.message(Command("billing"))
async def cmd_billing(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_billing_text()
    await message.answer(text, reply_markup=billing_menu_keyboard())


@router.message(Command("providers"))
async def cmd_providers(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_providers_text()
    await message.answer(text, reply_markup=providers_menu_keyboard())


@router.message(Command("billing_nodes"))
async def cmd_billing_nodes(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_billing_nodes_text()
    await message.answer(text, reply_markup=billing_nodes_menu_keyboard())


@router.message(Command("bulk"))
async def cmd_bulk(message: Message) -> None:
    if await _not_admin(message):
        return
    await message.answer(_("bulk.title"), reply_markup=bulk_menu_keyboard())


@router.message(Command("bulk_delete_status"))
async def cmd_bulk_delete_status(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("bulk.usage_delete_status"))
        return
    status = parts[1].strip()
    await _run_bulk_action(message, action="delete_status", status=status)


@router.message(Command("bulk_delete"))
async def cmd_bulk_delete(message: Message) -> None:
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await message.answer(_("bulk.usage_delete"))
        return
    await _run_bulk_action(message, action="delete", uuids=uuids)


@router.message(Command("bulk_revoke"))
async def cmd_bulk_revoke(message: Message) -> None:
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await message.answer(_("bulk.usage_revoke"))
        return
    await _run_bulk_action(message, action="revoke", uuids=uuids)


@router.message(Command("bulk_reset"))
async def cmd_bulk_reset(message: Message) -> None:
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await message.answer(_("bulk.usage_reset"))
        return
    await _run_bulk_action(message, action="reset", uuids=uuids)


@router.message(Command("bulk_extend"))
async def cmd_bulk_extend(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(_("bulk.usage_extend"))
        return
    try:
        days = int(parts[1])
    except ValueError:
        await message.answer(_("bulk.usage_extend"))
        return
    uuids = parts[2:]
    if not uuids:
        await message.answer(_("bulk.usage_extend"))
        return
    await _run_bulk_action(message, action="extend", uuids=uuids, days=days)


@router.message(Command("bulk_extend_all"))
async def cmd_bulk_extend_all(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split()
    if len(parts) != 2:
        await message.answer(_("bulk.usage_extend_all"))
        return
    try:
        days = int(parts[1])
    except ValueError:
        await message.answer(_("bulk.usage_extend_all"))
        return
    await _run_bulk_action(message, action="extend_all", days=days)


@router.message(Command("bulk_status"))
async def cmd_bulk_status(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer(_("bulk.usage_status"))
        return
    status = parts[1]
    uuids = parts[2:]
    await _run_bulk_action(message, action="status", status=status, uuids=uuids)


@router.message(Command("user"))
async def cmd_user(message: Message) -> None:
    if await _not_admin(message):
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("bot.user_usage"))
        return
    query = parts[1].strip()
    await _send_user_detail(message, query)


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
    PENDING_INPUT[user_id] = {"action": "user_create", "stage": "username", "data": {}}
    await _send_user_create_prompt(message, _("user.prompt_username"))


@router.message(Command("nodes"))
async def cmd_nodes(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_nodes_text()
    await message.answer(text, reply_markup=nodes_menu_keyboard())


@router.message(Command("nodes_usage"))
async def cmd_nodes_usage(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_nodes_realtime_text()
    await message.answer(text, reply_markup=nodes_menu_keyboard())


@router.message(Command("nodes_range"))
async def cmd_nodes_range(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(_("node_stats.usage_range_usage"))
        return
    start, end = parts[1], parts[2]
    text = await _fetch_nodes_range_text(start, end)
    await message.answer(text, reply_markup=nodes_menu_keyboard())


@router.message(Command("node"))
async def cmd_node(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("node.usage"))
        return
    node_uuid = parts[1].strip()
    await _send_node_detail(message, node_uuid)


@router.message(Command("hosts"))
async def cmd_hosts(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_hosts_text()
    await message.answer(text, reply_markup=nodes_menu_keyboard())


@router.message(Command("host"))
async def cmd_host(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("host.usage"))
        return
    host_uuid = parts[1].strip()
    await _send_host_detail(message, host_uuid)


@router.message(Command("sub"))
async def cmd_sub(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("sub.usage"))
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
        await message.answer(_("token.usage"))
        return
    name = parts[1].strip()
    await _create_token(message, name)


@router.message(Command("templates"))
async def cmd_templates(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_templates_text()
    await message.answer(text, reply_markup=template_menu_keyboard())


@router.message(Command("template"))
async def cmd_template(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("template.usage"))
        return
    tpl_uuid = parts[1].strip()
    await _send_template_detail(message, tpl_uuid)


@router.message(Command("snippets"))
async def cmd_snippets(message: Message) -> None:
    if await _not_admin(message):
        return
    text = await _fetch_snippets_text()
    await message.answer(text, reply_markup=resources_menu_keyboard())


@router.message(Command("snippet"))
async def cmd_snippet(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("snippet.usage"))
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
    await message.answer(text, reply_markup=nodes_menu_keyboard())


@router.message(Command("config"))
async def cmd_config(message: Message) -> None:
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(_("config.usage"))
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
    logger.info("User create flow started by user_id=%s", callback.from_user.id)
    PENDING_INPUT[callback.from_user.id] = {"action": "user_create", "stage": "username", "data": {}}
    await _send_user_create_prompt(callback, _("user.prompt_username"))


@router.callback_query(F.data.startswith("user_create:"))
async def cb_user_create_flow(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    logger.info("User create callback action=%s user_id=%s", callback.data, callback.from_user.id)
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
    await callback.message.edit_text(text, reply_markup=system_menu_keyboard())


@router.callback_query(F.data == "menu:stats")
async def cb_stats(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_stats_text()
    await callback.message.edit_text(text, reply_markup=system_menu_keyboard())


@router.callback_query(F.data == "menu:find_user")
async def cb_find_user(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.user_usage"), reply_markup=users_menu_keyboard())


@router.callback_query(F.data == "menu:nodes")
async def cb_nodes(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_nodes_text()
    await callback.message.edit_text(text, reply_markup=nodes_menu_keyboard())


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
    await callback.message.edit_text(_("sub.usage"), reply_markup=users_menu_keyboard())


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
    text = await _fetch_templates_text()
    await callback.message.edit_text(text, reply_markup=template_menu_keyboard())


@router.callback_query(F.data == "menu:snippets")
async def cb_snippets(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_snippets_text()
    await callback.message.edit_text(text, reply_markup=resources_menu_keyboard())


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
    await callback.message.edit_text(text, reply_markup=providers_menu_keyboard())


@router.callback_query(F.data == "menu:billing")
async def cb_billing(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_billing_text()
    await callback.message.edit_text(text, reply_markup=billing_menu_keyboard())


@router.callback_query(F.data == "menu:billing_nodes")
async def cb_billing_nodes(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_billing_nodes_text()
    await callback.message.edit_text(text, reply_markup=billing_nodes_menu_keyboard())


@router.callback_query(F.data == "menu:bulk_hosts")
async def cb_bulk_hosts(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bulk_hosts.title"), reply_markup=bulk_hosts_keyboard())


@router.callback_query(F.data == "menu:bulk_nodes")
async def cb_bulk_nodes(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bulk_nodes.title"), reply_markup=bulk_nodes_keyboard())


@router.callback_query(F.data == "menu:bulk_users")
async def cb_bulk_users(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bulk.title"), reply_markup=bulk_users_keyboard())


@router.callback_query(F.data.startswith("providers:"))
async def cb_providers_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    action = callback.data.split(":")[-1]
    if action == "create":
        PENDING_INPUT[callback.from_user.id] = {"action": "provider_create"}
        await callback.message.edit_text(_("provider.prompt_create"), reply_markup=providers_menu_keyboard())
    elif action == "update":
        PENDING_INPUT[callback.from_user.id] = {"action": "provider_update"}
        await callback.message.edit_text(_("provider.prompt_update"), reply_markup=providers_menu_keyboard())
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
    action = callback.data.split(":")[-1]
    if action == "create":
        PENDING_INPUT[callback.from_user.id] = {"action": "billing_history_create"}
        await callback.message.edit_text(_("billing.prompt_create"), reply_markup=billing_menu_keyboard())
    elif action == "delete":
        PENDING_INPUT[callback.from_user.id] = {"action": "billing_history_delete"}
        await callback.message.edit_text(_("billing.prompt_delete"), reply_markup=billing_menu_keyboard())
    else:
        await callback.message.edit_text(_("errors.generic"), reply_markup=billing_menu_keyboard())


@router.callback_query(F.data.startswith("billing_nodes:"))
async def cb_billing_nodes_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    action = callback.data.split(":")[-1]
    if action == "create":
        PENDING_INPUT[callback.from_user.id] = {"action": "billing_nodes_create"}
        await callback.message.edit_text(_("billing_nodes.prompt_create"), reply_markup=billing_nodes_menu_keyboard())
    elif action == "update":
        PENDING_INPUT[callback.from_user.id] = {"action": "billing_nodes_update"}
        await callback.message.edit_text(_("billing_nodes.prompt_update"), reply_markup=billing_nodes_menu_keyboard())
    elif action == "delete":
        PENDING_INPUT[callback.from_user.id] = {"action": "billing_nodes_delete"}
        await callback.message.edit_text(_("billing_nodes.prompt_delete"), reply_markup=billing_nodes_menu_keyboard())
    else:
        await callback.message.edit_text(_("errors.generic"), reply_markup=billing_nodes_menu_keyboard())


@router.callback_query(F.data == "menu:back")
async def cb_back(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    await callback.message.edit_text(_("bot.menu"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("user:"))
async def cb_user_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _, user_uuid, action = callback.data.split(":")
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
        await callback.message.edit_text(summary, reply_markup=user_actions_keyboard(user_uuid, status))
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("user.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("User action failed: %s", action)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("node:"))
async def cb_node_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _, node_uuid, action = callback.data.split(":")
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
        logger.exception("Node action failed: %s", action)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("host:"))
async def cb_host_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _, host_uuid, action = callback.data.split(":")
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
        logger.exception("Host action failed: %s", action)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("token:"))
async def cb_token_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _, token_uuid, action = callback.data.split(":")
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
        logger.exception("Token action failed: %s", action)
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

    _, tpl_uuid, action = parts
    try:
        if action == "delete":
            await api_client.delete_template(tpl_uuid)
            await callback.message.edit_text(_("template.deleted"), reply_markup=main_menu_keyboard())
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
        logger.exception("Template action failed: %s", action)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("snippet:"))
async def cb_snippet_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _, name, action = callback.data.split(":")
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
        logger.exception("Snippet action failed: %s", action)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("bulk:users:"))
async def cb_bulk_users_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[2] if len(parts) > 2 else None
    if action == "usage":
        await callback.message.edit_text(
            "\n".join(
                [
                    _("bulk.title"),
                    _("bulk.usage_delete_status"),
                    _("bulk.usage_delete"),
                    _("bulk.usage_revoke"),
                    _("bulk.usage_reset"),
                    _("bulk.usage_extend"),
                    _("bulk.usage_extend_all"),
                    _("bulk.usage_status"),
                ]
            ),
            reply_markup=bulk_users_keyboard(),
        )
        return
    try:
        if action == "reset":
            await api_client.bulk_reset_traffic_all_users()
        elif action == "delete" and len(parts) > 3:
            status = parts[3]
            await api_client.bulk_delete_users_by_status(status)
        elif action == "extend_all" and len(parts) > 3:
            try:
                days = int(parts[3])
            except ValueError:
                await callback.message.edit_text(_("bulk.usage_extend_all"), reply_markup=bulk_users_keyboard())
                return
            await api_client.bulk_extend_all_users(days)
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
        await callback.message.edit_text(_("bulk.done"), reply_markup=main_menu_keyboard())
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("Bulk users action failed: %s", action)
        await callback.message.edit_text(_("bulk.error"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("bulk:prompt:"))
async def cb_bulk_prompt(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    key = callback.data.split(":")[-1]
    prompt_map = {
        "delete": _("bulk.usage_delete"),
        "revoke": _("bulk.usage_revoke"),
        "reset": _("bulk.usage_reset"),
        "extend": _("bulk.usage_extend"),
        "status": _("bulk.usage_status"),
    }
    text = "\n".join([_("bulk.title"), prompt_map.get(key, _("errors.generic"))])
    await callback.message.edit_text(text, reply_markup=bulk_users_keyboard())


@router.callback_query(F.data.startswith("bulk:hosts:"))
async def cb_bulk_hosts_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    action = callback.data.split(":")[-1]
    if action == "prompt":
        await callback.message.edit_text(_("bulk_hosts.prompt"), reply_markup=bulk_hosts_keyboard())
        return
    # Expect user to send UUIDs next
    PENDING_INPUT[callback.from_user.id] = {"action": f"bulk_hosts_{action}"}
    await callback.message.edit_text(_("bulk_hosts.usage"), reply_markup=bulk_hosts_keyboard())


@router.callback_query(F.data.startswith("bulk:nodes:"))
async def cb_bulk_nodes_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    action = callback.data.split(":")[-1]
    if action == "profile":
        PENDING_INPUT[callback.from_user.id] = {"action": "bulk_nodes_profile", "stage": "profile"}
        await callback.message.edit_text(_("bulk_nodes.prompt_profile"), reply_markup=bulk_nodes_keyboard())
    else:
        await callback.message.edit_text(_("errors.generic"), reply_markup=bulk_nodes_keyboard())


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
        await _reply(target, _("bulk.done"), back=True)
    except UnauthorizedError:
        await _reply(target, _("errors.unauthorized"))
    except ApiClientError:
        logger.exception("Bulk users action failed: %s", action)
        await _reply(target, _("bulk.error"))


async def _reply(target: Message | CallbackQuery, text: str, back: bool = False) -> None:
    markup = main_menu_keyboard() if back else None
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("config:"))
async def cb_config_actions(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()
    _, config_uuid, action = callback.data.split(":")
    if action != "view":
        await callback.answer(_("errors.generic"), show_alert=True)
        return
    await _send_config_detail(callback, config_uuid)


# Helpers
async def _send_user_detail(target: Message | CallbackQuery, query: str) -> None:
    try:
        user = await _fetch_user(query)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except NotFoundError:
        text = _("user.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("API client error while fetching user")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    summary = build_user_summary(user, _)
    status = user.get("response", user).get("status", "UNKNOWN")
    uuid = user.get("response", user).get("uuid")
    reply_markup = user_actions_keyboard(uuid, status)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=reply_markup)
    else:
        await target.answer(summary, reply_markup=reply_markup)


async def _send_node_detail(target: Message | CallbackQuery, node_uuid: str, from_callback: bool = False) -> None:
    try:
        node = await api_client.get_node(node_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except NotFoundError:
        text = _("node.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("API client error while fetching node")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    info = node.get("response", node)
    summary = build_node_summary(node, _)
    is_disabled = bool(info.get("isDisabled"))
    keyboard = node_actions_keyboard(info.get("uuid", node_uuid), is_disabled)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await target.answer(summary, reply_markup=keyboard)


async def _send_host_detail(target: Message | CallbackQuery, host_uuid: str, from_callback: bool = False) -> None:
    try:
        host = await api_client.get_host(host_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except NotFoundError:
        text = _("host.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("API client error while fetching host")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    info = host.get("response", host)
    summary = build_host_summary(host, _)
    is_disabled = bool(info.get("isDisabled"))
    keyboard = host_actions_keyboard(info.get("uuid", host_uuid), is_disabled)

    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await target.answer(summary, reply_markup=keyboard)


async def _send_subscription_detail(target: Message | CallbackQuery, short_uuid: str) -> None:
    try:
        sub = await api_client.get_subscription_info(short_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except NotFoundError:
        text = _("sub.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("API client error while fetching subscription")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    summary = build_subscription_summary(sub, _)
    sub_url = sub.get("response", sub).get("subscriptionUrl")
    keyboard = subscription_keyboard(sub_url)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await target.answer(summary, reply_markup=keyboard)


async def _send_template_detail(target: Message | CallbackQuery, tpl_uuid: str) -> None:
    try:
        tpl = await api_client.get_template(tpl_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except NotFoundError:
        text = _("template.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("API client error while fetching template")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    summary = build_template_summary(tpl, _)
    keyboard = template_actions_keyboard(tpl_uuid)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await target.answer(summary, reply_markup=keyboard)


async def _handle_template_create_input(message: Message, ctx: dict) -> None:
    parts = message.text.split(maxsplit=1)
    if len(parts) != 2:
        await message.answer(_("template.prompt_create"), reply_markup=template_menu_keyboard())
        return
    name, tpl_type = parts[0], parts[1].strip().upper()
    allowed = {"XRAY_JSON", "XRAY_BASE64", "MIHOMO", "STASH", "CLASH", "SINGBOX"}
    if tpl_type not in allowed:
        await message.answer(_("template.invalid_type"), reply_markup=template_menu_keyboard())
        return
    try:
        await api_client.create_template(name, tpl_type)
        await message.answer(_("template.created"), reply_markup=template_menu_keyboard())
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=template_menu_keyboard())
    except ApiClientError:
        logger.exception("Template create failed")
        await message.answer(_("template.invalid_payload"), reply_markup=template_menu_keyboard())


async def _handle_template_update_json_input(message: Message, ctx: dict) -> None:
    tpl_uuid = ctx.get("uuid")
    try:
        import json

        payload = json.loads(message.text)
    except Exception:
        await message.answer(_("template.invalid_payload"), reply_markup=template_actions_keyboard(tpl_uuid))
        return
    try:
        await api_client.update_template(tpl_uuid, template_json=payload)
        await message.answer(_("template.updated"), reply_markup=template_actions_keyboard(tpl_uuid))
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=template_actions_keyboard(tpl_uuid))
    except ApiClientError:
        logger.exception("Template update failed")
        await message.answer(_("template.invalid_payload"), reply_markup=template_actions_keyboard(tpl_uuid))


async def _handle_template_reorder_input(message: Message, ctx: dict) -> None:
    uuids = message.text.split()
    if not uuids:
        await message.answer(_("template.prompt_reorder"), reply_markup=template_menu_keyboard())
        return
    try:
        await api_client.reorder_templates(uuids)
        await message.answer(_("template.reordered"), reply_markup=template_menu_keyboard())
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=template_menu_keyboard())
    except ApiClientError:
        logger.exception("Template reorder failed")
        await message.answer(_("template.invalid_payload"), reply_markup=template_menu_keyboard())


async def _handle_provider_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action")
    parts = message.text.split()
    try:
        if action == "provider_create":
            if not parts:
                raise ValueError
            name = parts[0]
            favicon = parts[1] if len(parts) > 1 else None
            login = parts[2] if len(parts) > 2 else None
            await api_client.create_infra_provider(name=name, favicon_link=favicon, login_url=login)
            await message.answer(_("provider.created"), reply_markup=providers_menu_keyboard())
        elif action == "provider_update":
            if len(parts) < 2:
                raise ValueError
            provider_uuid = parts[0]
            name = parts[1] if len(parts) > 1 and parts[1] != "-" else None
            favicon = parts[2] if len(parts) > 2 and parts[2] != "-" else None
            login = parts[3] if len(parts) > 3 and parts[3] != "-" else None
            await api_client.update_infra_provider(provider_uuid, name=name, favicon_link=favicon, login_url=login)
            await message.answer(_("provider.updated"), reply_markup=providers_menu_keyboard())
        elif action == "provider_delete":
            if len(parts) != 1:
                raise ValueError
            await api_client.delete_infra_provider(parts[0])
            await message.answer(_("provider.deleted"), reply_markup=providers_menu_keyboard())
        else:
            await message.answer(_("errors.generic"), reply_markup=providers_menu_keyboard())
            return
    except ValueError:
        prompt_key = "provider.prompt_create" if action == "provider_create" else (
            "provider.prompt_update" if action == "provider_update" else "provider.prompt_delete"
        )
        await message.answer(_(prompt_key), reply_markup=providers_menu_keyboard())
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=providers_menu_keyboard())
    except ApiClientError:
        logger.exception("Provider action failed: %s", action)
        await message.answer(_("provider.invalid"), reply_markup=providers_menu_keyboard())


async def _handle_billing_history_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action")
    parts = message.text.split()
    try:
        if action == "billing_history_create":
            if len(parts) < 3:
                raise ValueError
            provider_uuid = parts[0]
            amount = float(parts[1])
            billed_at = parts[2]
            await api_client.create_infra_billing_record(provider_uuid, amount, billed_at)
            await message.answer(_("billing.done"), reply_markup=billing_menu_keyboard())
        elif action == "billing_history_delete":
            if len(parts) != 1:
                raise ValueError
            await api_client.delete_infra_billing_record(parts[0])
            await message.answer(_("billing.deleted"), reply_markup=billing_menu_keyboard())
        else:
            await message.answer(_("errors.generic"), reply_markup=billing_menu_keyboard())
            return
    except ValueError:
        prompt_key = "billing.prompt_create" if action == "billing_history_create" else "billing.prompt_delete"
        await message.answer(_(prompt_key), reply_markup=billing_menu_keyboard())
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=billing_menu_keyboard())
    except ApiClientError:
        logger.exception("Billing history action failed: %s", action)
        await message.answer(_("billing.invalid"), reply_markup=billing_menu_keyboard())


async def _handle_billing_nodes_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action")
    parts = message.text.split()
    try:
        if action == "billing_nodes_create":
            if len(parts) < 2:
                raise ValueError
            provider_uuid, node_uuid = parts[0], parts[1]
            next_billing_at = parts[2] if len(parts) > 2 else None
            await api_client.create_infra_billing_node(provider_uuid, node_uuid, next_billing_at)
            await message.answer(_("billing_nodes.done"), reply_markup=billing_nodes_menu_keyboard())
        elif action == "billing_nodes_update":
            if len(parts) < 2:
                raise ValueError
            next_billing_at = parts[0]
            uuids = parts[1:]
            await api_client.update_infra_billing_nodes(uuids, next_billing_at)
            await message.answer(_("billing_nodes.done"), reply_markup=billing_nodes_menu_keyboard())
        elif action == "billing_nodes_delete":
            if len(parts) != 1:
                raise ValueError
            await api_client.delete_infra_billing_node(parts[0])
            await message.answer(_("billing_nodes.deleted"), reply_markup=billing_nodes_menu_keyboard())
        else:
            await message.answer(_("errors.generic"), reply_markup=billing_nodes_menu_keyboard())
            return
    except ValueError:
        prompt_map = {
            "billing_nodes_create": _("billing_nodes.prompt_create"),
            "billing_nodes_update": _("billing_nodes.prompt_update"),
            "billing_nodes_delete": _("billing_nodes.prompt_delete"),
        }
        await message.answer(prompt_map.get(action, _("errors.generic")), reply_markup=billing_nodes_menu_keyboard())
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=billing_nodes_menu_keyboard())
    except ApiClientError:
        logger.exception("Billing nodes action failed: %s", action)
        await message.answer(_("billing_nodes.invalid"), reply_markup=billing_nodes_menu_keyboard())


async def _handle_bulk_nodes_input(message: Message, ctx: dict) -> None:
    stage = ctx.get("stage", "profile")
    user_id = message.from_user.id

    if stage == "profile":
        parts = message.text.split()
        if len(parts) < 2:
            PENDING_INPUT[user_id] = {"action": "bulk_nodes_profile", "stage": "profile"}
            await message.answer(_("bulk_nodes.prompt_profile"), reply_markup=bulk_nodes_keyboard())
            return
        profile_uuid, inbound_uuids = parts[0], parts[1:]
        PENDING_INPUT[user_id] = {
            "action": "bulk_nodes_profile",
            "stage": "nodes",
            "profile_uuid": profile_uuid,
            "inbound_uuids": inbound_uuids,
        }
        await message.answer(_("bulk_nodes.prompt_nodes"), reply_markup=bulk_nodes_keyboard())
        return

    node_uuids = message.text.split()
    if not node_uuids:
        PENDING_INPUT[user_id] = {
            "action": "bulk_nodes_profile",
            "stage": "nodes",
            "profile_uuid": ctx.get("profile_uuid"),
            "inbound_uuids": ctx.get("inbound_uuids", []),
        }
        await message.answer(_("bulk_nodes.prompt_nodes"), reply_markup=bulk_nodes_keyboard())
        return

    try:
        await api_client.bulk_nodes_profile_modification(
            node_uuids, ctx.get("profile_uuid", ""), ctx.get("inbound_uuids", [])
        )
        await message.answer(_("bulk_nodes.done"), reply_markup=main_menu_keyboard())
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=bulk_nodes_keyboard())
    except ApiClientError:
        logger.exception("Bulk nodes action failed")
        await message.answer(_("errors.generic"), reply_markup=bulk_nodes_keyboard())


async def _handle_bulk_hosts_input(message: Message, ctx: dict) -> None:
    action = ctx.get("action", "")
    uuids = message.text.split()
    if not uuids:
        await message.answer(_("bulk_hosts.usage"), reply_markup=bulk_hosts_keyboard())
        return
    try:
        if action == "bulk_hosts_enable":
            await api_client.bulk_enable_hosts(uuids)
        elif action == "bulk_hosts_disable":
            await api_client.bulk_disable_hosts(uuids)
        elif action == "bulk_hosts_delete":
            await api_client.bulk_delete_hosts(uuids)
        else:
            await message.answer(_("errors.generic"), reply_markup=bulk_hosts_keyboard())
            return
        await message.answer(_("bulk_hosts.done"), reply_markup=main_menu_keyboard())
    except UnauthorizedError:
        await message.answer(_("errors.unauthorized"), reply_markup=bulk_hosts_keyboard())
    except ApiClientError:
        logger.exception("Bulk hosts action failed")
        await message.answer(_("errors.generic"), reply_markup=bulk_hosts_keyboard())


async def _fetch_user(query: str) -> dict:
    if query.isdigit():
        return await api_client.get_user_by_telegram_id(int(query))
    return await api_client.get_user_by_username(query)


def _iso_from_days(days: int) -> str:
    now = datetime.utcnow()
    return (now + timedelta(days=days)).replace(microsecond=0).isoformat() + "Z"


async def _send_user_create_prompt(
    target: Message | CallbackQuery, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    if isinstance(target, CallbackQuery):
        await target.message.answer(text, reply_markup=reply_markup)
    else:
        await target.answer(text, reply_markup=reply_markup)


async def _send_squad_prompt(target: Message | CallbackQuery, ctx: dict) -> None:
    data = ctx.setdefault("data", {})
    squads: list[dict] = []
    squad_source = "internal"
    try:
        res = await api_client.get_internal_squads()
        squads = res.get("response", {}).get("internalSquads", [])
        logger.info("Loaded %s internal squads for user_id=%s", len(squads), target.from_user.id)
    except UnauthorizedError:
        await _send_user_create_prompt(target, _("errors.unauthorized"), users_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("Failed to load internal squads")
    except Exception:
        logger.exception("Unexpected error while loading internal squads")

    if not squads:
        try:
            res = await api_client.get_external_squads()
            squads = res.get("response", {}).get("externalSquads", [])
            squad_source = "external"
            logger.info("Loaded %s external squads for user_id=%s", len(squads), target.from_user.id)
        except UnauthorizedError:
            await _send_user_create_prompt(target, _("errors.unauthorized"), users_menu_keyboard())
            return
        except ApiClientError:
            logger.exception("Failed to load external squads")
        except Exception:
            logger.exception("Unexpected error while loading external squads")

    if not squads:
        await _send_user_create_prompt(
            target, _("user.squad_load_failed"), user_create_squad_keyboard([])
        )
        return

    squads_sorted = sorted(squads, key=lambda s: s.get("viewPosition", 0))
    markup = user_create_squad_keyboard(squads_sorted)
    text = _("user.prompt_squad") if squads_sorted else _("user.squad_load_failed")
    data["squad_source"] = squad_source
    PENDING_INPUT[target.from_user.id] = ctx
    await _send_user_create_prompt(target, text, markup)


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
        if isinstance(target, CallbackQuery):
            await target.message.answer(text, reply_markup=reply_markup)
        else:
            await target.answer(text, reply_markup=reply_markup)

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
            "Creating user username=%s expire_at=%s traffic_bytes=%s hwid=%s telegram_id=%s squad_source=%s internal_squads=%s external_squad_uuid=%s",
            username,
            expire_at,
            data.get("traffic_limit_bytes"),
            data.get("hwid_limit"),
            telegram_id,
            squad_source,
            internal_squads,
            external_squad_uuid,
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
        logger.exception("Create user failed")
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
    logger.info("User create input stage=%s user_id=%s text='%s'", stage, user_id, text)

    if stage == "username":
        if not text:
            await _send_user_create_prompt(message, _("user.prompt_username"))
            PENDING_INPUT[user_id] = ctx
            return
        data["username"] = text.split()[0]
        ctx["stage"] = "description"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(message, _("user.prompt_description"), user_create_description_keyboard())
        return

    if stage == "description":
        data["description"] = text
        ctx["stage"] = "expire"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(message, _("user.prompt_expire"), user_create_expire_keyboard())
        return

    if stage == "expire":
        try:
            datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            ctx["stage"] = "expire"
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(
                message, _("user.invalid_expire"), user_create_expire_keyboard()
            )
            return
        data["expire_at"] = text
        ctx["stage"] = "traffic"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(message, _("user.prompt_traffic"), user_create_traffic_keyboard())
        return

    if stage == "traffic":
        try:
            gb = float(text)
        except ValueError:
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(message, _("user.invalid_traffic"), user_create_traffic_keyboard())
            return
        data["traffic_limit_bytes"] = int(gb * 1024 * 1024 * 1024)
        ctx["stage"] = "hwid"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(message, _("user.prompt_hwid"), user_create_hwid_keyboard())
        return

    if stage == "hwid":
        try:
            hwid = int(text)
        except ValueError:
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(message, _("user.invalid_hwid"), user_create_hwid_keyboard())
            return
        data["hwid_limit"] = hwid
        ctx["stage"] = "telegram"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(message, _("user.prompt_telegram"), user_create_telegram_keyboard())
        return

    if stage == "telegram":
        if text:
            try:
                data["telegram_id"] = int(text)
            except ValueError:
                PENDING_INPUT[user_id] = ctx
                await _send_user_create_prompt(message, _("user.invalid_telegram"), user_create_telegram_keyboard())
                return
        else:
            data["telegram_id"] = None
        ctx["stage"] = "squad"
        PENDING_INPUT[user_id] = ctx
        try:
            await _send_squad_prompt(message, ctx)
        except Exception:
            logger.exception("Squad prompt failed, falling back to manual entry")
            await _send_user_create_prompt(
                message, _("user.squad_load_failed"), user_create_squad_keyboard([])
            )
        return

    if stage == "squad":
        data["squad_uuid"] = text or None
        ctx["stage"] = "confirm"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _build_user_create_preview(data), user_create_confirm_keyboard()
        )
        return

    # Default: stay on confirm
    if ctx.get("stage") == "confirm":
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            message, _build_user_create_preview(data), user_create_confirm_keyboard()
        )


async def _handle_user_create_callback(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id
    ctx = PENDING_INPUT.get(user_id, {"action": "user_create", "data": {}, "stage": "username"})
    data = ctx.setdefault("data", {})
    parts = callback.data.split(":")
    if len(parts) < 2:
        return
    action = parts[1]

    if action == "expire" and len(parts) >= 3:
        try:
            days = int(parts[2])
            data["expire_at"] = _iso_from_days(days)
        except ValueError:
            pass
        ctx["stage"] = "traffic"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(callback, _("user.prompt_traffic"), user_create_traffic_keyboard())
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
        await _send_user_create_prompt(callback, _("user.prompt_hwid"), user_create_hwid_keyboard())
        return

    if action == "hwid" and len(parts) >= 3:
        try:
            hwid = int(parts[2])
            data["hwid_limit"] = hwid if hwid > 0 else None
        except ValueError:
            data["hwid_limit"] = None
        ctx["stage"] = "telegram"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(callback, _("user.prompt_telegram"), user_create_telegram_keyboard())
        return

    if action == "skip" and len(parts) >= 3:
        field = parts[2]
        if field == "description":
            data["description"] = ""
            ctx["stage"] = "expire"
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(callback, _("user.prompt_expire"), user_create_expire_keyboard())
            return
        if field == "telegram":
            data["telegram_id"] = None
            ctx["stage"] = "squad"
            PENDING_INPUT[user_id] = ctx
            try:
                await _send_squad_prompt(callback, ctx)
            except Exception:
                logger.exception("Squad prompt failed from callback, falling back to manual entry")
                await _send_user_create_prompt(
                    callback, _("user.squad_load_failed"), user_create_squad_keyboard([])
                )
            return
        if field == "squad":
            data["squad_uuid"] = None
            ctx["stage"] = "confirm"
            PENDING_INPUT[user_id] = ctx
            await _send_user_create_prompt(callback, _build_user_create_preview(data), user_create_confirm_keyboard())
            return

    if action == "confirm":
        try:
            await _create_user(callback, data)
            PENDING_INPUT.pop(user_id, None)
        except Exception:
            PENDING_INPUT[user_id] = ctx
            raise
        return

    if action == "cancel":
        PENDING_INPUT.pop(user_id, None)
        await _send_user_create_prompt(callback, _("user.cancelled"), users_menu_keyboard())

    if action == "squad" and len(parts) >= 3:
        data["squad_uuid"] = parts[2]
        ctx["stage"] = "confirm"
        PENDING_INPUT[user_id] = ctx
        await _send_user_create_prompt(
            callback, _build_user_create_preview(data), user_create_confirm_keyboard()
        )


async def _fetch_health_text() -> str:
    try:
        data = await api_client.get_health()
        pm2 = data.get("response", {}).get("pm2Stats", [])
        if not pm2:
            return _("health.empty")
        lines = [_("health.title")]
        for proc in pm2:
            lines.append(f"• {proc.get('name')}: CPU {proc.get('cpu')} | RAM {proc.get('memory')}")
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Health check failed")
        return _("errors.generic")


async def _fetch_stats_text() -> str:
    try:
        data = await api_client.get_stats()
        res = data.get("response", {})
        mem = res.get("memory", {})
        cpu = res.get("cpu", {})
        users = res.get("users", {})
        online = res.get("onlineStats", {})
        nodes = res.get("nodes", {})
        status_counts = users.get("statusCounts", {}) or {}
        status_str = ", ".join(f"{k}: {v}" for k, v in status_counts.items()) if status_counts else "—"
        lines = [
            _("stats.title"),
            _("stats.uptime").format(uptime=format_uptime(res.get("uptime"))),
            _("stats.cpu").format(cores=cpu.get("cores", "—"), physical=cpu.get("physicalCores", "—")),
            _("stats.memory").format(
                used=format_bytes(mem.get("used")), total=format_bytes(mem.get("total"))
            ),
            _("stats.users").format(total=users.get("totalUsers", "—")),
            _("stats.status_counts").format(counts=status_str),
            _("stats.online").format(
                now=online.get("onlineNow", "—"),
                day=online.get("lastDay", "—"),
                week=online.get("lastWeek", "—"),
            ),
            _("stats.nodes").format(online=nodes.get("totalOnline", "—")),
        ]
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Stats fetch failed")
        return _("errors.generic")


async def _fetch_bandwidth_text() -> str:
    try:
        data = await api_client.get_bandwidth_stats()
        return build_bandwidth_stats(data, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Bandwidth fetch failed")
        return _("errors.generic")


async def _fetch_billing_text() -> str:
    try:
        data = await api_client.get_infra_billing_history()
        records = data.get("response", {}).get("records", [])
        return build_billing_history(records, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Billing fetch failed")
        return _("errors.generic")


async def _fetch_providers_text() -> str:
    try:
        data = await api_client.get_infra_providers()
        providers = data.get("response", {}).get("providers", [])
        return build_infra_providers(providers, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Providers fetch failed")
        return _("errors.generic")


async def _fetch_billing_nodes_text() -> str:
    try:
        data = await api_client.get_infra_billing_nodes()
        return build_billing_nodes(data, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Billing nodes fetch failed")
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
        logger.exception("Nodes fetch failed")
        return _("errors.generic")


async def _fetch_nodes_realtime_text() -> str:
    try:
        data = await api_client.get_nodes_realtime_usage()
        usages = data.get("response", [])
        return build_nodes_realtime_usage(usages, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Nodes realtime fetch failed")
        return _("errors.generic")


async def _fetch_nodes_range_text(start: str, end: str) -> str:
    try:
        data = await api_client.get_nodes_usage_range(start, end)
        usages = data.get("response", [])
        return build_nodes_usage_range(usages, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Nodes range fetch failed")
        return _("errors.generic")


async def _fetch_configs_text() -> str:
    try:
        data = await api_client.get_config_profiles()
        profiles = data.get("response", {}).get("configProfiles", [])
        return build_config_profiles_list(profiles, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Config profiles fetch failed")
        return _("errors.generic")


async def _send_config_detail(target: Message | CallbackQuery, config_uuid: str) -> None:
    try:
        profile = await api_client.get_config_profile_computed(config_uuid)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except NotFoundError:
        text = _("config.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("Config profile fetch failed")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    summary = build_config_profile_detail(profile, _)
    keyboard = config_actions_keyboard(config_uuid)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await target.answer(summary, reply_markup=keyboard)


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
        logger.exception("Hosts fetch failed")
        return _("errors.generic")


async def _fetch_tokens_text() -> str:
    try:
        data = await api_client.get_tokens()
        tokens = data.get("response", {}).get("apiKeys", [])
        return build_tokens_list(tokens, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Tokens fetch failed")
        return _("errors.generic")


async def _fetch_templates_text() -> str:
    try:
        data = await api_client.get_templates()
        templates = data.get("response", {}).get("templates", [])
        return build_templates_list(templates, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Templates fetch failed")
        return _("errors.generic")


async def _fetch_snippets_text() -> str:
    try:
        data = await api_client.get_snippets()
        snippets = data.get("response", {}).get("snippets", [])
        return build_snippets_list(snippets, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("Snippets fetch failed")
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
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except NotFoundError:
        text = _("snippet.not_found")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("API client error while fetching snippet")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    summary = build_snippet_detail(snippet, _)
    keyboard = snippet_actions_keyboard(name)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await target.answer(summary, reply_markup=keyboard)


async def _upsert_snippet(target: Message, action: str) -> None:
    parts = target.text.split(maxsplit=2)
    if len(parts) < 3:
        await target.answer(_("snippet.usage"))
        return
    name = parts[1].strip()
    raw_json = parts[2].strip()
    try:
        import json

        snippet_body = json.loads(raw_json)
    except Exception:
        await target.answer(_("snippet.invalid_json"))
        return

    try:
        if action == "create":
            res = await api_client.create_snippet(name, snippet_body)
        else:
            res = await api_client.update_snippet(name, snippet_body)
    except UnauthorizedError:
        await target.answer(_("errors.unauthorized"))
        return
    except ApiClientError:
        logger.exception("Snippet %s failed", action)
        await target.answer(_("errors.generic"))
        return

    # Return detail
    content = res.get("response", res).get("snippet", snippet_body)
    detail = build_snippet_detail({"name": name, "snippet": content}, _)
    await target.answer(detail, reply_markup=snippet_actions_keyboard(name))


async def _create_token(target: Message | CallbackQuery, name: str) -> None:
    try:
        token = await api_client.create_token(name)
    except UnauthorizedError:
        text = _("errors.unauthorized")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return
    except ApiClientError:
        logger.exception("Create token failed")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await target.answer(text)
        return

    summary = build_created_token(token, _)
    token_uuid = token.get("response", token).get("uuid", "")
    keyboard = token_actions_keyboard(token_uuid)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=keyboard)
    else:
        await target.answer(summary, reply_markup=keyboard)


async def _show_tokens(
    target: Message | CallbackQuery, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    text = await _fetch_tokens_text()
    markup = reply_markup or main_menu_keyboard()
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(text, reply_markup=markup)
        send = target.message.answer
    else:
        await target.answer(text, reply_markup=markup)
        send = target.answer

    # Also send first few tokens with delete buttons for quick actions
    try:
        data = await api_client.get_tokens()
        tokens = data.get("response", {}).get("apiKeys", [])
        for token in tokens[:5]:
            line = build_token_line(token, _)
            uuid = token.get("uuid", "")
            await send(line, reply_markup=token_actions_keyboard(uuid))
    except Exception:
        logger.exception("Failed to send token buttons")
