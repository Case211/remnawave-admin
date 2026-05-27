"""Обработчики для управления заблокированными IP-адресами."""
import ipaddress

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin, _send_clean_message, _schedule_message_cleanup
from src.handlers.state import PENDING_INPUT
from src.keyboards.navigation import NavTarget, nav_row
from shared.database import db_service
from shared.logger import logger

router = Router(name="blocked_ips")

# Max subnet width limits (same as backend schemas)
_MIN_IPV4_PREFIX = 16
_MIN_IPV6_PREFIX = 48


# ── Keyboards ────────────────────────────────────────────────


def _blocked_ips_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=_("blocked_ips.btn_add"), callback_data="block_ip:add")],
            nav_row(NavTarget.SYSTEM_MENU),
        ]
    )


def _blocked_ips_list_keyboard(items: list[dict]) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for item in items:
        ip_cidr = str(item.get("ip_cidr", "?"))
        ip_id = item.get("id", 0)
        reason = item.get("reason") or ""
        label = f"❌ {ip_cidr}"
        if reason:
            label += f" — {reason[:30]}"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"block_ip:remove:{ip_id}")])
    rows.append([InlineKeyboardButton(text=_("blocked_ips.btn_add"), callback_data="block_ip:add")])
    rows.append(nav_row(NavTarget.SYSTEM_MENU))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _confirm_remove_keyboard(ip_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=_("actions.confirm"), callback_data=f"block_ip:confirm_remove:{ip_id}"),
                InlineKeyboardButton(text=_("actions.cancel"), callback_data="menu:blocked_ips"),
            ],
        ]
    )


def _input_cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            nav_row(NavTarget.SYSTEM_MENU),
        ]
    )


# ── PENDING_INPUT handler (called from commands.py handle_pending) ──


async def handle_block_ip_add(message: Message, ctx: dict) -> None:
    """Handle text input for IP blocking. Called from central handle_pending dispatcher."""
    user_id = message.from_user.id
    text = message.text.strip()
    _schedule_message_cleanup(message)

    # Validate IP/CIDR
    try:
        net = ipaddress.ip_network(text, strict=False)
        ip_cidr = str(net)
    except ValueError:
        await _send_clean_message(
            message,
            _("blocked_ips.invalid_ip").format(ip=text),
            reply_markup=_input_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    # Check subnet width
    if net.version == 4 and net.prefixlen < _MIN_IPV4_PREFIX:
        await _send_clean_message(
            message,
            _("blocked_ips.subnet_too_wide").format(ip=text),
            reply_markup=_input_cancel_keyboard(),
            parse_mode="HTML",
        )
        return
    if net.version == 6 and net.prefixlen < _MIN_IPV6_PREFIX:
        await _send_clean_message(
            message,
            _("blocked_ips.subnet_too_wide").format(ip=text),
            reply_markup=_input_cancel_keyboard(),
            parse_mode="HTML",
        )
        return

    # Remove from pending
    PENDING_INPUT.pop(user_id, None)

    # Add to DB
    try:
        row = await db_service.add_blocked_ip(
            ip_cidr=ip_cidr,
            reason="Added via Telegram bot",
            admin_id=None,
            admin_username=str(user_id),
        )
    except Exception as e:
        logger.error("Error adding blocked IP %s: %s", ip_cidr, e)
        row = None

    if not row:
        await _send_clean_message(
            message,
            _("blocked_ips.duplicate").format(ip=ip_cidr),
            reply_markup=_blocked_ips_keyboard(),
            parse_mode="HTML",
        )
        return

    await _send_clean_message(
        message,
        _("blocked_ips.added").format(ip=ip_cidr),
        reply_markup=_blocked_ips_keyboard(),
        parse_mode="HTML",
    )


# ── Callback handlers ──────────────────────────────────────


@router.callback_query(F.data == "menu:blocked_ips")
async def cb_blocked_ips_menu(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()

    try:
        items = await db_service.get_blocked_ips(limit=10, offset=0)
        total = await db_service.get_blocked_ips_count()
    except Exception as e:
        logger.error("Error fetching blocked IPs: %s", e)
        items = []
        total = 0

    if items:
        lines = [f"*{_('blocked_ips.title')}*  ({total})", ""]
        for item in items:
            ip_cidr = str(item.get("ip_cidr", "?"))
            reason = item.get("reason") or "—"
            added_by = item.get("added_by_username") or "?"
            lines.append(f"• `{ip_cidr}` — {reason} (by {added_by})")
        text = "\n".join(lines)
        kb = _blocked_ips_list_keyboard(items)
    else:
        text = f"*{_('blocked_ips.title')}*\n\n{_('blocked_ips.empty')}"
        kb = _blocked_ips_keyboard()

    await _edit_text_safe(callback.message, text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "block_ip:add")
async def cb_block_ip_add(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()

    user_id = callback.from_user.id
    PENDING_INPUT[user_id] = {"action": "block_ip_add"}

    await _edit_text_safe(
        callback.message,
        _("blocked_ips.prompt_ip"),
        reply_markup=_input_cancel_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("block_ip:remove:"))
async def cb_block_ip_remove(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()

    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    try:
        ip_id = int(parts[2])
    except ValueError:
        return

    await _edit_text_safe(
        callback.message,
        _("blocked_ips.confirm_remove").format(id=ip_id),
        reply_markup=_confirm_remove_keyboard(ip_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("block_ip:confirm_remove:"))
async def cb_block_ip_confirm_remove(callback: CallbackQuery) -> None:
    if await _not_admin(callback):
        return
    await callback.answer()

    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    try:
        ip_id = int(parts[2])
    except ValueError:
        return

    try:
        deleted = await db_service.remove_blocked_ip(ip_id)
    except Exception as e:
        logger.error("Error removing blocked IP %d: %s", ip_id, e)
        deleted = False

    if not deleted:
        await _edit_text_safe(
            callback.message,
            _("blocked_ips.not_found"),
            reply_markup=_blocked_ips_keyboard(),
            parse_mode="HTML",
        )
        return

    await _edit_text_safe(
        callback.message,
        _("blocked_ips.removed").format(id=ip_id),
        reply_markup=_blocked_ips_keyboard(),
        parse_mode="HTML",
    )
