"""Обработчики для работы с нодами."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.callback_mapping import generate_short_callback, resolve_short_callback
from src.handlers.common import _cleanup_message, _edit_text_safe, _not_admin, _send_clean_message
from src.handlers.state import PENDING_INPUT
from src.keyboards.main_menu import main_menu_keyboard, nodes_menu_keyboard
from src.keyboards.navigation import NavTarget, nav_keyboard, nav_row
from src.keyboards.node_actions import node_actions_keyboard
from src.keyboards.node_edit import node_edit_keyboard
from src.keyboards.navigation import input_keyboard
from src.services.api_client import ApiClientError, NotFoundError, UnauthorizedError, api_client
from src.utils.formatters import _esc, build_node_summary, build_nodes_realtime_usage, build_nodes_usage_range, format_bytes
from src.utils.logger import logger

# Функции перенесены из basic.py

router = Router(name="nodes")


async def _fetch_nodes_text() -> str:
    """Получает текст со списком нод."""
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
            line = _("node.list_item").format(
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


async def _fetch_nodes_with_keyboard() -> tuple[str, InlineKeyboardMarkup]:
    """Получает текст списка нод со статистикой и клавиатуру с кнопками для каждой ноды."""
    try:
        data = await api_client.get_nodes()
        nodes = data.get("response", [])
        if not nodes:
            return _("node.list_empty"), InlineKeyboardMarkup(inline_keyboard=[nav_row(NavTarget.NODES_LIST)])

        sorted_nodes = sorted(nodes, key=lambda n: n.get("viewPosition", 0))

        # Вычисляем статистику
        total_nodes = len(nodes)
        enabled_nodes = sum(1 for n in nodes if not n.get("isDisabled"))
        disabled_nodes = total_nodes - enabled_nodes
        online_nodes = sum(1 for n in nodes if n.get("isConnected"))
        total_users = sum(n.get("usersOnline", 0) or 0 for n in nodes)
        total_traffic = sum(n.get("trafficUsedBytes", 0) or 0 for n in nodes)

        # Формируем текст со статистикой и списком нод
        lines = [
            _("node.list_title").format(total=total_nodes),
            "",
            _("node.list_stats").format(
                total=total_nodes,
                enabled=enabled_nodes,
                disabled=disabled_nodes,
                online=online_nodes,
                users=total_users,
                traffic=format_bytes(total_traffic),
            ),
            "",
        ]

        rows: list[list[InlineKeyboardButton]] = []

        for node in sorted_nodes[:20]:  # Увеличиваем до 20 нод
            status = "DISABLED" if node.get("isDisabled") else ("ONLINE" if node.get("isConnected") else "OFFLINE")
            status_emoji = "🟢" if status == "ONLINE" else ("🟡" if status == "DISABLED" else "🔴")
            address = f"{node.get('address', 'n/a')}:{node.get('port') or '—'}"
            users_online = node.get("usersOnline", "—")
            name = node.get("name", "n/a")
            node_uuid = node.get("uuid", "")

            line = _("node.list_item").format(
                statusEmoji=status_emoji,
                name=name,
                address=address,
                users=users_online,
                traffic=format_bytes(node.get("trafficUsedBytes")),
            )
            lines.append(line)

            # Добавляем кнопку для редактирования ноды
            rows.append([InlineKeyboardButton(text=f"{status_emoji} {name}", callback_data=f"node_edit:{node_uuid}")])

        if len(nodes) > 20:
            lines.append(_("node.list_more").format(count=len(nodes) - 20))

        # Добавляем только кнопку "Назад" к списку нод
        rows.append(nav_row(NavTarget.NODES_LIST))

        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        return "\n".join(lines), keyboard
    except UnauthorizedError:
        return _("errors.unauthorized"), InlineKeyboardMarkup(inline_keyboard=[nav_row(NavTarget.NODES_LIST)])
    except ApiClientError:
        logger.exception("⚠️ Nodes fetch failed")
        return _("errors.generic"), InlineKeyboardMarkup(inline_keyboard=[nav_row(NavTarget.NODES_LIST)])


async def _fetch_nodes_realtime_text() -> str:
    """Получает текст со статистикой нод в реальном времени."""
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
    """Получает текст со статистикой нод за период."""
    try:
        data = await api_client.get_nodes_usage_range(start, end)
        usages = data.get("response", [])
        return build_nodes_usage_range(usages, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Nodes range fetch failed")
        return _("errors.generic")


async def _apply_node_update(target: Message | CallbackQuery, node_uuid: str, payload: dict, back_to: str) -> None:
    """Применяет обновление ноды."""
    try:
        # Преобразуем payload для API
        api_payload = {}
        if "name" in payload:
            api_payload["name"] = payload["name"]
        if "address" in payload:
            api_payload["address"] = payload["address"]
        if "port" in payload:
            api_payload["port"] = payload["port"]
        if "country_code" in payload:
            api_payload["countryCode"] = payload["country_code"]
        if "providerUuid" in payload:
            api_payload["provider_uuid"] = payload["providerUuid"]
        if "config_profile_uuid" in payload and "active_inbounds" in payload:
            api_payload["config_profile_uuid"] = payload["config_profile_uuid"]
            api_payload["active_inbounds"] = payload["active_inbounds"]
        if "traffic_limit_bytes" in payload:
            api_payload["traffic_limit_bytes"] = payload["traffic_limit_bytes"]
        if "notify_percent" in payload:
            api_payload["notifyPercent"] = payload["notify_percent"]
        if "traffic_reset_day" in payload:
            api_payload["trafficResetDay"] = payload["traffic_reset_day"]
        if "consumption_multiplier" in payload:
            api_payload["consumptionMultiplier"] = payload["consumption_multiplier"]
        if "tags" in payload:
            api_payload["tags"] = payload["tags"]

        await api_client.update_node(node_uuid, **api_payload)
        node = await api_client.get_node(node_uuid)
        info = node.get("response", node)
        is_disabled = bool(info.get("isDisabled"))
        text = _format_node_edit_snapshot(info, _)
        markup = node_edit_keyboard(node_uuid, is_disabled=is_disabled, back_to=back_to)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")
        else:
            await _send_clean_message(target, text, reply_markup=markup, parse_mode="Markdown")
    except UnauthorizedError:
        reply_markup = nodes_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("errors.unauthorized"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("errors.unauthorized"), reply_markup=reply_markup)
    except NotFoundError:
        reply_markup = nodes_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("node.not_found"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("node.not_found"), reply_markup=reply_markup)
    except ApiClientError:
        logger.exception("❌ Node update failed node_uuid=%s payload_keys=%s", node_uuid, list(payload.keys()))
        reply_markup = nodes_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("errors.generic"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("errors.generic"), reply_markup=reply_markup)


def _format_node_edit_snapshot(info: dict, t) -> str:
    """Форматирует снимок данных ноды для отображения при редактировании."""
    from src.utils.formatters import format_bytes, format_datetime

    lines = [f"*{t('node.edit_title')}*"]
    lines.append(f"  {t('node.edit_name')}: `{_esc(info.get('name', 'n/a'))}`")
    lines.append(f"  {t('node.edit_address')}: `{_esc(info.get('address', 'n/a'))}`")
    port = info.get("port")
    lines.append(f"  {t('node.edit_port')}: `{port if port else '—'}`")
    country = info.get("countryCode")
    lines.append(f"  {t('node.edit_country_code')}: `{country if country else '—'}`")
    provider = info.get("provider", {})
    provider_name = provider.get("name", "—") if provider else "—"
    lines.append(f"  {t('node.edit_provider')}: `{_esc(provider_name)}`")
    profile = info.get("configProfile", {})
    profile_name = profile.get("name", "—") if profile else "—"
    lines.append(f"  {t('node.edit_config_profile')}: `{_esc(profile_name)}`")
    traffic_limit = info.get("trafficLimitBytes")
    lines.append(f"  {t('node.edit_traffic_limit')}: `{format_bytes(traffic_limit) if traffic_limit else '—'}`")
    notify_percent = info.get("notifyPercent")
    lines.append(f"  {t('node.edit_notify_percent')}: `{notify_percent if notify_percent is not None else '—'}`")
    reset_day = info.get("trafficResetDay")
    lines.append(f"  {t('node.edit_traffic_reset_day')}: `{reset_day if reset_day else '—'}`")
    multiplier = info.get("consumptionMultiplier")
    lines.append(f"  {t('node.edit_consumption_multiplier')}: `{multiplier if multiplier else '—'}`")
    tags = info.get("tags", [])
    tags_str = ", ".join(tags) if tags else "—"
    lines.append(f"  {t('node.edit_tags')}: `{_esc(tags_str)}`")
    return "\n".join(lines)


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
                await _send_clean_message(message, _("node.prompt_name"), reply_markup=input_keyboard(action))
                PENDING_INPUT[user_id] = ctx
                return
            data["name"] = text
            ctx["stage"] = "address"
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(
                message,
                _("node.prompt_address").format(name=data["name"]),
                reply_markup=input_keyboard(action),
            )
            return

        elif stage == "address":
            if not text or len(text) < 2:
                await _send_clean_message(
                    message,
                    _("node.prompt_address").format(name=data.get("name", "")),
                    reply_markup=input_keyboard(action),
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
                    _("node.prompt_config_profile").format(name=data["name"], address=data["address"]),
                    reply_markup=keyboard,
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
                        parse_mode="Markdown",
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
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port=port_display,
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:country"),
            )
            return

        elif stage == "country":
            if text:
                if len(text) != 2:
                    await _send_clean_message(
                        message,
                        _("node.invalid_country"),
                        reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:country"),
                        parse_mode="Markdown",
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
                        name=data.get("name", ""),
                        address=data.get("address", ""),
                        port=str(data.get("port", "—")) if data.get("port") else "—",
                        country=country_display,
                        profile_name=data.get("profile_name", ""),
                        inbounds_count=len(data.get("selected_inbounds", [])),
                    ),
                    reply_markup=keyboard,
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
                        name=data.get("name", ""),
                        address=data.get("address", ""),
                        port=str(data.get("port", "—")) if data.get("port") else "—",
                        country=country_display,
                        provider="—",
                        profile_name=data.get("profile_name", ""),
                        inbounds_count=len(data.get("selected_inbounds", [])),
                    ),
                    reply_markup=_node_yes_no_keyboard("node_create", "traffic_tracking"),
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
                        parse_mode="Markdown",
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
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port=str(data.get("port", "—")) if data.get("port") else "—",
                    country=data.get("country_code", "—") or "—",
                    provider=data.get("provider_name", "—") or "—",
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=limit_display,
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:notify_percent"),
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
                        parse_mode="Markdown",
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
                    name=data.get("name", ""),
                    address=data.get("address", ""),
                    port=str(data.get("port", "—")) if data.get("port") else "—",
                    country=data.get("country_code", "—") or "—",
                    provider=data.get("provider_name", "—") or "—",
                    profile_name=data.get("profile_name", ""),
                    inbounds_count=len(data.get("selected_inbounds", [])),
                    tracking=_("node.yes") if data.get("is_traffic_tracking_active") else _("node.no"),
                    traffic_limit=format_bytes(data["traffic_limit_bytes"]) if data.get("traffic_limit_bytes") else "—",
                    notify_percent=percent_display,
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:traffic_reset_day"),
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
                        parse_mode="Markdown",
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
                    reset_day=day_display,
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:consumption_multiplier"),
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
                        parse_mode="Markdown",
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
                    multiplier=multiplier_display,
                ),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:tags"),
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
                        parse_mode="Markdown",
                    )
                    PENDING_INPUT[user_id] = ctx
                    return
                for tag in tags:
                    if not tag_pattern.match(tag) or len(tag) > 36:
                        await _send_clean_message(
                            message,
                            _("node.invalid_tags"),
                            reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:node_create:tags"),
                            parse_mode="Markdown",
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


async def _handle_node_edit_input(message: Message, ctx: dict) -> None:
    """Обработчик ввода значений при редактировании ноды."""
    import asyncio

    node_uuid = ctx.get("uuid")
    field = ctx.get("field")
    back_to = ctx.get("back_to", NavTarget.NODES_LIST)
    text = (message.text or "").strip()

    if not node_uuid or not field:
        await _send_clean_message(message, _("errors.generic"), reply_markup=nav_keyboard(back_to))
        return

    def _set_retry(prompt_key: str) -> None:
        PENDING_INPUT[message.from_user.id] = ctx
        asyncio.create_task(
            _send_clean_message(
                message,
                _(prompt_key),
                reply_markup=node_edit_keyboard(node_uuid, back_to=back_to),
            )
        )

    payload: dict[str, object | None] = {}

    if field == "name":
        if not text or len(text) < 3 or len(text) > 30:
            _set_retry("node.invalid_name")
            return
        payload["name"] = text
    elif field == "address":
        if not text:
            _set_retry("node.invalid_address")
            return
        payload["address"] = text
    elif field == "port":
        if text in {"", "-"}:
            payload["port"] = None
        else:
            try:
                port = int(text)
                if port < 1 or port > 65535:
                    raise ValueError
                payload["port"] = port
            except ValueError:
                _set_retry("node.invalid_port")
                return
    elif field == "country_code":
        if text in {"", "-"}:
            payload["country_code"] = None
        else:
            if len(text) != 2:
                _set_retry("node.invalid_country_code")
                return
            payload["country_code"] = text.upper()
    elif field == "traffic_limit":
        if text in {"", "-"}:
            payload["traffic_limit_bytes"] = None
        else:
            try:
                gb = float(text)
                if gb < 0:
                    raise ValueError
                payload["traffic_limit_bytes"] = int(gb * 1024 * 1024 * 1024)
            except ValueError:
                _set_retry("node.invalid_number")
                return
    elif field == "notify_percent":
        if text in {"", "-"}:
            payload["notify_percent"] = None
        else:
            try:
                percent = int(text)
                if percent < 0 or percent > 100:
                    raise ValueError
                payload["notify_percent"] = percent
            except ValueError:
                _set_retry("node.invalid_number")
                return
    elif field == "traffic_reset_day":
        if text in {"", "-"}:
            payload["traffic_reset_day"] = None
        else:
            try:
                day = int(text)
                if day < 1 or day > 31:
                    raise ValueError
                payload["traffic_reset_day"] = day
            except ValueError:
                _set_retry("node.invalid_number")
                return
    elif field == "consumption_multiplier":
        if text in {"", "-"}:
            payload["consumption_multiplier"] = None
        else:
            try:
                multiplier = float(text)
                if multiplier < 0:
                    raise ValueError
                payload["consumption_multiplier"] = multiplier
            except ValueError:
                _set_retry("node.invalid_multiplier")
                return
    elif field == "tags":
        if text in {"", "-"}:
            payload["tags"] = []
        else:
            tags = [tag.strip() for tag in text.split(",") if tag.strip()]
            payload["tags"] = tags
    else:
        await _send_clean_message(message, _("errors.generic"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))
        return

    await _apply_node_update(message, node_uuid, payload, back_to=back_to)


def _node_config_profiles_keyboard(profiles: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора профиля конфигурации при создании ноды."""
    rows: list[list[InlineKeyboardButton]] = []
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        name = profile.get("name", "n/a")
        uuid = profile.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"nodes:select_profile:{uuid}")])
    rows.append(nav_row(NavTarget.NODES_LIST))
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
        rows.append(
            [
                InlineKeyboardButton(
                    text=_("node.select_inbounds_done").format(count=len(selected)), callback_data="nodes:confirm_inbounds"
                )
            ]
        )

    rows.append(nav_row(NavTarget.NODES_LIST))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _bulk_nodes_select_keyboard(nodes: list[dict], selected: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора нод для массового изменения профилей."""
    rows: list[list[InlineKeyboardButton]] = []
    for node in nodes[:20]:  # Ограничиваем до 20 для удобства
        name = node.get("name", "n/a")
        uuid = node.get("uuid", "")
        is_selected = uuid in selected
        prefix = "✅ " if is_selected else "☐ "
        rows.append([InlineKeyboardButton(text=f"{prefix}{name}", callback_data=f"nodes:bulk_profile_toggle_node:{uuid}")])

    # Кнопка подтверждения выбора
    if selected:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_("node.select_inbounds_done").format(count=len(selected)),
                    callback_data="nodes:bulk_profile_confirm_nodes",
                )
            ]
        )

    rows.append(nav_row(NavTarget.NODES_LIST))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _bulk_profile_select_keyboard(profiles: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора профиля конфигурации для массового изменения."""
    rows: list[list[InlineKeyboardButton]] = []
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        name = profile.get("name", "n/a")
        uuid = profile.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"nodes:bulk_profile_select_profile:{uuid}")])
    rows.append(nav_row(NavTarget.NODES_LIST))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _bulk_profile_inbounds_keyboard(inbounds: list[dict], selected: list[str]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора инбаундов для массового изменения профилей."""
    rows: list[list[InlineKeyboardButton]] = []
    for inbound in inbounds[:20]:  # Ограничиваем до 20 для удобства
        name = inbound.get("remark") or inbound.get("tag") or "n/a"
        uuid = inbound.get("uuid", "")
        is_selected = uuid in selected
        prefix = "✅ " if is_selected else "☐ "
        rows.append([InlineKeyboardButton(text=f"{prefix}{name}", callback_data=f"nodes:bulk_profile_toggle_inbound:{uuid}")])

    # Кнопка подтверждения выбора
    if selected:
        rows.append(
            [
                InlineKeyboardButton(
                    text=_("node.select_inbounds_done").format(count=len(selected)), callback_data="nodes:bulk_profile_confirm"
                )
            ]
        )

    rows.append(nav_row(NavTarget.NODES_LIST))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _node_providers_keyboard(providers: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера при создании ноды."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"nodes:select_provider:{uuid}")])
    rows.append([InlineKeyboardButton(text=_("actions.skip_step"), callback_data="nodes:select_provider:none")])
    rows.append(nav_row(NavTarget.NODES_LIST))
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


async def _send_node_detail(target: Message | CallbackQuery, node_uuid: str, from_callback: bool = False) -> None:
    """Отправляет детальную информацию о ноде."""
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


@router.callback_query(F.data == "menu:nodes")
async def cb_nodes(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Ноды' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    from src.keyboards.nodes_menu import nodes_list_keyboard

    await callback.message.edit_text(_("bot.menu"), reply_markup=nodes_list_keyboard())


@router.callback_query(F.data.startswith("nodes:") | F.data.startswith("node_create:"))
async def cb_nodes_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с нодами."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    # Обрабатываем как nodes:action, так и node_create:action
    if callback.data.startswith("node_create:"):
        action = parts[1] if len(parts) > 1 else None
    else:
        action = parts[1] if len(parts) > 1 else None

    if action == "list":
        # Обновляем список нод
        try:
            text, keyboard = await _fetch_nodes_with_keyboard()
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as e:
                # Если сообщение не изменилось, просто показываем уведомление
                if "message is not modified" in str(e):
                    await callback.answer(_("node.list_updated"), show_alert=False)
                else:
                    raise
        except UnauthorizedError:
            from src.keyboards.nodes_menu import nodes_list_keyboard

            await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nodes_list_keyboard())
        except ApiClientError:
            logger.exception("❌ Nodes fetch failed")
            from src.keyboards.nodes_menu import nodes_list_keyboard

            await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_list_keyboard())
    elif action == "create":
        # Начинаем создание ноды
        PENDING_INPUT[callback.from_user.id] = {"action": "node_create", "stage": "name", "data": {}}
        await callback.message.edit_text(_("node.prompt_name"), reply_markup=input_keyboard("node_create"))
    elif action == "select_profile":
        # Выбор профиля конфигурации
        if len(parts) < 3:
            from src.keyboards.nodes_menu import nodes_list_keyboard

            await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_list_keyboard())
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
                    _("node.no_inbounds"), reply_markup=input_keyboard("node_create"), parse_mode="Markdown"
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
                    name=data.get("name", ""), address=data.get("address", ""), profile_name=data["profile_name"]
                ),
                reply_markup=keyboard,
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
                name=data.get("name", ""), address=data.get("address", ""), profile_name=data.get("profile_name", "")
            ),
            reply_markup=keyboard,
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
                name=data.get("name", ""),
                address=data.get("address", ""),
                profile_name=data.get("profile_name", ""),
                inbounds_count=len(selected),
            ),
            reply_markup=input_keyboard("node_create", allow_skip=True, skip_callback="input:skip:node_create:port"),
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
                name=data.get("name", ""),
                address=data.get("address", ""),
                port=str(data.get("port", "—")) if data.get("port") else "—",
                country=data.get("country_code", "—") or "—",
                provider=provider_name,
                profile_name=data.get("profile_name", ""),
                inbounds_count=len(data.get("selected_inbounds", [])),
            ),
            reply_markup=_node_yes_no_keyboard("node_create", "traffic_tracking"),
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
        data["is_traffic_tracking_active"] = value == "yes"
        ctx["stage"] = "traffic_limit"
        PENDING_INPUT[user_id] = ctx

        tracking_display = _("node.yes") if data["is_traffic_tracking_active"] else _("node.no")
        await callback.message.edit_text(
            _("node.prompt_traffic_limit").format(
                name=data.get("name", ""),
                address=data.get("address", ""),
                port=str(data.get("port", "—")) if data.get("port") else "—",
                country=data.get("country_code", "—") or "—",
                provider=data.get("provider_name", "—") or "—",
                profile_name=data.get("profile_name", ""),
                inbounds_count=len(data.get("selected_inbounds", [])),
                tracking=tracking_display,
            ),
            reply_markup=input_keyboard("node_create", allow_skip=True, skip_callback="input:skip:node_create:traffic_limit"),
        )
    elif action == "bulk_profile":
        # Начинаем массовое изменение профилей конфигурации
        try:
            # Получаем список нод для выбора
            nodes_data = await api_client.get_nodes()
            nodes = nodes_data.get("response", [])
            if not nodes:
                from src.keyboards.nodes_menu import nodes_list_keyboard

                await callback.message.edit_text(_("node.list_empty"), reply_markup=nodes_list_keyboard())
                return

            # Инициализируем состояние для массового изменения
            PENDING_INPUT[callback.from_user.id] = {
                "action": "nodes_bulk_profile",
                "stage": "select_nodes",
                "data": {"selected_nodes": [], "available_nodes": nodes},
            }

            # Показываем список нод для выбора
            keyboard = _bulk_nodes_select_keyboard(nodes, [])
            await callback.message.edit_text(_("node.bulk_profile_select_nodes"), reply_markup=keyboard)
        except Exception:
            logger.exception("Failed to start bulk profile modification")
            from src.keyboards.nodes_menu import nodes_list_keyboard

            await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_list_keyboard())
    elif action == "bulk_profile_toggle_node":
        # Переключение выбора ноды для массового изменения
        if len(parts) < 3:
            return
        node_uuid = parts[2]
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        selected = data.get("selected_nodes", [])
        available = data.get("available_nodes", [])

        if node_uuid in selected:
            selected.remove(node_uuid)
        else:
            selected.append(node_uuid)

        data["selected_nodes"] = selected
        PENDING_INPUT[user_id] = ctx

        # Обновляем клавиатуру
        keyboard = _bulk_nodes_select_keyboard(available, selected)
        await callback.message.edit_text(_("node.bulk_profile_select_nodes"), reply_markup=keyboard)
    elif action == "bulk_profile_confirm_nodes":
        # Подтверждение выбора нод
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        selected = data.get("selected_nodes", [])

        if not selected:
            await callback.answer(_("node.bulk_profile_select_nodes"), show_alert=True)
            return

        # Получаем список профилей конфигурации
        try:
            profiles_data = await api_client.get_config_profiles()
            profiles = profiles_data.get("response", {}).get("configProfiles", [])
            if not profiles:
                await callback.message.edit_text(_("node.no_profiles"), reply_markup=nodes_menu_keyboard())
                return

            ctx["stage"] = "select_profile"
            PENDING_INPUT[user_id] = ctx

            # Показываем список профилей
            keyboard = _bulk_profile_select_keyboard(profiles)
            await callback.message.edit_text(_("node.bulk_profile_select_profile"), reply_markup=keyboard)
        except Exception:
            logger.exception("Failed to get config profiles for bulk modification")
            await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_menu_keyboard())
    elif action == "bulk_profile_select_profile":
        # Выбор профиля конфигурации
        if len(parts) < 3:
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
                await callback.message.edit_text(_("node.no_inbounds"), reply_markup=nodes_menu_keyboard())
                return

            data["config_profile_uuid"] = profile_uuid
            data["profile_name"] = profile_info.get("name", "n/a")
            data["available_inbounds"] = inbounds
            data["selected_inbounds"] = []
            ctx["stage"] = "select_inbounds"
            PENDING_INPUT[user_id] = ctx

            # Показываем список инбаундов для выбора
            keyboard = _bulk_profile_inbounds_keyboard(inbounds, [])
            await callback.message.edit_text(_("node.bulk_profile_select_inbounds"), reply_markup=keyboard)
        except Exception:
            logger.exception("Failed to get profile inbounds for bulk modification")
            await callback.message.edit_text(_("errors.generic"), reply_markup=nodes_menu_keyboard())
    elif action == "bulk_profile_toggle_inbound":
        # Переключение выбора инбаунда для массового изменения
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
        keyboard = _bulk_profile_inbounds_keyboard(available, selected)
        await callback.message.edit_text(_("node.bulk_profile_select_inbounds"), reply_markup=keyboard)
    elif action == "bulk_profile_confirm":
        # Применение массового изменения профилей
        user_id = callback.from_user.id
        if user_id not in PENDING_INPUT:
            return
        ctx = PENDING_INPUT[user_id]
        data = ctx.setdefault("data", {})
        selected_nodes = data.get("selected_nodes", [])
        profile_uuid = data.get("config_profile_uuid")
        selected_inbounds = data.get("selected_inbounds", [])

        if not selected_nodes or not profile_uuid or not selected_inbounds:
            await callback.answer(_("errors.generic"), show_alert=True)
            return

        try:
            # Применяем массовое изменение
            await api_client.bulk_nodes_profile_modification(
                node_uuids=selected_nodes, profile_uuid=profile_uuid, inbound_uuids=selected_inbounds
            )

            # Очищаем состояние
            PENDING_INPUT.pop(user_id, None)

            # Показываем успешное сообщение
            from src.keyboards.nodes_menu import nodes_list_keyboard

            text = _("node.bulk_profile_success").format(count=len(selected_nodes))
            await callback.message.edit_text(text, reply_markup=nodes_list_keyboard())
        except UnauthorizedError:
            await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nodes_menu_keyboard())
        except ApiClientError:
            logger.exception("Failed to apply bulk profile modification")
            await callback.message.edit_text(_("node.bulk_profile_error"), reply_markup=nodes_menu_keyboard())
        finally:
            PENDING_INPUT.pop(user_id, None)


@router.callback_query(F.data.startswith("node_edit:"))
async def cb_node_edit_menu(callback: CallbackQuery) -> None:
    """Обработчик входа в меню редактирования ноды."""
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, node_uuid = callback.data.split(":")
    try:
        node = await api_client.get_node(node_uuid)
        info = node.get("response", node)
        summary = build_node_summary(node, _)
        is_disabled = bool(info.get("isDisabled"))
        await callback.message.edit_text(
            summary,
            reply_markup=node_edit_keyboard(node_uuid, is_disabled=is_disabled, back_to=NavTarget.NODES_LIST),
            parse_mode="HTML",
        )
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("node.not_found"), reply_markup=main_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Node edit menu failed node_uuid=%s actor_id=%s", node_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())


@router.callback_query(F.data.startswith("nef:"))
async def cb_node_edit_field(callback: CallbackQuery) -> None:
    """Обработчик редактирования полей ноды."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    # patterns: nef:{field}::{node_uuid} или nef:{field}:{value}:{node_uuid}
    if len(parts) < 3:
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())
        return
    _prefix, field = parts[0], parts[1]
    value = parts[2] if len(parts) > 3 and parts[2] else None
    node_uuid = parts[-1]
    back_to = NavTarget.NODES_LIST

    # Маппинг коротких префиксов на полные имена полей (для экономии байт в callback_data)
    field_mapping = {
        "cmult": "consumption_multiplier",
    }
    field = field_mapping.get(field, field)

    # Загружаем текущие данные ноды
    try:
        node = await api_client.get_node(node_uuid)
        info = node.get("response", node)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=main_menu_keyboard())
        return
    except NotFoundError:
        await callback.message.edit_text(_("node.not_found"), reply_markup=main_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("❌ Node edit fetch failed node_uuid=%s actor_id=%s", node_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=main_menu_keyboard())
        return

    # Специальные обработки для полей, требующих выбор из списка
    if field == "provider" and not value:
        # Показываем список провайдеров для выбора
        try:
            providers_data = await api_client.get_infra_providers()
            providers = providers_data.get("response", {}).get("providers", [])
            if not providers:
                await callback.message.edit_text(
                    _("node.no_providers"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to)
                )
                return
            keyboard = _node_providers_keyboard(providers)
            # Заменяем callback_data для редактирования (используем короткие callback для обхода 64-байтового лимита)
            for row in keyboard.inline_keyboard:
                for button in row:
                    if button.callback_data:
                        if button.callback_data.startswith("nodes:select_provider:"):
                            provider_uuid = button.callback_data.split(":")[-1]
                            button.callback_data = generate_short_callback(provider_uuid, node_uuid, "nef_prov")
                        elif button.callback_data == "nodes:select_provider:none":
                            button.callback_data = generate_short_callback("none", node_uuid, "nef_prov")
            await callback.message.edit_text(_("node.prompt_provider"), reply_markup=keyboard)
            return
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))
            return

    if field == "config_profile" and not value:
        # Показываем список профилей конфигурации для выбора
        try:
            profiles_data = await api_client.get_config_profiles()
            profiles = profiles_data.get("response", {}).get("configProfiles", [])
            if not profiles:
                await callback.message.edit_text(
                    _("node.no_config_profiles"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to)
                )
                return
            keyboard = _node_config_profiles_keyboard(profiles)
            # Заменяем callback_data для редактирования (используем короткие callback для обхода 64-байтового лимита)
            for row in keyboard.inline_keyboard:
                for button in row:
                    if button.callback_data and button.callback_data.startswith("nodes:select_profile:"):
                        profile_uuid = button.callback_data.split(":")[-1]
                        button.callback_data = generate_short_callback(profile_uuid, node_uuid, "nef_cfg")
            await callback.message.edit_text(_("node.prompt_config_profile"), reply_markup=keyboard)
            return
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))
            return

    # Если значение уже передано (например, выбор провайдера или профиля)
    if value and field in ("provider", "config_profile"):
        payload = {}
        if field == "provider":
            if value == "none":
                payload["providerUuid"] = None
            else:
                payload["providerUuid"] = value
        elif field == "config_profile":
            # Для профиля конфигурации нужно также получить инбаунды
            # Пока упростим - просто обновим профиль, инбаунды оставим как есть
            try:
                profile_data = await api_client.get_config_profile_computed(value)
                profile_info = profile_data.get("response", profile_data)
                inbounds = profile_info.get("inbounds", [])
                inbound_uuids = [i.get("uuid") for i in inbounds if i.get("uuid")]
                if inbound_uuids:
                    payload["config_profile_uuid"] = value
                    payload["active_inbounds"] = inbound_uuids
            except Exception:
                await callback.message.edit_text(_("errors.generic"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))
                return

        if payload:
            await _apply_node_update(callback, node_uuid, payload, back_to)
        return

    # Для остальных полей показываем промпт для ввода
    current_values = {
        "name": info.get("name", ""),
        "address": info.get("address", ""),
        "port": str(info.get("port", "")) if info.get("port") else "",
        "country_code": info.get("countryCode", ""),
        "traffic_limit": format_bytes(info.get("trafficLimitBytes")) if info.get("trafficLimitBytes") else "",
        "notify_percent": str(info.get("notifyPercent", "")) if info.get("notifyPercent") else "",
        "traffic_reset_day": str(info.get("trafficResetDay", "")) if info.get("trafficResetDay") else "",
        "consumption_multiplier": str(info.get("consumptionMultiplier", "")) if info.get("consumptionMultiplier") else "",
        "tags": ", ".join(info.get("tags", [])) if info.get("tags") else "",
    }

    prompt_map = {
        "name": _("node.edit_prompt_name"),
        "address": _("node.edit_prompt_address"),
        "port": _("node.edit_prompt_port"),
        "country_code": _("node.edit_prompt_country_code"),
        "traffic_limit": _("node.edit_prompt_traffic_limit"),
        "notify_percent": _("node.edit_prompt_notify_percent"),
        "traffic_reset_day": _("node.edit_prompt_traffic_reset_day"),
        "consumption_multiplier": _("node.edit_prompt_consumption_multiplier"),
        "tags": _("node.edit_prompt_tags"),
    }
    prompt = prompt_map.get(field, _("errors.generic"))
    if prompt == _("errors.generic"):
        await callback.message.edit_text(prompt, reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))
        return

    current_line = _("user.current").format(value=current_values.get(field, _("user.not_set")))
    prompt = f"{prompt}\n{current_line}"

    PENDING_INPUT[callback.from_user.id] = {
        "action": "node_edit",
        "field": field,
        "uuid": node_uuid,
        "back_to": back_to,
    }
    await callback.message.edit_text(
        prompt,
        reply_markup=input_keyboard("node_edit", allow_skip=True, skip_callback=f"nef:skip:{node_uuid}:{field}"),
    )


