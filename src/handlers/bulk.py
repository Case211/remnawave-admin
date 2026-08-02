"""Обработчики для массовых операций."""
import asyncio

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin, require_permission, _send_clean_message
from src.handlers.state import PENDING_INPUT, SEARCH_PAGE_SIZE
from src.keyboards.bulk_hosts import bulk_hosts_keyboard
from src.keyboards.bulk_nodes import bulk_nodes_keyboard
from src.keyboards.bulk_users import bulk_users_keyboard
from src.utils.auth import BotAdmin
from shared.internal_api import ApiClientError, UnauthorizedError, internal_api_client
from shared.database import db_service
from shared.logger import logger
from shared.admin_quota import (
    apply_users_delete_quotas_batch,
    apply_users_reset_traffic_quotas_batch,
    fetch_users_quota_data_batch,
)
from src.utils.notifications import send_user_notification

from src.handlers.hosts import _fetch_hosts_text

router = Router(name="bulk")

# Разрешенные статусы для массовых операций
ALLOWED_STATUSES = {"ACTIVE", "DISABLED", "LIMITED", "EXPIRED"}


def _parse_uuids(text: str, expected_min: int = 1) -> list[str]:
    """Парсит UUID из текста команды."""
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
    admin: BotAdmin | None = None,
) -> None:
    """Выполняет массовую операцию над пользователями."""
    try:
        if action == "reset":
            # Apply quota counter changes via shared helper
            if uuids:
                try:
                    # Fetch used_traffic_bytes BEFORE the reset so the counter
                    # is incremented by the correct amount.
                    users_data = await fetch_users_quota_data_batch(uuids)
                    await internal_api_client.bulk_reset_traffic_users(uuids or [])
                    await apply_users_reset_traffic_quotas_batch(users_data)
                except Exception:
                    logger.debug("Failed to update usage counters on bulk reset")
            else:
                await internal_api_client.bulk_reset_traffic_users([])
        elif action == "delete":
            # Получаем информацию о пользователях перед удалением для уведомлений
            users_to_notify = []
            if uuids:
                for user_uuid in uuids:
                    try:
                        user = await internal_api_client.get_user_by_id(user_uuid)
                        users_to_notify.append(user)
                    except Exception:
                        logger.debug("Failed to get user data for notification user_uuid=%s", user_uuid)
            
            await internal_api_client.bulk_delete_users(uuids or [])

            # Apply quota counter changes via shared helper.
            # Fetch the creator admin from the local DB so the counter is
            # attributed to the original owner (consistent with web backend).
            if uuids:
                try:
                    users_data = await fetch_users_quota_data_batch(uuids)
                    await apply_users_delete_quotas_batch(users_data)
                except Exception:
                    logger.debug("Failed to update usage counters on bulk delete")
            
            # Отправляем уведомления о удалении
            try:
                bot = target.message.bot if isinstance(target, CallbackQuery) else target.bot
                for user in users_to_notify:
                    await send_user_notification(bot, "deleted", user)
            except Exception:
                logger.exception("Failed to send user deletion notifications")
        elif action == "delete_status":
            if status not in ALLOWED_STATUSES:
                await _reply(target, _("bulk.usage_delete_status"))
                return
            
            # Определяем admin_id для фильтрации на бэкенде
            admin_id_for_api = None
            if admin and admin.account_id and not admin.is_superadmin and not admin.unrestricted_user_access:
                admin_id_for_api = admin.account_id
            
            # Получаем информацию о пользователях перед удалением для уведомлений
            users_to_notify = []
            try:
                start = 0
                while True:
                    users_data = await internal_api_client.get_users(start=start, size=SEARCH_PAGE_SIZE, admin_id=admin_id_for_api)
                    payload = users_data.get("response", users_data)
                    users = payload.get("users", [])
                    total = payload.get("total", len(users))
                    
                    for user in users:
                        user_info = user.get("response", user)
                        if user_info.get("status") == status and user_info.get("uuid"):
                            users_to_notify.append(user)
                    
                    start += SEARCH_PAGE_SIZE
                    if start >= total or not users:
                        break
            except Exception:
                logger.exception("Failed to get users for deletion notifications")
            
            await internal_api_client.bulk_delete_users_by_status(status)

            # Apply quota counter changes via shared helper
            if uuids_for_delete := [u.get("uuid") for u in users_to_notify if u.get("uuid")]:
                try:
                    users_data = await fetch_users_quota_data_batch(uuids_for_delete)
                    await apply_users_delete_quotas_batch(users_data)
                except Exception:
                    logger.debug("Failed to update usage counters on bulk delete by status")
            
            # Отправляем уведомления о удалении
            try:
                bot = target.message.bot if isinstance(target, CallbackQuery) else target.bot
                for user in users_to_notify:
                    await send_user_notification(bot, "deleted", user)
            except Exception:
                logger.exception("Failed to send user deletion notifications")
        elif action == "revoke":
            await internal_api_client.bulk_revoke_subscriptions(uuids or [])
        elif action == "extend":
            if days is None:
                await _reply(target, _("bulk.usage_extend"))
                return
            await internal_api_client.bulk_extend_users(uuids or [], days)
        elif action == "extend_all":
            if days is None:
                await _reply(target, _("bulk.usage_extend_all"))
                return
            await internal_api_client.bulk_extend_all_users(days)
        elif action == "status":
            if status not in ALLOWED_STATUSES:
                await _reply(target, _("bulk.usage_status"))
                return
            await internal_api_client.bulk_update_users_status(uuids or [], status)
        else:
            await _reply(target, _("errors.generic"))
            return
        await _reply(target, _("bulk.done"), back=False)
    except UnauthorizedError:
        await _reply(target, _("errors.unauthorized"))
    except ApiClientError:
        logger.exception("❌ Bulk users action failed action=%s", action)
        await _reply(target, _("bulk.error"))


