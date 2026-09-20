"""Быстрые действия из уведомлений об обращениях.

Callback data: ``sact:<action>:<ticket_id>``, действия — take, snooze, close.

Смысл кнопок в том, чтобы ночной ответ клиента можно было разобрать не
открывая панель: взять обращение себе, отложить на час или закрыть. Права те
же, что и в вебе (``bedolaga_support:edit``), — уведомление уходит в общий
чат, и нажать кнопку может кто угодно из тех, кто в этот чат допущен.
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from shared.database import db_service
from src.utils.auth import BotAdmin

logger = logging.getLogger(__name__)
router = Router()

SNOOZE_MINUTES = 60


def _ensure_bedolaga() -> bool:
    """Настроить клиент бота Bedolaga: у процесса бота его никто не поднимал."""
    from shared.bedolaga_client import bedolaga_client

    if bedolaga_client.is_configured:
        return True
    try:
        from web.backend.core.config import get_web_settings

        settings = get_web_settings()
        if not settings.bedolaga_api_url or not settings.bedolaga_api_token:
            return False
        bedolaga_client.configure(settings.bedolaga_api_url, settings.bedolaga_api_token)
        return True
    except Exception as exc:  # noqa: BLE001 — не настроено: скажем об этом кнопкой
        logger.warning("Support action: клиент Bedolaga не настроен: %s", exc)
        return False


@router.callback_query(F.data.startswith("sact:"))
async def handle_support_action(callback: CallbackQuery, admin: BotAdmin) -> None:
    parts = (callback.data or "").split(":", 2)
    if len(parts) < 3 or not parts[2].isdigit():
        await callback.answer("Не разобрал кнопку", show_alert=True)
        return

    _prefix, action, raw_id = parts
    ticket_id = int(raw_id)

    if not await admin.has_permission("bedolaga_support", "edit"):
        logger.warning("Support action %s DENIED for %s", action, admin.username or admin.telegram_id)
        await callback.answer("Нет прав на обращения", show_alert=True)
        return

    if not db_service.is_connected:
        await callback.answer("База недоступна", show_alert=True)
        return

    try:
        if action == "take":
            if not admin.account_id:
                # Назначение хранится по учётке панели: у админа из .env её нет.
                await callback.answer("Взять обращение может только админ с учёткой панели", show_alert=True)
                return
            async with db_service.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO support_assignments (ticket_id, admin_id, claimed_at)
                    VALUES ($1, $2, NOW())
                    ON CONFLICT (ticket_id) DO UPDATE SET admin_id = EXCLUDED.admin_id, claimed_at = NOW()
                    """,
                    ticket_id,
                    admin.account_id,
                )
            await callback.answer(f"Обращение #{ticket_id} на вас")

        elif action == "snooze":
            async with db_service.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO support_snoozes (ticket_id, snooze_to)
                    VALUES ($1, NOW() + ($2 || ' minutes')::interval)
                    ON CONFLICT (ticket_id) DO UPDATE SET snooze_to = EXCLUDED.snooze_to
                    """,
                    ticket_id,
                    str(SNOOZE_MINUTES),
                )
            await callback.answer(f"Отложено на {SNOOZE_MINUTES} мин")

        elif action == "close":
            if not _ensure_bedolaga():
                await callback.answer("Bedolaga API не настроен", show_alert=True)
                return
            from shared.bedolaga_client import bedolaga_client
            from web.backend.core.support_sync import sync_ticket

            # Статус живёт в боте — закрываем через него, проекция догоняет следом.
            await bedolaga_client.set_ticket_status(ticket_id, "closed")
            await sync_ticket(ticket_id)
            await callback.answer(f"Обращение #{ticket_id} закрыто")

        else:
            await callback.answer("Неизвестное действие", show_alert=True)
            return

    except Exception as exc:  # noqa: BLE001 — бот не должен падать на кнопке
        logger.error("Support action %s по %s не выполнено: %s", action, ticket_id, exc, exc_info=True)
        await callback.answer("Не получилось, посмотрите в панели", show_alert=True)
        return

    logger.info(
        "Support action %s по обращению %s от %s", action, ticket_id, admin.username or admin.telegram_id
    )
