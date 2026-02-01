"""Обработчики команд бота."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _not_admin, _send_clean_message
from src.handlers.state import PENDING_INPUT
from src.keyboards.billing_menu import billing_menu_keyboard
from src.keyboards.billing_nodes_menu import billing_nodes_menu_keyboard
from src.keyboards.hosts_menu import hosts_menu_keyboard
from src.keyboards.main_menu import bulk_menu_keyboard, main_menu_keyboard, nodes_menu_keyboard, resources_menu_keyboard, system_menu_keyboard
from src.keyboards.providers_menu import providers_menu_keyboard
from src.keyboards.stats_menu import stats_menu_keyboard

# Импорты из соответствующих модулей
from src.handlers.billing import _fetch_billing_nodes_text, _fetch_billing_text, _fetch_providers_text
from src.handlers.bulk import ALLOWED_STATUSES, _handle_bulk_users_input, _parse_uuids, _run_bulk_action
from src.handlers.hosts import _fetch_hosts_text, _handle_host_create_input, _send_host_detail
from src.handlers.nodes import _fetch_nodes_range_text, _fetch_nodes_realtime_text, _fetch_nodes_text, _handle_node_create_input, _handle_node_edit_input, _send_node_detail
from src.handlers.navigation import _fetch_main_menu_text, _send_subscription_detail
from src.handlers.resources import (
    _create_token,
    _fetch_configs_text,
    _fetch_snippets_text,
    _handle_template_create_input,
    _handle_template_reorder_input,
    _handle_template_update_json_input,
    _send_config_detail,
    _send_snippet_detail,
    _send_template_detail,
    _send_templates,
    _show_tokens,
    _upsert_snippet,
)
from src.handlers.system import _fetch_bandwidth_text, _fetch_health_text, _handle_asn_sync_custom_limit_input
from src.handlers.users import (
    _create_user,
    _handle_user_create_input,
    _handle_user_edit_input,
    _handle_user_search_input,
    _send_user_create_prompt,
    _start_user_search_flow,
)

from src.handlers.billing import _handle_billing_history_input, _handle_billing_nodes_input, _handle_provider_input

router = Router(name="commands")


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Обработчик команды /start."""
    if await _not_admin(message):
        return

    await _send_clean_message(message, _("bot.welcome"))
    menu_text = await _fetch_main_menu_text()
    await _send_clean_message(message, menu_text, reply_markup=main_menu_keyboard(), parse_mode="HTML")


