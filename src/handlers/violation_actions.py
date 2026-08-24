"""Обработчики inline-кнопок быстрых действий из уведомлений о нарушениях.

Callback data format: vact:<action>:<user_uuid>
Actions: info, block, kill, dismiss (= annul), reset, thr, unthr, wl, wlp_<analyzer>

wlp_<analyzer> держит разрез внутри самого действия, а не отдельным полем:
user_uuid читается как остаток строки, и лишнее двоеточие сломало бы разбор.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from shared.internal_api import internal_api_client
from shared.database import db_service
from shared.admin_quota import (
    apply_user_reset_traffic_quotas,
    fetch_user_quota_data,
)
from src.services import data_access
from src.utils.auth import BotAdmin
from src.utils.formatters import _esc
from src.utils.notifications import VIOLATION_ANALYZERS

logger = logging.getLogger(__name__)
router = Router()

# Действия, меняющие состояние. Белый список сюда же: он отключает защиту,
# то есть последствия у него не меньше, чем у блокировки.
_MUTATING_ACTIONS = frozenset({"block", "kill", "dismiss", "reset", "wl", "thr", "unthr"})


def needs_resolve_permission(action: str) -> bool:
    """Требует ли действие права violations:resolve — как в веб-API."""
    return action in _MUTATING_ACTIONS or action.startswith("wlp_")


@router.callback_query(F.data.startswith("vact:"))
async def handle_violation_action(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Handle quick action buttons from violation notifications."""
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer(_("vact.invalid_format"), show_alert=True)
        return

    # Не «_»: это имя занято gettext, и присваивание делало его локальным —
    # ответ про неверный формат выше падал с UnboundLocalError.
    _prefix, action, user_uuid = parts
    admin_name = callback.from_user.first_name or str(callback.from_user.id)
    logger.info("Violation action: %s on user %s by %s", action, user_uuid[:8], admin_name)

    # RBAC: мутирующие действия требуют права violations:resolve — как в веб-API
    # (require_permission("violations","resolve")). Приходящий admin подтверждает
    # только доступ к боту, но не право на действие над нарушением.
    if needs_resolve_permission(action):
        if not await admin.has_permission("violations", "resolve"):
            logger.warning(
                "Violation action %s DENIED for %s (no violations:resolve)", action, admin_name
            )
            await callback.answer(_("vact.no_permission"), show_alert=True)
            return

    # Access-policy scope: не даём действовать (в т.ч. смотреть) на юзеров вне
    # зоны видимости админа — веб-API так проверяет resolve/annul/detail.
    visible = await admin.get_visible_user_uuids()
    if visible is not None and user_uuid.lower() not in visible:
        logger.warning(
            "Violation action %s DENIED for %s (user %s out of scope)", action, admin_name, user_uuid[:8]
        )
        await callback.answer(_("vact.out_of_scope"), show_alert=True)
        return

    try:
        # The panel identifies users by numeric id under v3; local DB rows
        # carry the panel id so resolve it once for all API calls below.
        panel_user_id = await data_access.resolve_panel_user_id(user_uuid)
        if action == "info":
            await _show_user_info(callback, user_uuid, panel_user_id)
        elif action == "block":
            await _block_user(callback, user_uuid, panel_user_id)
        elif action == "kill":
            await _kill_user(callback, user_uuid, panel_user_id)
        elif action == "dismiss":
            await _annul(callback, user_uuid)
        elif action == "reset":
            await _reset_traffic(callback, user_uuid, panel_user_id)
        elif action == "thr":
            await _throttle_user(callback, user_uuid, admin)
        elif action == "unthr":
            await _unthrottle_user(callback, user_uuid)
        elif action == "wl":
            await _whitelist_full(callback, user_uuid, admin)
        elif action.startswith("wlp_"):
            await _whitelist_partial(callback, user_uuid, action[len("wlp_"):], admin)
        else:
            await callback.answer(_("vact.unknown_action").format(action=action), show_alert=True)
    except Exception as e:
        logger.error("Violation action error (%s/%s): %s", action, user_uuid, e)
        await callback.answer(_("vact.error").format(e=e), show_alert=True)


async def _show_user_info(callback: CallbackQuery, user_uuid: str, panel_user_id: str | int) -> None:
    """Show brief user info."""
    try:
        result = await internal_api_client.get_user_by_id(panel_user_id)
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


async def _block_user(callback: CallbackQuery, user_uuid: str, panel_user_id: str | int) -> None:
    """Disable (block) user via Panel API."""
    try:
        await internal_api_client.disable_user(panel_user_id)

        # Get username for confirmation
        username = user_uuid[:8]
        try:
            result = await internal_api_client.get_user_by_id(panel_user_id)
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