async def _reply(target: Message | CallbackQuery, text: str, back: bool = False, admin: BotAdmin | None = None) -> None:
    """Отправляет ответ на массовую операцию."""
    markup = bulk_users_keyboard(admin=admin) if back else None
    if isinstance(target, CallbackQuery):
        await _edit_text_safe(target.message, text, reply_markup=markup)
    else:
        await _send_clean_message(target, text, reply_markup=markup)


async def _handle_bulk_users_input(message: Message, ctx: dict, admin: BotAdmin | None = None) -> None:
    """Обрабатывает ввод для массовых операций над пользователями."""
    action = ctx.get("action", "")
    text = (message.text or "").strip()
    user_id = message.from_user.id

    def _reask(prompt_key: str) -> None:
        PENDING_INPUT[user_id] = ctx
        asyncio.create_task(_send_clean_message(message, _(prompt_key), reply_markup=bulk_users_keyboard(admin=admin)))

    if action == "bulk_users_extend_active":
        try:
            days = int(text)
            if days <= 0:
                _reask("bulk.prompt_extend_active")
                return
        except ValueError:
            _reask("bulk.prompt_extend_active")
            return

        # Определяем admin_id для фильтрации на бэкенде
        admin_id_for_api = None
        if admin and admin.account_id and not admin.is_superadmin and not admin.unrestricted_user_access:
            admin_id_for_api = admin.account_id

        try:
            # Получаем всех активных пользователей с пагинацией
            active_uuids: list[str] = []
            start = 0
            while True:
                users_data = await internal_api_client.get_users(start=start, size=SEARCH_PAGE_SIZE, admin_id=admin_id_for_api)
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
                await _send_clean_message(message, _("bulk.no_active_users"), reply_markup=bulk_users_keyboard(admin=admin))
                PENDING_INPUT.pop(user_id, None)
                return

            # Продлеваем активным
            await internal_api_client.bulk_extend_users(active_uuids, days)
            result_text = _("bulk.done_extend_active").format(count=len(active_uuids), days=days)
            await _send_clean_message(message, result_text, reply_markup=bulk_users_keyboard(admin=admin))
            PENDING_INPUT.pop(user_id, None)
        except UnauthorizedError:
            await _send_clean_message(message, _("errors.unauthorized"), reply_markup=bulk_users_keyboard(admin=admin))
            PENDING_INPUT.pop(user_id, None)
        except ApiClientError:
            logger.exception("❌ Bulk extend active users failed")
            await _send_clean_message(message, _("bulk.error"), reply_markup=bulk_users_keyboard(admin=admin))
            PENDING_INPUT.pop(user_id, None)
        return

    await _send_clean_message(message, _("errors.generic"), reply_markup=bulk_users_keyboard(admin=admin))


