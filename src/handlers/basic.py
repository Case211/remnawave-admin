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
from src.keyboards.hosts_menu import hosts_menu_keyboard
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
from src.keyboards.host_edit import host_edit_keyboard
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
from src.keyboards.user_actions import (
    user_actions_keyboard,
    user_edit_keyboard,
    user_edit_strategy_keyboard,
    user_edit_squad_keyboard,
)
from src.keyboards.user_stats import user_stats_keyboard
from src.keyboards.node_edit import node_edit_keyboard
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
    _esc,
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
from src.handlers.hosts import _apply_host_update, _fetch_hosts_text, _host_config_profiles_keyboard
from src.handlers.common import _cleanup_message, _not_admin, _send_clean_message, _get_target_user_id, _clear_user_state, _edit_text_safe
from src.handlers.resources import _show_tokens, _fetch_configs_text, _fetch_snippets_text, _send_templates, _send_template_detail
from src.handlers.users import (
    _send_user_detail,
    _send_user_summary,
    _store_user_detail_back_target,
    _get_user_detail_back_target,
    _start_user_search_flow,
    _handle_user_search_input,
    _run_user_search,
    _show_user_search_results,
    _search_users,
    _fetch_user,
    _apply_user_update,
    _handle_user_edit_input,
    _format_user_edit_snapshot,
    _current_user_edit_values,
    _iso_from_days,
    _delete_ctx_message,
    _send_user_create_prompt,
    _show_squad_selection_for_edit,
    _send_squad_prompt,
    _build_user_create_preview,
    _create_user,
    _handle_user_create_input,
    _handle_user_create_callback,
)
from src.handlers.nodes import (
    _send_node_detail,
    _fetch_nodes_text,
    _node_providers_keyboard,
    _node_yes_no_keyboard,
    _apply_node_update,
    _handle_node_edit_input,
    _handle_node_create_input,
)
from src.handlers.navigation import (
    _navigate,
    _send_subscriptions_page,
    _get_subs_page,
    _fetch_main_menu_text,
)
from src.handlers.billing import (
    _fetch_billing_text,
    _fetch_billing_nodes_text,
    _fetch_providers_text,
    _handle_provider_input,
    _handle_billing_history_input,
    _handle_billing_nodes_input,
)
from src.handlers.resources import (
    _handle_template_create_input,
    _handle_template_update_json_input,
    _handle_template_reorder_input,
)
from src.handlers.hosts import _handle_host_create_input
from src.handlers.state import (
    PENDING_INPUT,
    LAST_BOT_MESSAGES,
    USER_SEARCH_CONTEXT,
    USER_DETAIL_BACK_TARGET,
    SUBS_PAGE_BY_USER,
    ADMIN_COMMAND_DELETE_DELAY,
    SEARCH_PAGE_SIZE,
    MAX_SEARCH_RESULTS,
    SUBS_PAGE_SIZE,
)

router = Router(name="basic")


# Все обработчики команд перенесены в commands.py
# Все callback-обработчики перенесены в соответствующие модули:
# - users.py: menu:create_user, user_create:, menu:find_user, user_search:view:, user:, user_edit:, uef:, user_configs:, user_sub_link:, user_happ_link:, user_stats:*
# - nodes.py: menu:nodes, nodes:*, node_create:*, node_edit:*, nef:*, node_delete:*, node:*
# - hosts.py: menu:hosts, hosts:*, host_edit:*, hef:*, host:*
# - resources.py: menu:tokens, menu:templates, menu:snippets, menu:configs, token:*, template:*, tplview:*, snippet:*, config:*
# - billing.py: menu:providers, menu:billing, menu:billing_nodes, providers:*, billing:*, billing_nodes:*
# - bulk.py: menu:bulk_users, menu:bulk_hosts, bulk:users:*, bulk:hosts:*
# - system.py: menu:section:system, menu:health, menu:stats, stats:*, menu:system_nodes, system:nodes:*
# - navigation.py: nav:home, nav:back:*, menu:back, subs:page:*, subs:view:*


# Обработчики user_search:view:, menu:nodes, nodes:*, node_create:* перенесены в users.py и nodes.py
# Обработчики menu:hosts, hosts:*, host_edit:*, hef:* перенесены в hosts.py
# Удаляем дубликаты для уменьшения размера файла


