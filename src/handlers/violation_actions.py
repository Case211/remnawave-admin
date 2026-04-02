"""Обработчики inline-кнопок быстрых действий из уведомлений о нарушениях.

Callback data format: vact:<action>:<user_uuid>
Actions: info, block, dismiss, reset
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from shared.api_client import api_client
from shared.database import db_service

logger = logging.getLogger(__name__)
router = Router()


def _esc(text: str) -> str:
    if not text:
        return ""
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


@router.callback_query(F.data.startswith("vact:"))
async def handle_violation_action(callback: CallbackQuery) -> None:
    """Handle quick action buttons from violation notifications."""
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("❌ Неверный формат", show_alert=True)
        return

    _, action, user_uuid = parts
    admin_name = callback.from_user.first_name or str(callback.from_user.id)
    logger.info("Violation action: %s on user %s by %s", action, user_uuid[:8], admin_name)

    try:
        if action == "info":
            await _show_user_info(callback, user_uuid)
        elif action == "block":
            await _block_user(callback, user_uuid)
        elif action == "kill":
            await _kill_user(callback, user_uuid)
        elif action == "dismiss":
            await _dismiss(callback)
        elif action == "reset":
            await _reset_traffic(callback, user_uuid)
        else:
            await callback.answer(f"❌ Неизвестное действие: {action}", show_alert=True)
    except Exception as e:
        logger.error("Violation action error (%s/%s): %s", action, user_uuid, e)
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


async def _show_user_info(callback: CallbackQuery, user_uuid: str) -> None:
    """Show brief user info."""
    try:
        result = await api_client.get_user_by_uuid(user_uuid)
        user = result.get("response", result)
        username = user.get("username", "?")
        status = user.get("status", "?")

        ut = user.get("userTraffic") or {}
        used = int(ut.get("usedTrafficBytes") or user.get("usedTrafficBytes") or 0)
        limit = int(user.get("trafficLimitBytes") or 0)
        used_gb = used / (1024 ** 3)
        limit_gb = limit / (1024 ** 3) if limit else 0

        traffic_str = f"{used_gb:.2f} GB"
        if limit:
            percent = (used / limit * 100) if limit > 0 else 0
            traffic_str += f" / {limit_gb:.1f} GB ({percent:.0f}%)"
        else:
            traffic_str += " / ∞"

        text = (
            f"👤 <b>{_esc(username)}</b>\n"
            f"Статус: <code>{status}</code>\n"
            f"Трафик: <code>{traffic_str}</code>\n"
            f"UUID: <code>{user_uuid[:16]}...</code>"
        )
        await callback.message.reply(text, parse_mode="HTML")
        await callback.answer()
    except Exception as e:
        await callback.answer(f"❌ Не удалось получить инфо: {e}", show_alert=True)


async def _block_user(callback: CallbackQuery, user_uuid: str) -> None:
    """Disable (block) user via Panel API."""
    try:
        await api_client.disable_user(user_uuid)

        # Get username for confirmation
        username = user_uuid[:8]
        try:
            result = await api_client.get_user_by_uuid(user_uuid)
            username = result.get("response", result).get("username", username)
        except Exception:
            pass

        logger.warning("User %s (%s) BLOCKED by %s via violation button", user_uuid, username, callback.from_user.first_name)
        await callback.answer(f"🔒 {username} заблокирован", show_alert=True)

        try:
            old_text = callback.message.text or callback.message.html_text or ""
            await callback.message.edit_text(
                old_text + f"\n\n✅ <i>Заблокирован ({callback.from_user.first_name})</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Block user %s failed: %s", user_uuid, e)
        await callback.answer(f"❌ Ошибка блокировки: {e}", show_alert=True)


async def _kill_user(callback: CallbackQuery, user_uuid: str) -> None:
    """Disable user AND drop all connections via Panel API."""
    try:
        # 1. Disable user
        await api_client.disable_user(user_uuid)

        # 2. Drop all connections
        try:
            await api_client.drop_connections(
                drop_by={"by": "userUuids", "userUuids": [user_uuid]},
                target_nodes={"target": "allNodes"},
            )
        except Exception as e:
            logger.warning("Drop connections failed for %s: %s", user_uuid, e)

        username = user_uuid[:8]
        try:
            result = await api_client.get_user_by_uuid(user_uuid)
            username = result.get("response", result).get("username", username)
        except Exception:
            pass

        logger.warning("User %s (%s) KILLED (disabled + connections dropped) by %s", user_uuid, username, callback.from_user.first_name)
        await callback.answer(f"⛔ {username} отключён, соединения разорваны", show_alert=True)

        try:
            old_text = callback.message.text or callback.message.html_text or ""
            await callback.message.edit_text(
                old_text + f"\n\n⛔ <i>Отключён + соединения разорваны ({callback.from_user.first_name})</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Kill user %s failed: %s", user_uuid, e)
        await callback.answer(f"❌ Ошибка: {e}", show_alert=True)


async def _dismiss(callback: CallbackQuery) -> None:
    """Dismiss the notification (remove buttons)."""
    await callback.answer("✅ Пропущено")
    try:
        old_text = callback.message.text or callback.message.html_text or ""
        await callback.message.edit_text(
            old_text + f"\n\n✅ <i>Пропущено ({callback.from_user.first_name})</i>",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def _reset_traffic(callback: CallbackQuery, user_uuid: str) -> None:
    """Reset user traffic via Panel API."""
    try:
        await api_client.reset_user_traffic(user_uuid)

        username = user_uuid[:8]
        try:
            result = await api_client.get_user_by_uuid(user_uuid)
            username = result.get("response", result).get("username", username)
        except Exception:
            pass

        logger.warning("Traffic RESET for user %s (%s) by %s via violation button", user_uuid, username, callback.from_user.first_name)
        await callback.answer(f"🔄 Трафик {username} сброшен", show_alert=True)

        try:
            old_text = callback.message.text or callback.message.html_text or ""
            await callback.message.edit_text(
                old_text + f"\n\n🔄 <i>Трафик сброшен ({callback.from_user.first_name})</i>",
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        await callback.answer(f"❌ Ошибка сброса: {e}", show_alert=True)
