"""Обработчики для работы с хостами."""
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin, _send_clean_message
from src.handlers.state import PENDING_INPUT
from src.keyboards.host_actions import host_actions_keyboard
from src.keyboards.host_edit import host_edit_keyboard
from src.keyboards.hosts_menu import hosts_menu_keyboard
from src.keyboards.main_menu import main_menu_keyboard
from src.keyboards.navigation import NavTarget, input_keyboard, nav_keyboard, nav_row
from src.services.api_client import ApiClientError, NotFoundError, UnauthorizedError, api_client
from src.utils.formatters import build_host_summary
from src.utils.logger import logger

# Функции перенесены из basic.py

router = Router(name="hosts")


def _host_config_profiles_keyboard(profiles: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора профиля конфигурации при создании хоста."""
    rows: list[list[InlineKeyboardButton]] = []
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        name = profile.get("name", "n/a")
        uuid = profile.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"hosts:select_profile:{uuid}")])
    rows.append(nav_row(NavTarget.HOSTS_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _host_inbounds_keyboard(inbounds: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора инбаунда при создании хоста."""
    rows: list[list[InlineKeyboardButton]] = []
    for inbound in inbounds[:20]:  # Ограничиваем до 20 для удобства
        name = inbound.get("remark") or inbound.get("tag") or "n/a"
        uuid = inbound.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"hosts:select_inbound:{uuid}")])
    rows.append(nav_row(NavTarget.HOSTS_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _fetch_hosts_text() -> str:
    """Получает текст со списком хостов."""
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
            line = _("host.list_item").format(
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


async def _fetch_hosts_with_keyboard() -> tuple[str, InlineKeyboardMarkup]:
    """Получает список хостов с клавиатурой для редактирования."""
    try:
        data = await api_client.get_hosts()
        hosts = data.get("response", [])
        if not hosts:
            return _("host.list_empty"), InlineKeyboardMarkup(inline_keyboard=[nav_row(NavTarget.HOSTS_MENU)])

        sorted_hosts = sorted(hosts, key=lambda h: h.get("viewPosition", 0))

        # Вычисляем статистику
        total_hosts = len(hosts)
        enabled_hosts = sum(1 for h in hosts if not h.get("isDisabled"))
        disabled_hosts = total_hosts - enabled_hosts

        # Формируем текст со статистикой и списком хостов
        lines = [
            _("host.list_title").format(total=total_hosts),
            "",
            f"✅ Включено: {enabled_hosts} | ⛔️ Выключено: {disabled_hosts}",
            "",
        ]

        rows: list[list[InlineKeyboardButton]] = []

        for host in sorted_hosts[:20]:
            status = "DISABLED" if host.get("isDisabled") else "ENABLED"
            status_emoji = "🟡" if status == "DISABLED" else "🟢"
            address = f"{host.get('address', 'n/a')}:{host.get('port', '—')}"
            remark = host.get("remark", "n/a")
            tag = host.get("tag", "—")

            line = _("host.list_item").format(
                statusEmoji=status_emoji,
                remark=remark,
                address=address,
                tag=tag,
            )
            lines.append(line)

            # Добавляем кнопку для редактирования хоста
            rows.append([InlineKeyboardButton(text=f"{status_emoji} {remark}", callback_data=f"host_edit:{host.get('uuid', '')}")])

        if len(hosts) > 20:
            lines.append(_("host.list_more").format(count=len(hosts) - 20))

        # Добавляем только кнопку "Назад" к списку хостов
        rows.append(nav_row(NavTarget.HOSTS_MENU))

        keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
        return "\n".join(lines), keyboard
    except UnauthorizedError:
        return _("errors.unauthorized"), InlineKeyboardMarkup(inline_keyboard=[nav_row(NavTarget.HOSTS_MENU)])
    except ApiClientError:
        logger.exception("⚠️ Hosts fetch failed")
        return _("errors.generic"), InlineKeyboardMarkup(inline_keyboard=[nav_row(NavTarget.HOSTS_MENU)])


async def _send_host_detail(target: Message | CallbackQuery, host_uuid: str, from_callback: bool = False) -> None:
    """Отправляет детальную информацию о хосте."""
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


async def _handle_host_create_input(message: Message, ctx: dict) -> None:
    """Обработчик пошагового ввода для создания хоста."""
    action = ctx.get("action")
    user_id = message.from_user.id
    text = message.text.strip()
    data = ctx.setdefault("data", {})
    stage = ctx.get("stage", None)

    try:
        if stage == "remark":
            if not text or len(text) < 1:
                await _send_clean_message(message, _("host.prompt_remark"), reply_markup=input_keyboard(action))
                PENDING_INPUT[user_id] = ctx
                return
            data["remark"] = text
            ctx["stage"] = "address"
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(
                message,
                _("host.prompt_address").format(remark=data["remark"]),
                reply_markup=input_keyboard(action),
            )
            return

        elif stage == "address":
            if not text or len(text) < 2:
                await _send_clean_message(
                    message,
                    _("host.prompt_address").format(remark=data.get("remark", "")),
                    reply_markup=input_keyboard(action),
                )
                PENDING_INPUT[user_id] = ctx
                return
            data["address"] = text
            ctx["stage"] = "port"
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(
                message,
                _("host.prompt_port").format(remark=data["remark"], address=data["address"]),
                reply_markup=input_keyboard(action),
            )
            return

        elif stage == "port":
            try:
                port = int(text)
                if port < 1 or port > 65535:
                    raise ValueError
                data["port"] = port
            except ValueError:
                await _send_clean_message(message, _("host.invalid_port"), reply_markup=input_keyboard(action))
                PENDING_INPUT[user_id] = ctx
                return
            ctx["stage"] = "tag"
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(
                message,
                _("host.prompt_tag").format(remark=data["remark"], address=data["address"], port=data["port"]),
                reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:host_create:tag"),
            )
            return

        elif stage == "tag":
            data["tag"] = text if text else None
            ctx["stage"] = "config_profile"
            PENDING_INPUT[user_id] = ctx
            # Показываем список профилей конфигурации для выбора
            try:
                profiles_data = await api_client.get_config_profiles()
                profiles = profiles_data.get("response", {}).get("configProfiles", [])
                if not profiles:
                    await _send_clean_message(message, _("host.no_config_profiles"), reply_markup=input_keyboard(action))
                    PENDING_INPUT[user_id] = ctx
                    return
                keyboard = _host_config_profiles_keyboard(profiles)
                await _send_clean_message(message, _("host.prompt_config_profile"), reply_markup=keyboard)
            except Exception:
                logger.exception("❌ Failed to load config profiles for host creation")
                await _send_clean_message(message, _("errors.generic"), reply_markup=hosts_menu_keyboard())
                PENDING_INPUT.pop(user_id, None)
            return

    except Exception as e:
        logger.exception("❌ Host create input error")
        PENDING_INPUT.pop(user_id, None)
        await _send_clean_message(message, _("errors.generic"), reply_markup=hosts_menu_keyboard())


async def _send_host_detail(target: Message | CallbackQuery, host_uuid: str, from_callback: bool = False) -> None:
    """Отправляет детальную информацию о хосте."""
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


async def _apply_host_update(target: Message | CallbackQuery, host_uuid: str, payload: dict, back_to: str) -> None:
    """Применяет обновление хоста."""
    try:
        await api_client.update_host(host_uuid, **payload)
        host = await api_client.get_host(host_uuid)
        summary = build_host_summary(host, _)
        markup = host_edit_keyboard(host_uuid, back_to=back_to)
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(summary, reply_markup=markup)
        else:
            await _send_clean_message(target, summary, reply_markup=markup)
    except UnauthorizedError:
        reply_markup = hosts_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("errors.unauthorized"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("errors.unauthorized"), reply_markup=reply_markup)
    except NotFoundError:
        reply_markup = hosts_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("host.not_found"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("host.not_found"), reply_markup=reply_markup)
    except ApiClientError:
        logger.exception("❌ Host update failed host_uuid=%s payload_keys=%s", host_uuid, list(payload.keys()))
        reply_markup = hosts_menu_keyboard()
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(_("errors.generic"), reply_markup=reply_markup)
        else:
            await _send_clean_message(target, _("errors.generic"), reply_markup=reply_markup)


@router.callback_query(F.data == "menu:hosts")
async def cb_hosts(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Хосты' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_hosts_text()
    await callback.message.edit_text(text, reply_markup=hosts_menu_keyboard())


@router.callback_query(F.data == "hosts:create")
async def cb_hosts_create(callback: CallbackQuery) -> None:
    """Обработчик создания хоста."""
    if await _not_admin(callback):
        return
    await callback.answer()
    user_id = callback.from_user.id

    # Инициализируем контекст для создания хоста
    ctx = {
        "action": "host_create",
        "stage": "remark",
        "data": {},
        "bot_chat_id": callback.message.chat.id,
        "bot_message_id": callback.message.message_id,
    }
    PENDING_INPUT[user_id] = ctx

    await callback.message.edit_text(_("host.prompt_remark"), reply_markup=input_keyboard("host_create"))


@router.callback_query(F.data.startswith("hosts:select_profile:"))
async def cb_hosts_select_profile(callback: CallbackQuery) -> None:
    """Обработчик выбора профиля конфигурации для хоста."""
    if await _not_admin(callback):
        return
    await callback.answer()
    user_id = callback.from_user.id
    ctx = PENDING_INPUT.get(user_id)
    if not ctx or ctx.get("action") != "host_create":
        await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())
        return

    profile_uuid = callback.data.split(":")[-1]
    data = ctx.setdefault("data", {})
    data["config_profile_uuid"] = profile_uuid
    ctx["stage"] = "inbound"
    PENDING_INPUT[user_id] = ctx

    # Загружаем инбаунды профиля
    try:
        profile_data = await api_client.get_config_profile_computed(profile_uuid)
        profile_info = profile_data.get("response", profile_data)
        inbounds = profile_info.get("inbounds", [])
        if not inbounds:
            await callback.message.edit_text(_("host.no_inbounds"), reply_markup=input_keyboard("host_create"))
            PENDING_INPUT[user_id] = ctx
            return
        keyboard = _host_inbounds_keyboard(inbounds)
        await callback.message.edit_text(_("host.prompt_inbound"), reply_markup=keyboard)
    except Exception:
        logger.exception("❌ Failed to load inbounds for host creation")
        await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())
        PENDING_INPUT.pop(user_id, None)


@router.callback_query(F.data.startswith("hosts:select_inbound:"))
async def cb_hosts_select_inbound(callback: CallbackQuery) -> None:
    """Обработчик выбора инбаунда для хоста."""
    if await _not_admin(callback):
        return
    await callback.answer()
    user_id = callback.from_user.id
    ctx = PENDING_INPUT.get(user_id)
    if not ctx or ctx.get("action") != "host_create":
        await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())
        return

    inbound_uuid = callback.data.split(":")[-1]
    data = ctx.setdefault("data", {})
    data["config_profile_inbound_uuid"] = inbound_uuid

    # Создаем хост
    try:
        await api_client.create_host(
            remark=data["remark"],
            address=data["address"],
            port=data["port"],
            config_profile_uuid=data["config_profile_uuid"],
            config_profile_inbound_uuid=data["config_profile_inbound_uuid"],
            tag=data.get("tag"),
        )
        PENDING_INPUT.pop(user_id, None)
        hosts_text = await _fetch_hosts_text()
        await callback.message.edit_text(hosts_text, reply_markup=hosts_menu_keyboard())
    except UnauthorizedError:
        PENDING_INPUT.pop(user_id, None)
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=hosts_menu_keyboard())
    except ApiClientError:
        PENDING_INPUT.pop(user_id, None)
        logger.exception("❌ Host creation failed")
        await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())