# Обработчики menu:subs, menu:tokens, menu:templates, menu:snippets, menu:configs перенесены в navigation.py и resources.py
# Обработчики menu:providers, menu:billing, menu:billing_nodes перенесены в billing.py
# Обработчики menu:bulk_hosts, menu:bulk_users перенесены в bulk.py
# Обработчики menu:system_nodes перенесены в system.py


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
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port="—",
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", []))
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:country")
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
                        name=data.get("name", ""),
                        address=data.get("address", ""),
                        port=str(data.get("port", "—")) if data.get("port") else "—",
                        country="—",
                        profile_name=data.get("profile_name", ""),
                        inbounds_count=len(data.get("selected_inbounds", []))
                    ),
                    reply_markup=keyboard
                )
            except Exception:
                data["provider_uuid"] = None
                ctx["stage"] = "traffic_tracking"
                PENDING_INPUT[user_id] = ctx
                await callback.message.edit_text(
                    _("node.prompt_traffic_tracking").format(
                        name=data.get("name", ""),
                        address=data.get("address", ""),
                        port=str(data.get("port", "—")) if data.get("port") else "—",
                        country="—",
                        provider="—",
                        profile_name=data.get("profile_name", ""),
                        inbounds_count=len(data.get("selected_inbounds", []))
                    ),
                    reply_markup=_node_yes_no_keyboard("node_create", "traffic_tracking")
                )
        elif stage == "traffic_limit":
            data["traffic_limit_bytes"] = None
            ctx["stage"] = "notify_percent"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_notify_percent").format(
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port=str(data.get("port", "—")) if data.get("port") else "—",
                    country=data.get("country_code", "—") or "—",
                    provider=data.get("provider_name", "—") or "—",
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:notify_percent")
            )
        elif stage == "notify_percent":
            data["notify_percent"] = None
            ctx["stage"] = "traffic_reset_day"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_traffic_reset_day").format(
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port=str(data.get("port", "—")) if data.get("port") else "—",
                    country=data.get("country_code", "—") or "—",
                    provider=data.get("provider_name", "—") or "—",
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—",
                    notify_percent="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:traffic_reset_day")
            )
        elif stage == "traffic_reset_day":
            data["traffic_reset_day"] = None
            ctx["stage"] = "consumption_multiplier"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_consumption_multiplier").format(
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port=str(data.get("port", "—")) if data.get("port") else "—",
                    country=data.get("country_code", "—") or "—",
                    provider=data.get("provider_name", "—") or "—",
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—",
                    notify_percent=str(data["notify_percent"]) if data.get("notify_percent") is not None else "—",
                    reset_day="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:consumption_multiplier")
            )
        elif stage == "consumption_multiplier":
            data["consumption_multiplier"] = None
            ctx["stage"] = "tags"
            PENDING_INPUT[user_id] = ctx
            await callback.message.edit_text(
                _("node.prompt_tags").format(
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port=str(data.get("port", "—")) if data.get("port") else "—",
                    country=data.get("country_code", "—") or "—",
                    provider=data.get("provider_name", "—") or "—",
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—",
                    notify_percent=str(data["notify_percent"]) if data.get("notify_percent") is not None else "—",
                    reset_day=str(data["traffic_reset_day"]) if data.get("traffic_reset_day") else "—",
                    multiplier="—"
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:tags")
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
                from src.keyboards.nodes_menu import nodes_list_keyboard
                await callback.message.edit_text(nodes_text, reply_markup=nodes_list_keyboard())
            except UnauthorizedError:
                PENDING_INPUT.pop(user_id, None)
                from src.keyboards.nodes_menu import nodes_list_keyboard
                await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nodes_list_keyboard())
            except ApiClientError:
                PENDING_INPUT.pop(user_id, None)
                logger.exception("❌ Node creation failed")
                from src.keyboards.nodes_menu import nodes_list_keyboard
                await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_list_keyboard())
    
    elif action == "host_create":
        # Обработка пропуска шагов при создании хоста
        if stage == "tag":
            data["tag"] = None
            ctx["stage"] = "config_profile"
            PENDING_INPUT[user_id] = ctx
            # Показываем список профилей конфигурации для выбора
            try:
                profiles_data = await api_client.get_config_profiles()
                profiles = profiles_data.get("response", {}).get("configProfiles", [])
                if not profiles:
                    await callback.message.edit_text(
                        _("host.no_config_profiles"),
                        reply_markup=input_keyboard(action)
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
                keyboard = _host_config_profiles_keyboard(profiles)
                await callback.message.edit_text(
                    _("host.prompt_config_profile"),
                    reply_markup=keyboard
                )
            except Exception:
                logger.exception("❌ Failed to load config profiles for host creation")
                await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())
                PENDING_INPUT.pop(user_id, None)
    elif len(parts) >= 4 and parts[0] == "hef" and parts[1] == "inbound" and len(parts) >= 4:
        # hef:inbound:{inbound_uuid}:{host_uuid} - выбор инбаунда для редактирования
        inbound_uuid = parts[2]
        host_uuid = parts[3]
        back_to = NavTarget.HOSTS_MENU
        
        try:
            # Получаем текущий профиль конфигурации хоста
            host = await api_client.get_host(host_uuid)
            info = host.get("response", host)
            inbound_info = info.get("inbound", {})
            config_profile_uuid = inbound_info.get("configProfileUuid")
            
            if not config_profile_uuid:
                await callback.message.edit_text(
                    _("host.no_config_profiles"),
                    reply_markup=host_edit_keyboard(host_uuid, back_to=back_to)
                )
                return
            
            # Обновляем хост с новым инбаундом
            await _apply_host_update(
                callback,
                host_uuid,
                {
                    "inbound": {
                        "configProfileUuid": config_profile_uuid,
                        "configProfileInboundUuid": inbound_uuid,
                    }
                },
                back_to=back_to
            )
        except Exception:
            logger.exception("❌ Failed to update host inbound")
            await callback.message.edit_text(_("errors.generic"), reply_markup=host_edit_keyboard(host_uuid, back_to=back_to))
    elif len(parts) >= 4 and parts[0] == "nef" and parts[1] == "skip":
        # nef:skip:{node_uuid}:{field}
        node_uuid = parts[2]
        field = parts[3]
        back_to = NavTarget.NODES_LIST
        
        # Пропускаем поле - оставляем текущее значение (не обновляем)
        try:
            node = await api_client.get_node(node_uuid)
            summary = build_node_summary(node, _)
            await callback.message.edit_text(
                summary,
                reply_markup=node_edit_keyboard(node_uuid, back_to=back_to),
                parse_mode="HTML"
            )
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))


