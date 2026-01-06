"""Обработчики для массовых операций."""
import asyncio

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin, _send_clean_message
from src.handlers.state import PENDING_INPUT, SEARCH_PAGE_SIZE
from src.keyboards.bulk_hosts import bulk_hosts_keyboard
from src.keyboards.bulk_users import bulk_users_keyboard
from src.services.api_client import ApiClientError, UnauthorizedError, api_client
from src.utils.logger import logger
from src.utils.notifications import send_user_notification

# Временные импорты из других модулей
# TODO: Импортировать _fetch_hosts_text из hosts.py после завершения рефакторинга
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
) -> None:
    """Выполняет массовую операцию над пользователями."""
    try:
        if action == "reset":
            await api_client.bulk_reset_traffic_users(uuids or [])
        elif action == "delete":
            # Получаем информацию о пользователях перед удалением для уведомлений
            users_to_notify = []
            if uuids:
                for user_uuid in uuids:
                    try:
                        user = await api_client.get_user_by_uuid(user_uuid)
                        users_to_notify.append(user)
                    except Exception:
                        logger.debug("Failed to get user data for notification user_uuid=%s", user_uuid)
            
            await api_client.bulk_delete_users(uuids or [])
            
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
            
            # Получаем информацию о пользователях перед удалением для уведомлений
            users_to_notify = []
            try:
                start = 0
                while True:
                    users_data = await api_client.get_users(start=start, size=SEARCH_PAGE_SIZE)
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
            
            await api_client.bulk_delete_users_by_status(status)
            
            # Отправляем уведомления о удалении
            try:
                bot = target.message.bot if isinstance(target, CallbackQuery) else target.bot
                for user in users_to_notify:
                    await send_user_notification(bot, "deleted", user)
            except Exception:
                logger.exception("Failed to send user deletion notifications")
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
    """Отправляет ответ на массовую операцию."""
    markup = bulk_users_keyboard() if back else None
    if isinstance(target, CallbackQuery):
        await _edit_text_safe(target.message, text, reply_markup=markup)
    else:
        await _send_clean_message(target, text, reply_markup=markup)


async def _handle_bulk_users_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод для массовых операций над пользователями."""
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


@router.callback_query(F.data == "menu:bulk_users")
async def cb_bulk_users(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Массовые операции (пользователи)' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("bulk.overview"), reply_markup=bulk_users_keyboard())


@router.callback_query(F.data.startswith("bulk:users:"))
async def cb_bulk_users_actions(callback: CallbackQuery) -> None:
    """Обработчик действий массовых операций над пользователями."""
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
            
            # Получаем информацию о пользователях перед удалением для уведомлений
            users_to_notify = []
            try:
                start = 0
                while True:
                    users_data = await api_client.get_users(start=start, size=SEARCH_PAGE_SIZE)
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
            
            await api_client.bulk_delete_users_by_status(status)
            
            # Отправляем уведомления о удалении
            try:
                bot = callback.message.bot
                for user in users_to_notify:
                    await send_user_notification(bot, "deleted", user)
            except Exception:
                logger.exception("Failed to send user deletion notifications")
            
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


@router.callback_query(F.data == "menu:bulk_hosts")
async def cb_bulk_hosts(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Массовые операции (хосты)' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("bulk_hosts.overview"), reply_markup=bulk_hosts_keyboard())


@router.callback_query(F.data.startswith("bulk:hosts:"))
async def cb_bulk_hosts_actions(callback: CallbackQuery) -> None:
    """Обработчик действий массовых операций над хостами."""
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