@router.callback_query(F.data == "menu:bulk_users")
async def cb_bulk_users(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Обработчик кнопки 'Массовые операции (пользователи)' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("bulk.overview"), reply_markup=bulk_users_keyboard(admin=admin))


@router.callback_query(F.data.startswith("bulk:users:"))
async def cb_bulk_users_actions(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Обработчик действий массовых операций над пользователями."""
    if await _not_admin(callback):
        return
    await callback.answer()
    if not await require_permission(callback, admin, "users", "bulk_operations"):
        return
    parts = callback.data.split(":")
    action = parts[2] if len(parts) > 2 else None
    try:
        # Confirm step for destructive bulk actions
        if action in ("reset", "delete") and "confirm" not in parts:
            label = _("bulk.reset_all_traffic") if action == "reset" else _("bulk.template_delete_disabled") if len(parts) > 3 and parts[3] == "DISABLED" else _("bulk.template_delete_expired")
            confirm_data = callback.data + ":confirm"
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ " + _("common.confirm", default="Подтвердить"), callback_data=confirm_data),
                    InlineKeyboardButton(text="❌ " + _("common.cancel", default="Отмена"), callback_data="bulk:users:menu"),
                ],
            ])
            await _edit_text_safe(
                callback.message,
                f"⚠️ <b>{label}</b>\n\n{_('bulk.confirm_warning', default='Это действие необратимо. Вы уверены?')}",
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            return

        # Remove "confirm" from parts for actual execution
        parts = [p for p in parts if p != "confirm"]
        action = parts[2] if len(parts) > 2 else None

        if action == "reset":
            # Fetch all users in scope to get used traffic and creator before reset.
            all_users_data: list = []
            admin_id_for_api = None
            if admin and admin.account_id and not admin.is_superadmin and not admin.unrestricted_user_access:
                admin_id_for_api = admin.account_id
            try:
                start = 0
                while True:
                    users_data = await internal_api_client.get_users(start=start, size=SEARCH_PAGE_SIZE, admin_id=admin_id_for_api)
                    payload = users_data.get("response", users_data)
                    users = payload.get("users", [])
                    total = payload.get("total", len(users))
                    for user in users:
                        info = user.get("response", user)
                        all_users_data.append((
                            info.get("createdByAdminId"),
                            info.get("trafficLimitBytes") or 0,
                            info.get("usedTrafficBytes") or 0,
                        ))
                    start += SEARCH_PAGE_SIZE
                    if start >= total or not users:
                        break
            except Exception:
                logger.exception("Failed to get users for bulk traffic reset (all)")

            await internal_api_client.bulk_reset_traffic_all_users()

            # Apply quota counter changes via shared helper
            if all_users_data:
                try:
                    await apply_users_reset_traffic_quotas_batch(all_users_data)
                except Exception:
                    logger.debug("Failed to update owner traffic counters on bulk reset (all)")

            await _edit_text_safe(callback.message, _("bulk.done"), reply_markup=bulk_users_keyboard(admin=admin))
        elif action == "delete" and len(parts) > 3:
            status = parts[3]
            
            # Определяем admin_id для фильтрации на бэкенде
            admin_id_for_api = None
            if admin and admin.account_id and not admin.is_superadmin and not admin.unrestricted_user_access:
                admin_id_for_api = admin.account_id
            
            # Получаем информацию о пользователях перед удалением для уведомлений
            users_to_notify = []
            try:
                start = 0
                while True:
                    users_data = await internal_api_client.get_users(start=start, size=SEARCH_PAGE_SIZE, admin_id=admin_id_for_api)
                    payload = users_data.get("response", users_data)
                    users = payload.get("users", [])
                    total = payload.get("total", len(users))
                    
                    for user in users:
                        user_info = user.get("response", user)
                        if user_info.get("status") == status and user_info.get("uuid"):
                            users_to_notify.append(user)
                    
                    start += SEARCH_PAGE_SIZE
                    if start >= total or not users:
                        break
            except Exception:
                logger.exception("Failed to get users for deletion notifications")
            
            await internal_api_client.bulk_delete_users_by_status(status)
            
            # Отправляем уведомления о удалении
            try:
                bot = callback.message.bot
                for user in users_to_notify:
                    await send_user_notification(bot, "deleted", user)
            except Exception:
                logger.exception("Failed to send user deletion notifications")
            
            await _edit_text_safe(callback.message, _("bulk.done"), reply_markup=bulk_users_keyboard(admin=admin))
        elif action == "extend_all" and len(parts) > 3:
            try:
                days = int(parts[3])
            except ValueError:
                await callback.answer(_("errors.generic"), show_alert=True)
                return
            await internal_api_client.bulk_extend_all_users(days)
            await _edit_text_safe(callback.message, _("bulk.done"), reply_markup=bulk_users_keyboard(admin=admin))
        elif action == "extend_active":
            # Запрашиваем количество дней
            PENDING_INPUT[callback.from_user.id] = {"action": "bulk_users_extend_active"}
            await _edit_text_safe(callback.message, _("bulk.prompt_extend_active"), reply_markup=bulk_users_keyboard(admin=admin))
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_users_keyboard(admin=admin))
    except ApiClientError:
        logger.exception("❌ Bulk users action failed action=%s", action)
        await _edit_text_safe(callback.message, _("bulk.error"), reply_markup=bulk_users_keyboard(admin=admin))


@router.callback_query(F.data == "menu:bulk_nodes")
async def cb_bulk_nodes(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Обработчик кнопки 'Массовые операции (ноды)' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("bulk_nodes.overview"), reply_markup=bulk_nodes_keyboard(admin=admin))


@router.callback_query(F.data.startswith("bulk:nodes:"))
async def cb_bulk_nodes_actions(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Обработчик действий массовых операций над нодами."""
    if await _not_admin(callback):
        return
    await callback.answer()
    if not await require_permission(callback, admin, "nodes", "edit"):
        return
    parts = callback.data.split(":")
    action = parts[2] if len(parts) > 2 else None
    
    try:
        if action == "profile":
            # Начинаем массовое изменение профилей конфигурации
            from src.handlers.nodes import _bulk_nodes_select_keyboard
            
            try:
                nodes_data = await internal_api_client.get_nodes()
                nodes = nodes_data.get("response", [])
            except UnauthorizedError:
                await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_nodes_keyboard(admin=admin))
                return
            except ApiClientError:
                logger.exception("❌ Bulk nodes fetch failed")
                await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=bulk_nodes_keyboard(admin=admin))
                return

            if not nodes:
                await _edit_text_safe(callback.message, _("node.list_empty"), reply_markup=bulk_nodes_keyboard(admin=admin))
                return

            # Инициализируем состояние для массового изменения
            user_id = callback.from_user.id
            PENDING_INPUT[user_id] = {
                "action": "bulk_nodes_profile",
                "data": {"available_nodes": nodes, "selected_nodes": []},
                "stage": "nodes",
            }
            keyboard = _bulk_nodes_select_keyboard(nodes, [])
            await callback.message.edit_text(_("node.bulk_profile_select_nodes"), reply_markup=keyboard)
            return
        
        if action == "assign_profile":
            try:
                data = await internal_api_client.get_config_profiles()
                profiles = data.get("response", {}).get("configProfiles", [])
            except UnauthorizedError:
                await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_nodes_keyboard(admin=admin))
                return
            except ApiClientError:
                logger.exception("❌ Bulk nodes fetch profiles failed")
                await _edit_text_safe(callback.message, _("bulk_nodes.error"), reply_markup=bulk_nodes_keyboard(admin=admin))
                return

            if not profiles:
                await _edit_text_safe(callback.message, _("bulk_nodes.no_profiles"), reply_markup=bulk_nodes_keyboard(admin=admin))
                return

            from src.handlers.system import _system_nodes_profiles_keyboard
            await _edit_text_safe(
                callback.message,
                _("bulk_nodes.select_profile"),
                reply_markup=_system_nodes_profiles_keyboard(profiles, prefix="bulk:nodes:profile:"),
            )
            return
        
        if len(parts) >= 4 and parts[2] == "profile":
            profile_uuid = parts[3]
            try:
                profile = await internal_api_client.get_config_profile_computed(profile_uuid)
                info = profile.get("response", profile)
                inbounds = info.get("inbounds", [])
                inbound_uuids = [i.get("uuid") for i in inbounds if i.get("uuid")]

                nodes_data = await internal_api_client.get_nodes()
                nodes = nodes_data.get("response", [])
                uuids = [n.get("uuid") for n in nodes if n.get("uuid")]

                if not uuids:
                    await _edit_text_safe(callback.message, _("bulk_nodes.no_nodes"), reply_markup=bulk_nodes_keyboard(admin=admin))
                    return

                await internal_api_client.bulk_nodes_profile_modification(uuids, profile_uuid, inbound_uuids)
                await _edit_text_safe(callback.message, _("bulk_nodes.done_assign"), reply_markup=bulk_nodes_keyboard(admin=admin))
            except UnauthorizedError:
                await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_nodes_keyboard(admin=admin))
            except ApiClientError:
                logger.exception("❌ Bulk nodes assign profile failed profile_uuid=%s", profile_uuid)
                await _edit_text_safe(callback.message, _("bulk_nodes.error"), reply_markup=bulk_nodes_keyboard(admin=admin))
            return

        # Получаем все ноды
        nodes_data = await internal_api_client.get_nodes()
        nodes = nodes_data.get("response", [])
        uuids = [n.get("uuid") for n in nodes if n.get("uuid")]

        if not uuids:
            await _edit_text_safe(callback.message, _("bulk_nodes.no_nodes"), reply_markup=bulk_nodes_keyboard(admin=admin))
            return

        # Выполняем операцию для каждой ноды
        success_count = 0
        error_count = 0

        if action == "enable_all":
            for uuid in uuids:
                try:
                    await internal_api_client.enable_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "disable_all":
            for uuid in uuids:
                try:
                    await internal_api_client.disable_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "restart_all":
            for uuid in uuids:
                try:
                    await internal_api_client.restart_node(uuid, force_restart=True)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "reset_traffic_all":
            for uuid in uuids:
                try:
                    await internal_api_client.reset_node_traffic(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return

        if success_count > 0:
            text = _("bulk_nodes.done").format(success=success_count, error=error_count)
        else:
            text = _("bulk_nodes.error")
        await _edit_text_safe(callback.message, text, reply_markup=bulk_nodes_keyboard(admin=admin))
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_nodes_keyboard(admin=admin))
    except ApiClientError:
        logger.exception("❌ Bulk nodes action failed action=%s", action)
        await _edit_text_safe(callback.message, _("bulk_nodes.error"), reply_markup=bulk_nodes_keyboard(admin=admin))