@router.message(F.text & ~F.text.startswith("/"))
async def handle_pending(message: Message, state: FSMContext) -> None:
    """Обработчик текстовых сообщений (не команд) для ожидаемого ввода."""
    if await _not_admin(message):
        return
    user_id = message.from_user.id
    from src.utils.logger import logger
    in_pending = user_id in PENDING_INPUT

    # Проверяем FSM состояние (например, ConfigInputState.waiting_value)
    fsm_state = await state.get_state()

    logger.info(
        "handle_pending: user_id=%s in_PENDING_INPUT=%s fsm_state=%s text='%s'",
        user_id, in_pending, fsm_state, message.text[:50] if message.text else None
    )

    # Если есть активное FSM состояние - пропускаем, пусть FSM обработчик сам обработает
    if fsm_state is not None:
        logger.info("handle_pending: skipping - FSM state active: %s", fsm_state)
        return

    if not in_pending:
        # Если это не ожидаемый ввод и нет FSM состояния, удаляем сообщение
        from src.handlers.common import _cleanup_message
        import asyncio
        logger.info("handle_pending: deleting message - not in PENDING_INPUT and no FSM state")
        asyncio.create_task(_cleanup_message(message, delay=0.0))
        return
    
    # НЕ удаляем из PENDING_INPUT сразу - пусть обработчик сам решает, когда это делать
    # Это гарантирует, что сообщение не будет удалено до завершения обработки
    ctx = PENDING_INPUT.get(user_id)
    if not ctx:
        logger.warning("handle_pending: user_id=%s in PENDING_INPUT but ctx is None", user_id)
        return
    action = ctx.get("action")
    logger.info("handle_pending: processing action=%s", action)
    if action == "user_search":
        await _handle_user_search_input(message, ctx)
    elif action == "subs_search":
        from src.handlers.navigation import _handle_subs_search_input
        await _handle_subs_search_input(message, ctx)
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
    elif action == "host_create":
        await _handle_host_create_input(message, ctx)
    elif action == "node_edit":
        await _handle_node_edit_input(message, ctx)
    elif action == "asn_sync_custom_limit":
        await _handle_asn_sync_custom_limit_input(message, ctx)
    else:
        await _send_clean_message(message, _("errors.generic"))


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Обработчик команды /help."""
    if await _not_admin(message):
        return

    await _send_clean_message(message, _("bot.help"))


@router.message(Command("health"))
async def cmd_health(message: Message) -> None:
    """Обработчик команды /health."""
    if await _not_admin(message):
        return
    await _send_clean_message(message, await _fetch_health_text(), reply_markup=system_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    """Обработчик команды /stats."""
    if await _not_admin(message):
        return
    text = _("stats.menu_title")
    await _send_clean_message(message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("bandwidth"))
async def cmd_bandwidth(message: Message) -> None:
    """Обработчик команды /bandwidth."""
    if await _not_admin(message):
        return
    text = await _fetch_bandwidth_text()
    await _send_clean_message(message, text, reply_markup=system_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("billing"))
async def cmd_billing(message: Message) -> None:
    """Обработчик команды /billing."""
    if await _not_admin(message):
        return
    text = await _fetch_billing_text()
    await _send_clean_message(message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("providers"))
async def cmd_providers(message: Message) -> None:
    """Обработчик команды /providers."""
    if await _not_admin(message):
        return
    text = await _fetch_providers_text()
    await _send_clean_message(message, text, reply_markup=providers_menu_keyboard(), parse_mode="Markdown")


@router.message(Command("billing_nodes"))
async def cmd_billing_nodes(message: Message) -> None:
    """Обработчик команды /billing_nodes."""
    if await _not_admin(message):
        return
    text = await _fetch_billing_nodes_text()
    await _send_clean_message(message, text, reply_markup=billing_nodes_menu_keyboard())


@router.message(Command("bulk"))
async def cmd_bulk(message: Message) -> None:
    """Обработчик команды /bulk."""
    if await _not_admin(message):
        return
    await _send_clean_message(message, _("bulk.title"), reply_markup=bulk_menu_keyboard())


@router.message(Command("bulk_delete_status"))
async def cmd_bulk_delete_status(message: Message) -> None:
    """Обработчик команды /bulk_delete_status."""
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
    """Обработчик команды /bulk_delete."""
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await _send_clean_message(message, _("bulk.usage_delete"))
        return
    await _run_bulk_action(message, action="delete", uuids=uuids)


@router.message(Command("bulk_revoke"))
async def cmd_bulk_revoke(message: Message) -> None:
    """Обработчик команды /bulk_revoke."""
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await _send_clean_message(message, _("bulk.usage_revoke"))
        return
    await _run_bulk_action(message, action="revoke", uuids=uuids)


@router.message(Command("bulk_reset"))
async def cmd_bulk_reset(message: Message) -> None:
    """Обработчик команды /bulk_reset."""
    if await _not_admin(message):
        return
    uuids = _parse_uuids(message.text, expected_min=1)
    if not uuids:
        await _send_clean_message(message, _("bulk.usage_reset"))
        return
    await _run_bulk_action(message, action="reset", uuids=uuids)


@router.message(Command("bulk_extend"))
async def cmd_bulk_extend(message: Message) -> None:
    """Обработчик команды /bulk_extend."""
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
    """Обработчик команды /bulk_extend_all."""
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
    """Обработчик команды /bulk_status."""
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
    """Обработчик команды /user."""
    if await _not_admin(message):
        return

    parts = message.text.split(maxsplit=1)
    preset_query = parts[1].strip() if len(parts) > 1 else ""
    await _start_user_search_flow(message, preset_query or None)


@router.message(Command("user_create"))
async def cmd_user_create(message: Message) -> None:
    """Обработчик команды /user_create."""
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
    """Обработчик команды /nodes."""
    if await _not_admin(message):
        return
    text = await _fetch_nodes_text()
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("nodes_usage"))
async def cmd_nodes_usage(message: Message) -> None:
    """Обработчик команды /nodes_usage."""
    if await _not_admin(message):
        return
    text = await _fetch_nodes_realtime_text()
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("nodes_range"))
async def cmd_nodes_range(message: Message) -> None:
    """Обработчик команды /nodes_range."""
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
    """Обработчик команды /node."""
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
    """Обработчик команды /hosts."""
    if await _not_admin(message):
        return
    text = await _fetch_hosts_text()
    await _send_clean_message(message, text, reply_markup=hosts_menu_keyboard())


@router.message(Command("host"))
async def cmd_host(message: Message) -> None:
    """Обработчик команды /host."""
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
    """Обработчик команды /sub."""
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
    """Обработчик команды /tokens."""
    if await _not_admin(message):
        return
    await _show_tokens(message, reply_markup=resources_menu_keyboard())


@router.message(Command("token"))
async def cmd_token_create(message: Message) -> None:
    """Обработчик команды /token."""
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
    """Обработчик команды /templates."""
    if await _not_admin(message):
        return
    await _send_templates(message)


@router.message(Command("template"))
async def cmd_template(message: Message) -> None:
    """Обработчик команды /template."""
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
    """Обработчик команды /snippets."""
    if await _not_admin(message):
        return
    text = await _fetch_snippets_text()
    await _send_clean_message(message, text, reply_markup=resources_menu_keyboard())


@router.message(Command("snippet"))
async def cmd_snippet(message: Message) -> None:
    """Обработчик команды /snippet."""
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
    """Обработчик команды /snippet_add."""
    if await _not_admin(message):
        return
    await _upsert_snippet(message, action="create")


@router.message(Command("snippet_update"))
async def cmd_snippet_update(message: Message) -> None:
    """Обработчик команды /snippet_update."""
    if await _not_admin(message):
        return
    await _upsert_snippet(message, action="update")


@router.message(Command("configs"))
async def cmd_configs(message: Message) -> None:
    """Обработчик команды /configs."""
    if await _not_admin(message):
        return
    text = await _fetch_configs_text()
    await _send_clean_message(message, text, reply_markup=nodes_menu_keyboard())


@router.message(Command("config"))
async def cmd_config(message: Message) -> None:
    """Обработчик команды /config."""
    if await _not_admin(message):
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await _send_clean_message(message, _("config.usage"))
        return
    config_uuid = parts[1].strip()
    await _send_config_detail(message, config_uuid)