# Обработчики providers:*, billing:*, billing_nodes:* перенесены в billing.py
# Обработчики nav:home, nav:back:*, subs:page:*, subs:view:*, menu:back перенесены в navigation.py
# Обработчики user:*, user_edit:*, uef:*, user_configs:*, user_sub_link:*, user_happ_link:*, user_stats:* перенесены в users.py
# Обработчики node_edit:*, nef:*, node_delete:*, node:* перенесены в nodes.py
# Обработчики host:* перенесены в hosts.py
# Обработчики token:*, template:*, tplview:*, snippet:* перенесены в resources.py
# Обработчики bulk:users:*, bulk:hosts:* перенесены в bulk.py
# Удаляем дубликаты для уменьшения размера файла

# Временно оставляем обработчик input:skip: для обратной совместимости
# TODO: Перенести логику input:skip: в соответствующие модули

# Обработчики providers:*, billing:*, billing_nodes:* уже есть в billing.py - удаляем дубликаты
# Обработчики nav:home, nav:back:*, subs:page:*, subs:view:* уже есть в navigation.py - удаляем дубликаты
# Обработчики user:*, user_edit:*, uef:*, user_configs:*, user_sub_link:*, user_happ_link:*, user_stats:* уже есть в users.py - удаляем дубликаты
# Обработчик menu:back уже есть в navigation.py - удаляем дубликат
# Обработчики node_edit:*, nef:*, node_delete:*, node_delete_confirm:*, node:* уже есть в nodes.py - удаляем дубликаты
# Обработчики token:*, template:*, snippet:*, tplview:* уже есть в resources.py - удаляем дубликаты
# Обработчики host:* уже есть в hosts.py - удаляем дубликаты
# Обработчики bulk:users:*, bulk:hosts:* уже есть в bulk.py - удаляем дубликаты
# Обработчики system:nodes:* уже есть в system.py - удаляем дубликаты
# Функции _parse_uuids, _run_bulk_action, _reply уже есть в bulk.py - удаляем дубликаты
# Обработчики config:* уже есть в resources.py - удаляем дубликаты


# Helpers
# Функции _send_user_detail, _send_user_summary, _store_user_detail_back_target, _get_user_detail_back_target, _get_subs_page
# уже импортированы из users.py и navigation.py - удаляем дубликаты
# Функции _send_node_detail, _send_host_detail уже импортированы из nodes.py и hosts.py - удаляем дубликаты


# Функция _send_subscription_detail перенесена в navigation.py
# Функция _send_template_detail уже импортирована из resources.py - удаляем дубликат
# Функции _handle_template_create_input, _handle_template_update_json_input, _handle_template_reorder_input уже импортированы из resources.py - удаляем дубликаты
# Функции _handle_provider_input, _handle_billing_history_input, _handle_billing_nodes_input уже импортированы из billing.py - удаляем дубликаты
# Функции _handle_node_create_input, _apply_node_update, _handle_node_edit_input уже импортированы из nodes.py - удаляем дубликаты
# Функции _handle_host_create_input уже импортированы из hosts.py - удаляем дубликаты
# Функции _apply_user_update, _handle_user_edit_input, _format_user_edit_snapshot, _current_user_edit_values,
# _send_user_create_prompt, _show_squad_selection_for_edit, _send_squad_prompt, _build_user_create_preview,
# _create_user, _handle_user_create_input уже импортированы из users.py - удаляем дубликаты
# Функции _billing_providers_keyboard, _providers_select_keyboard, _nodes_select_keyboard, _billing_nodes_keyboard
# уже импортированы из billing.py - удаляем дубликаты


# Дублирующиеся функции обработки ввода (_handle_provider_input, _handle_billing_history_input, 
# _handle_node_create_input, _handle_host_create_input, _handle_billing_nodes_input) 
# уже импортированы из billing.py, nodes.py, hosts.py - удаляем дубликаты