async def _kill_user(callback: CallbackQuery, user_uuid: str, panel_user_id: str | int) -> None:
    """Disable user AND drop all connections via Panel API."""
    try:
        # 1. Disable user
        await internal_api_client.disable_user(panel_user_id)

        # 2. Drop all connections
        try:
            await internal_api_client.drop_connections(
                drop_by={"by": "userIds", "userIds": [panel_user_id]},
                target_nodes={"target": "allNodes"},
            )
        except Exception as e:
            logger.warning("Drop connections failed for %s: %s", user_uuid, e)

        username = user_uuid[:8]
        try:
            result = await internal_api_client.get_user_by_id(panel_user_id)
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


async def _reset_traffic(callback: CallbackQuery, user_uuid: str, panel_user_id: str | int) -> None:
    """Reset user traffic via Panel API."""
    try:
        username = user_uuid[:8]
        try:
            result = await internal_api_client.get_user_by_id(panel_user_id)
            info = result.get("response", result)
            username = info.get("username", username)
        except Exception:
            logger.debug("Failed to fetch user data for reset user_uuid=%s", user_uuid)

        # Apply quota counter changes via shared helper
        try:
            # Fetch used_traffic_bytes BEFORE the reset
            creator_id, _limit, used_bytes = await fetch_user_quota_data(user_uuid)
            await internal_api_client.reset_user_traffic(panel_user_id)
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


async def _whitelist_full(callback: CallbackQuery, user_uuid: str, admin: BotAdmin) -> None:
    """Полный белый список: пользователя больше не проверяет ни один анализатор."""
    try:
        success, error = await db_service.add_to_violation_whitelist(
            user_uuid=user_uuid,
            reason=_("vact.wl_reason").format(name=callback.from_user.first_name),
            admin_id=admin.account_id,
            admin_username=admin.username or str(admin.telegram_id),
            excluded_analyzers=None,
        )
        if not success:
            await callback.answer(_("vact.wl_error").format(e=error or "?"), show_alert=True)
            return

        logger.warning(
            "User %s WHITELISTED (full) by %s via violation button",
            user_uuid, callback.from_user.first_name,
        )
        await callback.answer(_("vact.wl_done"), show_alert=True)
        await _append_note(callback, _("vact.wl_suffix").format(name=callback.from_user.first_name))
    except Exception as e:
        logger.error("Whitelist user %s failed: %s", user_uuid, e)
        await callback.answer(_("vact.wl_error").format(e=e), show_alert=True)


async def _whitelist_partial(
    callback: CallbackQuery, user_uuid: str, analyzer: str, admin: BotAdmin,
) -> None:
    """Частичный белый список: не проверять этого пользователя одним анализатором.

    Уже имеющиеся исключения сохраняются: запись в whitelist одна на
    пользователя и перезаписывается целиком, так что новый разрез нужно
    подмешать к старым, иначе прошлое решение молча потеряется.
    """
    if analyzer not in VIOLATION_ANALYZERS:
        await callback.answer(_("vact.wl_unknown_analyzer").format(analyzer=analyzer), show_alert=True)
        return

    try:
        is_whitelisted, excluded = await db_service.is_user_violation_whitelisted(user_uuid)
        if is_whitelisted and excluded is None:
            # Полный белый список шире частичного — сужать его молча нельзя.
            await callback.answer(_("vact.wl_already_full"), show_alert=True)
            return

        merged = sorted(set(excluded or []) | {analyzer})
        success, error = await db_service.add_to_violation_whitelist(
            user_uuid=user_uuid,
            reason=_("vact.wl_reason").format(name=callback.from_user.first_name),
            admin_id=admin.account_id,
            admin_username=admin.username or str(admin.telegram_id),
            excluded_analyzers=merged,
        )
        if not success:
            await callback.answer(_("vact.wl_error").format(e=error or "?"), show_alert=True)
            return

        label = _(f"vact.analyzer.{analyzer}")
        logger.warning(
            "User %s WHITELISTED (analyzers=%s) by %s via violation button",
            user_uuid, ",".join(merged), callback.from_user.first_name,
        )
        await callback.answer(_("vact.wlp_done").format(analyzer=label), show_alert=True)
        await _append_note(
            callback,
            _("vact.wlp_suffix").format(analyzer=label, name=callback.from_user.first_name),
        )
    except Exception as e:
        logger.error("Partial whitelist %s/%s failed: %s", user_uuid, analyzer, e)
        await callback.answer(_("vact.wl_error").format(e=e), show_alert=True)