@router.callback_query(F.data.startswith("hosts:"))
async def cb_hosts_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с хостами."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else None

    if action == "list":
        # Обновляем список хостов
        try:
            text, keyboard = await _fetch_hosts_with_keyboard()
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as e:
                # Если сообщение не изменилось, просто показываем уведомление
                if "message is not modified" in str(e):
                    await callback.answer(_("host.list_updated"), show_alert=False)
                else:
                    raise
        except UnauthorizedError:
            await callback.message.edit_text(_("errors.unauthorized"), reply_markup=hosts_menu_keyboard())
        except ApiClientError:
            logger.exception("❌ Hosts fetch failed")
            await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())
    elif action == "update":
        # Показываем список хостов для выбора
        try:
            text, keyboard = await _fetch_hosts_with_keyboard()
            await callback.message.edit_text(text, reply_markup=keyboard)
        except UnauthorizedError:
            await callback.message.edit_text(_("errors.unauthorized"), reply_markup=hosts_menu_keyboard())
        except ApiClientError:
            logger.exception("❌ Hosts fetch failed")
            await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())


@router.callback_query(F.data.startswith("host_edit:"))
async def cb_host_edit_menu(callback: CallbackQuery) -> None:
    """Обработчик входа в меню редактирования хоста."""
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, host_uuid = callback.data.split(":")
    try:
        host = await api_client.get_host(host_uuid)
        summary = build_host_summary(host, _)
        await callback.message.edit_text(
            summary,
            reply_markup=host_edit_keyboard(host_uuid, back_to=NavTarget.HOSTS_MENU),
        )
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=hosts_menu_keyboard())
    except NotFoundError:
        await callback.message.edit_text(_("host.not_found"), reply_markup=hosts_menu_keyboard())
    except ApiClientError:
        logger.exception("❌ Host edit menu failed host_uuid=%s actor_id=%s", host_uuid, callback.from_user.id)
        await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())