@router.callback_query(F.data.startswith("node_delete:"))
async def cb_node_delete(callback: CallbackQuery) -> None:
    """Обработчик удаления ноды с подтверждением."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return

    node_uuid = parts[1]
    back_to = NavTarget.NODES_LIST

    try:
        # Получаем информацию о ноде для подтверждения
        node = await api_client.get_node(node_uuid)
        node_info = node.get("response", node)
        node_name = node_info.get("name", "n/a")

        # Показываем подтверждение удаления
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text=_("node.delete_confirm_yes"), callback_data=f"node_delete_confirm:{node_uuid}"
                    ),
                    InlineKeyboardButton(text=_("node.delete_confirm_no"), callback_data=f"node_edit:{node_uuid}"),
                ],
                nav_row(back_to),
            ]
        )
        text = _("node.delete_confirm").format(name=_esc(node_name))
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("node.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to get node for delete confirmation node_uuid=%s actor_id=%s", node_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("node_delete_confirm:"))
async def cb_node_delete_confirm(callback: CallbackQuery) -> None:
    """Обработчик подтверждения удаления ноды."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        return

    node_uuid = parts[1]
    back_to = NavTarget.NODES_LIST

    try:
        # Получаем информацию о ноде перед удалением
        node = await api_client.get_node(node_uuid)
        node_info = node.get("response", node)
        node_name = node_info.get("name", "n/a")

        # Удаляем ноду
        await api_client.delete_node(node_uuid)

        # Показываем сообщение об успешном удалении
        text = _("node.deleted").format(name=_esc(node_name))
        keyboard = InlineKeyboardMarkup(inline_keyboard=[nav_row(back_to)])
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=nav_keyboard(back_to))
    except NotFoundError:
        await callback.message.edit_text(_("node.not_found"), reply_markup=nav_keyboard(back_to))
    except ApiClientError:
        logger.exception("Failed to delete node node_uuid=%s actor_id=%s", node_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=nav_keyboard(back_to))