async def _append_note(
    callback: CallbackQuery,
    note: str,
    keyboard: Optional[InlineKeyboardMarkup] = None,
) -> None:
    """Дописать отметку под карточкой нарушения.

    Карточки уходят rich-сообщением (Bot API 10.1), которого aiogram 3.12 ещё
    не знает: ни text, ни caption у такого сообщения нет, а html_text собран из
    них же и отдаёт пустую строку. Правка пустым текстом стирала карточку
    целиком, оставляя от неё одну отметку, — поэтому когда текста не видно,
    отметка уходит отдельным ответом, а на самой карточке меняются кнопки.
    """
    message = callback.message
    if message is None:
        return

    try:
        old_text = message.html_text
    except (AttributeError, TypeError):
        old_text = ""

    if old_text:
        try:
            await message.edit_text(old_text + note, parse_mode="HTML", reply_markup=keyboard)
        except Exception as e:
            logger.warning("Failed to append action note: %s", e)
        return

    try:
        await message.edit_reply_markup(reply_markup=keyboard)
    except Exception as e:
        logger.debug("Cannot update violation card keyboard: %s", e)
    try:
        await message.reply(note.strip(), parse_mode="HTML")
    except Exception as e:
        logger.warning("Failed to send action note: %s", e)


def _unthrottle_keyboard(user_uuid: str) -> InlineKeyboardMarkup:
    """Единственная кнопка под наказанием — вернуть скорость обратно."""
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text=_("vact.unthr_button"), callback_data=f"vact:unthr:{user_uuid}",
        )
    ]])


async def _throttle_user(callback: CallbackQuery, user_uuid: str, admin: BotAdmin) -> None:
    """Урезать пользователю скорость вместо полного отключения.

    Бот пишет решение в базу, а раскладывает его по нодам синхронизатор
    веб-бэкенда: WebSocket-каналы к агентам держит он, и дублировать их в
    боте незачем. Отсюда и задержка до минуты, о которой честно говорим.
    """
    from shared.config_service import config_service

    try:
        rate_kbit = int(config_service.get("throttle_default_kbit", 1024) or 1024)
    except (TypeError, ValueError):
        rate_kbit = 1024

    # Срок наказания берём из настроек: ноль там значит «до ручного снятия».
    try:
        hours = int(config_service.get("throttle_default_hours", 0) or 0)
    except (TypeError, ValueError):
        hours = 0
    until = datetime.utcnow() + timedelta(hours=hours) if hours > 0 else None
    period_note = _("vact.thr_period").format(hours=hours) if hours > 0 else ""

    try:
        from shared.throttle import apply_throttle

        success, error, moved = await apply_throttle(
            user_uuid=user_uuid,
            rate_kbit=rate_kbit,
            reason=_("vact.thr_reason").format(name=callback.from_user.first_name),
            admin_id=admin.account_id,
            admin_username=admin.username or str(admin.telegram_id),
            until=until,
        )
        if not success:
            await callback.answer(_("vact.thr_error").format(e=error or "?"), show_alert=True)
            return

        logger.warning(
            "User %s THROTTLED to %d kbit by %s via violation button",
            user_uuid, rate_kbit, callback.from_user.first_name,
        )
        moved_note = _("vact.thr_moved") if moved else ""
        await callback.answer(
            _("vact.thr_done").format(rate=rate_kbit, period=period_note, moved=moved_note),
            show_alert=True,
        )
        await _append_note(
            callback,
            _("vact.thr_suffix").format(
                rate=rate_kbit, name=callback.from_user.first_name,
                period=period_note, moved=moved_note,
            ),
            keyboard=_unthrottle_keyboard(user_uuid),
        )
    except Exception as e:
        logger.error("Throttle user %s failed: %s", user_uuid, e)
        await callback.answer(_("vact.thr_error").format(e=e), show_alert=True)


async def _unthrottle_user(callback: CallbackQuery, user_uuid: str) -> None:
    """Вернуть скорость: снять решение из базы и увести человека обратно.

    Правила с нод снимает тот же синхронизатор веб-бэкенда, что и ставит:
    пустой список для ноды — это и есть снятие, отсюда та же задержка до
    минуты, о которой честно говорим и при наказании.
    """
    try:
        from shared.throttle import lift_throttle

        removed, restored = await lift_throttle(user_uuid)
        if not removed:
            await callback.answer(_("vact.unthr_absent"), show_alert=True)
            return

        logger.warning(
            "User %s UNTHROTTLED by %s via violation button",
            user_uuid, callback.from_user.first_name,
        )
        restored_note = _("vact.unthr_restored") if restored else ""
        await callback.answer(
            _("vact.unthr_done").format(restored=restored_note), show_alert=True,
        )
        await _append_note(
            callback,
            _("vact.unthr_suffix").format(
                name=callback.from_user.first_name, restored=restored_note,
            ),
        )
    except Exception as e:
        logger.error("Unthrottle user %s failed: %s", user_uuid, e)
        await callback.answer(_("vact.unthr_error").format(e=e), show_alert=True)