@router.callback_query(F.data == "menu:bulk_hosts")
async def cb_bulk_hosts(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Обработчик кнопки 'Массовые операции (хосты)' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("bulk_hosts.overview"), reply_markup=bulk_hosts_keyboard(admin=admin))


@router.callback_query(F.data.startswith("bulk:hosts:"))
async def cb_bulk_hosts_actions(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Обработчик действий массовых операций над хостами."""
    if await _not_admin(callback):
        return
    await callback.answer()
    action = callback.data.split(":")[-1]
    if action == "list":
        text = await _fetch_hosts_text(admin=admin)
        await _edit_text_safe(callback.message, text, reply_markup=bulk_hosts_keyboard(admin=admin))
        return
    if not await require_permission(callback, admin, "hosts", "edit"):
        return
    try:
        if action == "enable_all":
            hosts_data = await internal_api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            uuids = [h.get("uuid") for h in hosts if h.get("uuid")]
            if uuids:
                await internal_api_client.bulk_enable_hosts(uuids)
            await _edit_text_safe(callback.message, _("bulk_hosts.done"), reply_markup=bulk_hosts_keyboard(admin=admin))
        elif action == "disable_all":
            hosts_data = await internal_api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            uuids = [h.get("uuid") for h in hosts if h.get("uuid")]
            if uuids:
                await internal_api_client.bulk_disable_hosts(uuids)
            await _edit_text_safe(callback.message, _("bulk_hosts.done"), reply_markup=bulk_hosts_keyboard(admin=admin))
        elif action == "delete_disabled":
            hosts_data = await internal_api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            uuids = [h.get("uuid") for h in hosts if h.get("uuid") and h.get("isDisabled")]
            if uuids:
                await internal_api_client.bulk_delete_hosts(uuids)
            await _edit_text_safe(callback.message, _("bulk_hosts.done"), reply_markup=bulk_hosts_keyboard(admin=admin))
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=bulk_hosts_keyboard(admin=admin))
    except ApiClientError:
        logger.exception("❌ Bulk hosts action failed action=%s", action)
        await _edit_text_safe(callback.message, _("bulk_hosts.error"), reply_markup=bulk_hosts_keyboard(admin=admin))

