"""Кнопки плагинов под уведомлениями в Telegram.

Callback data: ``pact:<plugin_id>:<action>:<ref>`` — формат собирает
``web.backend.core.plugin_api.plugin_actions_markup``.

Плагины живут в процессе веб-бэкенда, а кнопку жмут в боте — импортировать
их код здесь нельзя. Поэтому нажатие обрабатывает сам бот, а общего у них
только таблица в БД: обработчик пишет в неё ответ, плагин своим тиком его
подхватывает. Отсюда же мягкая деградация: плагин не установлен — таблицы
нет, и человек получает внятное «плагин не установлен», а не молчание.
"""
import logging
from typing import Awaitable, Callable, Dict

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from shared.database import db_service
from src.utils.auth import BotAdmin

logger = logging.getLogger(__name__)
router = Router()

# Отметки радара: была блокировка на самом деле или детектор ошибся.
_RADAR_VERDICTS = {"fb_yes": "confirmed", "fb_no": "false_positive"}


@router.callback_query(F.data.startswith("pact:"))
async def handle_plugin_action(callback: CallbackQuery, admin: BotAdmin) -> None:
    parts = callback.data.split(":", 3)
    if len(parts) < 4:
        await callback.answer(_("pact.invalid_format"), show_alert=True)
        return

    _prefix, plugin_id, action, ref = parts
    handler = _HANDLERS.get(plugin_id)
    if handler is None:
        await callback.answer(_("pact.unknown_plugin"), show_alert=True)
        return

    # Ресурс RBAC у плагина назван его же идентификатором (манифест
    # rbac_resources), а ответ об инциденте — изменение данных, поэтому
    # спрашиваем edit, а не view.
    if not await admin.has_permission(plugin_id, "edit"):
        logger.warning(
            "Plugin action %s/%s DENIED for %s", plugin_id, action, callback.from_user.id
        )
        await callback.answer(_("pact.no_permission"), show_alert=True)
        return

    try:
        await handler(callback, action, ref)
    except Exception as e:
        if _is_missing_table(e):
            await callback.answer(_("pact.plugin_missing"), show_alert=True)
            return
        logger.error("Plugin action %s/%s failed: %s", plugin_id, action, e)
        await callback.answer(_("pact.error").format(e=e), show_alert=True)


async def _block_radar(callback: CallbackQuery, action: str, ref: str) -> None:
    """Отметка об инциденте радара. Уезжает на сервер ближайшим тиком
    плагина — сам бот в облако не ходит."""
    verdict = _RADAR_VERDICTS.get(action)
    if verdict is None:
        await callback.answer(_("pact.unknown_action").format(action=action), show_alert=True)
        return
    try:
        alert_id = int(ref)
    except ValueError:
        await callback.answer(_("pact.invalid_format"), show_alert=True)
        return

    async with db_service.acquire() as conn:
        updated = await conn.fetchval(
            """UPDATE plugin_block_radar_alerts
               SET feedback = $2, feedback_at = NOW()
               WHERE id = $1
               RETURNING id""",
            alert_id, verdict,
        )
    if updated is None:
        await callback.answer(_("pact.radar_not_found"), show_alert=True)
        return

    logger.info(
        "Radar incident %s marked as %s by %s", alert_id, verdict, callback.from_user.id
    )
    mark = _("pact.radar_confirmed") if verdict == "confirmed" else _("pact.radar_false")
    await callback.answer(mark, show_alert=False)
    await _seal(callback, mark)


async def _seal(callback: CallbackQuery, mark: str) -> None:
    """Дописать итог в сообщение и убрать кнопки: следующий читатель должен
    видеть, что ответ уже дан, и не жать по второму разу."""
    try:
        old = callback.message.html_text or callback.message.text or ""
        name = callback.from_user.first_name or str(callback.from_user.id)
        await callback.message.edit_text(
            old + _("pact.mark_suffix").format(mark=mark, name=name),
            parse_mode="HTML",
        )
    except Exception:
        # Сообщение старше двух суток или без текста — Telegram править не
        # даст. Отметка уже сохранена, молчим.
        logger.debug("pact.seal_failed", exc_info=True)


def _is_missing_table(exc: Exception) -> bool:
    try:
        from asyncpg.exceptions import UndefinedTableError
    except ImportError:
        return False
    return isinstance(exc, UndefinedTableError)


_HANDLERS: Dict[str, Callable[[CallbackQuery, str, str], Awaitable[None]]] = {
    "block_radar": _block_radar,
}
