"""Обработчики для работы с ресурсами (токены, шаблоны, сниппеты, конфиги)."""
import json

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin, _send_clean_message
from src.handlers.state import PENDING_INPUT
from src.keyboards.main_menu import main_menu_keyboard, nodes_menu_keyboard, resources_menu_keyboard
from src.keyboards.navigation import NavTarget
from src.keyboards.snippet_actions import snippet_actions_keyboard
from src.keyboards.template_actions import template_actions_keyboard
from src.keyboards.template_menu import template_list_keyboard, template_menu_keyboard
from src.keyboards.token_actions import token_actions_keyboard
from src.services.api_client import ApiClientError, NotFoundError, UnauthorizedError, api_client
from src.utils.formatters import (
    build_config_profiles_list,
    build_created_token,
    build_snippet_detail,
    build_snippets_list,
    build_template_summary,
    build_templates_list,
    build_tokens_list,
)
from src.utils.logger import logger

# Функции перенесены из basic.py

router = Router(name="resources")


async def _show_tokens(target: Message | CallbackQuery, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    """Показывает список токенов."""
    text = await _fetch_tokens_text()
    markup = reply_markup or main_menu_keyboard()
    if isinstance(target, CallbackQuery):
        await _edit_text_safe(target.message, text, reply_markup=markup)
    else:
        await _send_clean_message(target, text, reply_markup=markup)


async def _create_token(target: Message | CallbackQuery, name: str) -> None:
    """Создает новый токен."""
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


async def _send_templates(target: Message | CallbackQuery) -> None:
    """Отправляет список шаблонов."""
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


async def _send_template_detail(target: Message | CallbackQuery, tpl_uuid: str) -> None:
    """Отправляет детальную информацию о шаблоне."""
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


async def _send_snippet_detail(target: Message | CallbackQuery, name: str) -> None:
    """Отправляет детальную информацию о сниппете."""
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
    """Создает или обновляет сниппет."""
    parts = target.text.split(maxsplit=2)
    if len(parts) < 3:
        await _send_clean_message(target, _("snippet.usage"))
        return
    name = parts[1].strip()
    raw_json = parts[2].strip()
    try:
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


async def _fetch_tokens_text() -> str:
    """Получает текст со списком токенов."""
    try:
        data = await api_client.get_tokens()
        logger.debug("Tokens API response keys: %s", list(data.keys()) if isinstance(data, dict) else "not a dict")

        # Пробуем разные варианты структуры ответа
        tokens = None
        if isinstance(data, dict):
            # Стандартная структура: response.apiKeys
            tokens = data.get("response", {}).get("apiKeys")
            if tokens is None:
                # Альтернативная структура: apiKeys напрямую
                tokens = data.get("apiKeys")
            if tokens is None and "response" in data:
                # Если response есть, но не словарь
                response = data.get("response")
                if isinstance(response, list):
                    tokens = response
                elif isinstance(response, dict):
                    tokens = response.get("apiKeys") or response.get("tokens")

        if tokens is None:
            tokens = []

        if not isinstance(tokens, list):
            logger.error("Tokens is not a list: %s (type: %s)", tokens, type(tokens))
            tokens = []

        logger.info("Fetched %d tokens", len(tokens))
        return build_tokens_list(tokens, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError as exc:
        logger.exception("⚠️ Tokens fetch failed: %s", exc)
        return _("errors.generic")


async def _fetch_templates_text() -> str:
    """Получает текст со списком шаблонов."""
    try:
        data = await api_client.get_templates()
        templates = data.get("response", {}).get("templates", [])
        return build_templates_list(templates, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Templates fetch failed")
        return _("errors.generic")


async def _fetch_snippets_text() -> str:
    """Получает текст со списком сниппетов."""
    try:
        data = await api_client.get_snippets()
        snippets = data.get("response", {}).get("snippets", [])
        return build_snippets_list(snippets, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Snippets fetch failed")
        return _("errors.generic")


async def _fetch_configs_text() -> str:
    """Получает текст со списком профилей конфигурации."""
    try:
        data = await api_client.get_config_profiles()
        profiles = data.get("response", {}).get("configProfiles", [])
        return build_config_profiles_list(profiles, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Config profiles fetch failed")
        return _("errors.generic")


async def _handle_template_create_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод для создания шаблона."""
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
    """Обрабатывает ввод JSON для обновления шаблона."""
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
    """Обрабатывает ввод для изменения порядка шаблонов."""
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


async def _send_config_detail(target: Message | CallbackQuery, config_uuid: str) -> None:
    """Отправляет детальную информацию о профиле конфигурации."""
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
        logger.exception("⚠️ API client error while fetching config profile")
        text = _("errors.generic")
        if isinstance(target, CallbackQuery):
            await target.message.edit_text(text, reply_markup=main_menu_keyboard())
        else:
            await _send_clean_message(target, text, reply_markup=main_menu_keyboard())
        return

    summary = build_config_profiles_list([profile.get("response", profile)], _)
    if isinstance(target, CallbackQuery):
        await target.message.edit_text(summary, reply_markup=nodes_menu_keyboard())
    else:
        await _send_clean_message(target, summary, reply_markup=nodes_menu_keyboard())


@router.callback_query(F.data == "menu:tokens")
async def cb_tokens(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Токены' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _show_tokens(callback, reply_markup=resources_menu_keyboard())


@router.callback_query(F.data.startswith("token:"))
async def cb_token_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с токеном."""
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


@router.callback_query(F.data == "menu:templates")
async def cb_templates(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Шаблоны' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _send_templates(callback)


@router.callback_query(F.data.startswith("template:"))
async def cb_template_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с шаблоном."""
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
    """Обработчик просмотра шаблона."""
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


@router.callback_query(F.data == "menu:snippets")
async def cb_snippets(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Сниппеты' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_snippets_text()
    await _edit_text_safe(callback.message, text, reply_markup=resources_menu_keyboard())


@router.callback_query(F.data.startswith("snippet:"))
async def cb_snippet_actions(callback: CallbackQuery) -> None:
    """Обработчик действий со сниппетом."""
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


@router.callback_query(F.data == "menu:configs")
async def cb_configs(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Конфиги' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_configs_text()
    await callback.message.edit_text(text, reply_markup=nodes_menu_keyboard())


@router.callback_query(F.data.startswith("config:"))
async def cb_config_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с конфигом."""
    if await _not_admin(callback):
        return
    await callback.answer()
    _prefix, config_uuid, action = callback.data.split(":")
    if action != "view":
        await callback.answer(_("errors.generic"), show_alert=True)
        return
    await _send_config_detail(callback, config_uuid)