@router.callback_query(F.data.startswith("hef:"))
async def cb_host_edit_field(callback: CallbackQuery) -> None:
    """Обработчик редактирования полей хоста."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    # patterns: hef:{field}::{host_uuid} или hef:{field}:{value}:{host_uuid}
    if len(parts) < 3:
        await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())
        return
    _prefix, field = parts[0], parts[1]
    value = parts[2] if len(parts) > 3 and parts[2] else None
    host_uuid = parts[-1]
    back_to = NavTarget.HOSTS_MENU

    # Загружаем текущие данные хоста
    try:
        host = await api_client.get_host(host_uuid)
        info = host.get("response", host)
    except UnauthorizedError:
        await callback.message.edit_text(_("errors.unauthorized"), reply_markup=hosts_menu_keyboard())
        return
    except NotFoundError:
        await callback.message.edit_text(_("host.not_found"), reply_markup=hosts_menu_keyboard())
        return
    except ApiClientError:
        logger.exception("❌ Failed to fetch host for edit host_uuid=%s", host_uuid)
        await callback.message.edit_text(_("errors.generic"), reply_markup=hosts_menu_keyboard())
        return

    # Если значение уже передано (например, выбор инбаунда)
    if value and field == "inbound":
        # Обновляем хост с новым инбаундом
        try:
            # Получаем текущий профиль конфигурации хоста
            inbound_info = info.get("inbound", {})
            config_profile_uuid = inbound_info.get("configProfileUuid")

            if not config_profile_uuid:
                await callback.message.edit_text(
                    _("host.no_config_profiles"),
                    reply_markup=host_edit_keyboard(host_uuid, back_to=back_to),
                )
                return

            # Обновляем хост с новым инбаундом
            await _apply_host_update(
                callback,
                host_uuid,
                {
                    "inbound": {
                        "configProfileUuid": config_profile_uuid,
                        "configProfileInboundUuid": value,
                    }
                },
                back_to=back_to,
            )
        except Exception:
            logger.exception("❌ Failed to update host inbound")
            await callback.message.edit_text(_("errors.generic"), reply_markup=host_edit_keyboard(host_uuid, back_to=back_to))
        return

    # Показываем промпт для ввода нового значения
    user_id = callback.from_user.id
    ctx = {
        "action": "host_edit",
        "field": field,
        "uuid": host_uuid,
        "back_to": back_to,
        "bot_chat_id": callback.message.chat.id,
        "bot_message_id": callback.message.message_id,
    }
    PENDING_INPUT[user_id] = ctx

    prompt = ""
    if field == "remark":
        prompt = _("host.edit_prompt_remark")
    elif field == "address":
        prompt = _("host.edit_prompt_address")
    elif field == "port":
        prompt = _("host.edit_prompt_port")
    elif field == "tag":
        prompt = _("host.edit_prompt_tag")
    elif field == "inbound":
        # Показываем список инбаундов для выбора
        try:
            # Получаем текущий профиль конфигурации хоста
            inbound_info = info.get("inbound", {})
            config_profile_uuid = inbound_info.get("configProfileUuid")
            if not config_profile_uuid:
                await callback.message.edit_text(
                    _("host.no_config_profiles"),
                    reply_markup=host_edit_keyboard(host_uuid, back_to=back_to),
                )
                return

            profile_data = await api_client.get_config_profile_computed(config_profile_uuid)
            profile_info = profile_data.get("response", profile_data)
            inbounds = profile_info.get("inbounds", [])
            if not inbounds:
                await callback.message.edit_text(
                    _("host.no_inbounds"),
                    reply_markup=host_edit_keyboard(host_uuid, back_to=back_to),
                )
                return
            keyboard = _host_inbounds_keyboard(inbounds)
            # Заменяем callback_data для редактирования
            for row in keyboard.inline_keyboard:
                for button in row:
                    if button.callback_data and button.callback_data.startswith("hosts:select_inbound:"):
                        inbound_uuid = button.callback_data.split(":")[-1]
                        button.callback_data = f"hef:inbound:{inbound_uuid}:{host_uuid}"
            await callback.message.edit_text(_("host.edit_prompt_inbound"), reply_markup=keyboard)
            return
        except Exception:
            logger.exception("❌ Failed to load inbounds for host edit")
            await callback.message.edit_text(_("errors.generic"), reply_markup=host_edit_keyboard(host_uuid, back_to=back_to))
            return
    else:
        await callback.message.edit_text(_("errors.generic"), reply_markup=host_edit_keyboard(host_uuid, back_to=back_to))
        return

    await callback.message.edit_text(prompt, reply_markup=input_keyboard("host_edit", allow_skip=(field == "tag")))


@router.callback_query(F.data.startswith("host:"))
async def cb_host_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с хостом (enable, disable)."""
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