@router.callback_query(F.data.startswith("node:"))
async def cb_node_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с нодой (enable, disable, restart, reset)."""
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


@router.callback_query(F.data.startswith("nef_prov:"))
async def cb_node_provider_short(callback: CallbackQuery) -> None:
    """Обработчик выбора provider через короткий callback (для обхода 64-байтового лимита)."""
    if await _not_admin(callback):
        return
    await callback.answer()

    result = resolve_short_callback(callback.data)
    if not result:
        await callback.answer(_("errors.generic"), show_alert=True)
        return

    provider_uuid, node_uuid, _ = result
    back_to = NavTarget.NODES_LIST

    # Обновляем provider ноды
    payload = {}
    if provider_uuid == "none":
        payload["providerUuid"] = None
    else:
        payload["providerUuid"] = provider_uuid

    await _apply_node_update(callback, node_uuid, payload, back_to)


@router.callback_query(F.data.startswith("nef_cfg:"))
async def cb_node_config_profile_short(callback: CallbackQuery) -> None:
    """Обработчик выбора config profile через короткий callback (для обхода 64-байтового лимита)."""
    if await _not_admin(callback):
        return
    await callback.answer()

    result = resolve_short_callback(callback.data)
    if not result:
        await callback.answer(_("errors.generic"), show_alert=True)
        return

    profile_uuid, node_uuid, _ = result
    back_to = NavTarget.NODES_LIST

    # Для профиля конфигурации нужно также получить инбаунды
    try:
        profile_data = await api_client.get_config_profile_computed(profile_uuid)
        profile_info = profile_data.get("response", profile_data)
        inbounds = profile_info.get("inbounds", [])
        inbound_uuids = [i.get("uuid") for i in inbounds if i.get("uuid")]
        if inbound_uuids:
            payload = {
                "config_profile_uuid": profile_uuid,
                "active_inbounds": inbound_uuids
            }
            await _apply_node_update(callback, node_uuid, payload, back_to)
        else:
            await callback.message.edit_text(_("errors.generic"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))
    except (ApiClientError, UnauthorizedError, NotFoundError):
        logger.exception("❌ Failed to update node config profile node_uuid=%s profile_uuid=%s", node_uuid, profile_uuid)
        await callback.message.edit_text(_("errors.generic"), reply_markup=node_edit_keyboard(node_uuid, back_to=back_to))

