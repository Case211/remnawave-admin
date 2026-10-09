"""Обработчики inline-кнопок из финансовых напоминаний.

Callback data format: fin:<action>:<item_id>
Actions: paid (платёж + сдвиг цикла), skip (сдвиг цикла без платежа)
"""
import logging
from html import escape

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from shared.database import db_service
from src.utils.auth import BotAdmin
from src.utils.cards import append_card_note

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data.startswith("fin:"))
async def handle_finance_action(callback: CallbackQuery, admin: BotAdmin) -> None:
    """Handle quick action buttons from finance payment reminders."""
    parts = callback.data.split(":", 2)
    if len(parts) < 3 or not parts[2].isdigit():
        await callback.answer(_("fin.invalid_format"), show_alert=True)
        return

    _unused, action, raw_id = parts
    item_id = int(raw_id)
    admin_name = callback.from_user.first_name or str(callback.from_user.id)

    # RBAC как в веб-API: отметка оплаты / пропуск цикла = finance:edit
    if not await admin.has_permission("finance", "edit"):
        logger.warning("Finance action %s DENIED for %s (no finance:edit)", action, admin_name)
        await callback.answer(_("fin.no_permission"), show_alert=True)
        return

    try:
        if action == "paid":
            item = await db_service.mark_finance_item_paid(item_id, source="telegram")
        elif action == "skip":
            item = await db_service.skip_finance_item_cycle(item_id)
        else:
            await callback.answer(_("fin.unknown_action").format(action=action), show_alert=True)
            return

        if not item:
            await callback.answer(_("fin.not_found"), show_alert=True)
            return

        logger.info("Finance action %s on item %s by %s", action, item_id, admin_name)
        next_due = item.get("next_due_at") or "—"
        key = "fin.paid_ok" if action == "paid" else "fin.skip_ok"
        note = _(key).format(name=item["name"], next_due=next_due)
        await callback.answer(note, show_alert=False)
        # Кнопки встроены в карточку: снимаем их правкой самой карточки,
        # заодно оставляя на ней отметку, что ответ уже дан
        await append_card_note(callback, "\n\n" + escape(note))
    except Exception as e:
        logger.error("Finance action error (%s/%s): %s", action, item_id, e)
        await callback.answer(_("fin.error").format(e=e), show_alert=True)
