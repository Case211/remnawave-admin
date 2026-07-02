"""Обработчики inline-кнопок быстрых действий из уведомлений о нарушениях.

Callback data format: vact:<action>:<user_uuid>
Actions: info, block, kill, dismiss (= annul), reset
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from shared.internal_api import internal_api_client
from shared.database import db_service
from shared.admin_quota import (
    apply_user_reset_traffic_quotas,
    fetch_user_quota_data,
)
from src.utils.auth import BotAdmin

logger = logging.getLogger(__name__)
router = Router()


from src.utils.formatters import _esc


@router.callback_query(F.data.startswith("vact:"))
async def handle_violation_action(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Handle quick action buttons from violation notifications."""
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer(_("vact.invalid_format"), show_alert=True)
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
            await _annul(callback, user_uuid)
        elif action == "reset":
            await _reset_traffic(callback, user_uuid)
        else:
            await callback.answer(_("vact.unknown_action").format(action=action), show_alert=True)
    except Exception as e:
        logger.error("Violation action error (%s/%s): %s", action, user_uuid, e)
        await callback.answer(_("vact.error").format(e=e), show_alert=True)


async def _show_user_info(callback: CallbackQuery, user_uuid: str) -> None:
    """Show brief user info."""
    try:
        result = await internal_api_client.get_user_by_uuid(user_uuid)
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

        # callback.answer — это plain-text алерт, HTML тут не рендерится и эскейп не нужен
        text = _("vact.user_info").format(
            username=username,
            status=status,
            traffic=traffic_str,
            uuid=f"{user_uuid[:16]}...",
        )
        await callback.answer(text[:200], show_alert=True)
    except Exception as e:
        await callback.answer(_("vact.info_failed").format(e=e), show_alert=True)


async def _block_user(callback: CallbackQuery, user_uuid: str) -> None:
    """Disable (block) user via Panel API."""
    try:
        await internal_api_client.disable_user(user_uuid)

        # Get username for confirmation
        username = user_uuid[:8]
        try:
            result = await internal_api_client.get_user_by_uuid(user_uuid)
            username = result.get("response", result).get("username", username)
        except Exception:
            pass

        logger.warning("User %s (%s) BLOCKED by %s via violation button", user_uuid, username, callback.from_user.first_name)
        await callback.answer(_("vact.blocked").format(username=username), show_alert=True)

        try:
            old_text = callback.message.text or callback.message.html_text or ""
            await callback.message.edit_text(
                old_text + _("vact.blocked_suffix").format(name=callback.from_user.first_name),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Block user %s failed: %s", user_uuid, e)
        await callback.answer(_("vact.block_error").format(e=e), show_alert=True)


async def _kill_user(callback: CallbackQuery, user_uuid: str) -> None:
    """Disable user AND drop all connections via Panel API."""
    try:
        # 1. Disable user
        await internal_api_client.disable_user(user_uuid)

        # 2. Drop all connections
        try:
            await internal_api_client.drop_connections(
                drop_by={"by": "userUuids", "userUuids": [user_uuid]},
                target_nodes={"target": "allNodes"},
            )
        except Exception as e:
            logger.warning("Drop connections failed for %s: %s", user_uuid, e)

        username = user_uuid[:8]
        try:
            result = await internal_api_client.get_user_by_uuid(user_uuid)
            username = result.get("response", result).get("username", username)
        except Exception:
            pass

        logger.warning("User %s (%s) KILLED (disabled + connections dropped) by %s", user_uuid, username, callback.from_user.first_name)
        await callback.answer(_("vact.killed").format(username=username), show_alert=True)

        try:
            old_text = callback.message.text or callback.message.html_text or ""
            await callback.message.edit_text(
                old_text + _("vact.killed_suffix").format(name=callback.from_user.first_name),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        logger.error("Kill user %s failed: %s", user_uuid, e)
        await callback.answer(_("vact.error").format(e=e), show_alert=True)


async def _annul(callback: CallbackQuery, user_uuid: str) -> None:
    """Аннулировать все pending-нарушения юзера и закрыть уведомление."""
    admin_id = callback.from_user.id
    admin_name = callback.from_user.first_name or str(admin_id)
    try:
        count = await db_service.annul_pending_violations(
            user_uuid=user_uuid,
            admin_telegram_id=admin_id,
            admin_comment=_("vact.annul_comment").format(admin_name=admin_name),
        )
    except Exception as e:
        logger.error("Annul violations for %s failed: %s", user_uuid, e)
        await callback.answer(_("vact.annul_failed").format(e=e), show_alert=True)
        return

    if count > 0:
        logger.info("Violations annulled for user %s by %s (count=%d)", user_uuid, admin_name, count)
        await callback.answer(_("vact.annulled").format(count=count))
        suffix = _("vact.annulled_suffix").format(count=count, name=_esc(admin_name))
    else:
        await callback.answer(_("vact.nothing_to_annul"))
        suffix = _("vact.already_processed").format(name=_esc(admin_name))

    try:
        old_text = callback.message.text or callback.message.html_text or ""
        await callback.message.edit_text(old_text + suffix, parse_mode="HTML")
    except Exception:
        pass


async def _reset_traffic(callback: CallbackQuery, user_uuid: str) -> None:
    """Reset user traffic via Panel API."""
    try:
        username = user_uuid[:8]
        try:
            result = await internal_api_client.get_user_by_uuid(user_uuid)
            info = result.get("response", result)
            username = info.get("username", username)
        except Exception:
            logger.debug("Failed to fetch user data for reset user_uuid=%s", user_uuid)

        # Apply quota counter changes via shared helper
        try:
            # Fetch used_traffic_bytes BEFORE the reset
            creator_id, _limit, used_bytes = await fetch_user_quota_data(user_uuid)
            await internal_api_client.reset_user_traffic(user_uuid)
            await apply_user_reset_traffic_quotas(creator_id, used_bytes)
        except Exception:
            logger.debug("Failed to update usage counters on violation reset user_uuid=%s", user_uuid)

        logger.warning("Traffic RESET for user %s (%s) by %s via violation button", user_uuid, username, callback.from_user.first_name)
        await callback.answer(_("vact.traffic_reset").format(username=username), show_alert=True)

        try:
            old_text = callback.message.text or callback.message.html_text or ""
            await callback.message.edit_text(
                old_text + _("vact.traffic_reset_suffix").format(name=callback.from_user.first_name),
                parse_mode="HTML",
            )
        except Exception:
            pass
    except Exception as e:
        await callback.answer(_("vact.reset_error").format(e=e), show_alert=True)
