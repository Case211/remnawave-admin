"""Кнопки быстрых действий под уведомлением о повторных пробных с одного адреса.

Callback data: ``ipact:<action>:<ip>``
Действия: block (в стоп-лист), users (кто там сидит), mute (замолчать про адрес).

Действие тут — по адресу, а не по одному аккаунту: смысл сигнала в том, что
подписок несколько, и блокировать поштучно бессмысленно.
"""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from shared.database import db_service
from src.utils.auth import BotAdmin
from src.utils.formatters import _esc

logger = logging.getLogger(__name__)
router = Router()

# Сколько молчать про адрес после «не напоминать»
MUTE_DAYS = 30
MUTE_SOURCE = "ip_trial_muted"


@router.callback_query(F.data.startswith("ipact:"))
async def handle_ip_action(callback: CallbackQuery, admin: BotAdmin) -> None:
    parts = callback.data.split(":", 2)
    if len(parts) < 3:
        await callback.answer("Некорректный формат", show_alert=True)
        return

    _, action, ip = parts
    admin_name = callback.from_user.first_name or str(callback.from_user.id)
    logger.info("IP action: %s on %s by %s", action, ip, admin_name)

    # Право то же, что и на разбор нарушений: стоп-лист адресов — мера того же
    # порядка, что блокировка юзера, и кнопка в чате не должна её удешевлять
    if action in ("block", "mute"):
        if not await admin.has_permission("violations", "resolve"):
            await callback.answer("Недостаточно прав", show_alert=True)
            return

    if action == "block":
        await _block_ip(callback, ip, admin, admin_name)
    elif action == "users":
        await _show_users(callback, ip)
    elif action == "mute":
        await _mute_ip(callback, ip, admin_name)
    else:
        await callback.answer("Неизвестное действие", show_alert=True)


async def _block_ip(callback: CallbackQuery, ip: str, admin: BotAdmin, admin_name: str) -> None:
    try:
        entry = await db_service.add_blocked_ip(
            ip_cidr=ip,
            reason="Повторные пробные подписки с одного адреса",
            admin_id=getattr(admin, "account_id", None),
            admin_username=admin_name,
        )
    except Exception as e:  # noqa: BLE001
        logger.error("IP block failed for %s: %s", ip, e)
        await callback.answer("Не удалось заблокировать", show_alert=True)
        return

    if entry is None:
        await callback.answer("Адрес уже в стоп-листе", show_alert=True)
        return

    await callback.answer(f"Адрес {ip} в стоп-листе")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass


async def _show_users(callback: CallbackQuery, ip: str) -> None:
    """Кто заходил с этого адреса — списком, без ухода из чата."""
    try:
        groups = await db_service.get_shared_ip_accounts(min_accounts=1, days=30, limit=200)
    except Exception as e:  # noqa: BLE001
        logger.error("IP users lookup failed for %s: %s", ip, e)
        await callback.answer("Не удалось получить список", show_alert=True)
        return

    group = next((g for g in groups if g.get("ip") == ip), None)
    users = (group or {}).get("users") or []
    if not users:
        await callback.answer("Подключений с этого адреса не найдено", show_alert=True)
        return

    lines = [f"<b>{_esc(ip)}</b> — пробных подписок: {len(users)}", ""]
    for user in sorted(users, key=lambda u: u.get("conns") or 0, reverse=True)[:15]:
        name = user.get("username") or str(user.get("uuid") or "")[:8]
        state = "активна" if user.get("is_active") else "неактивна"
        lines.append(
            f"• <code>{_esc(name)}</code> — подключений {int(user.get('conns') or 0)}, {state}"
        )
    await callback.message.answer("\n".join(lines), parse_mode="HTML")
    await callback.answer()


async def _mute_ip(callback: CallbackQuery, ip: str, admin_name: str) -> None:
    """Отметка «разобрано»: сторож перестаёт напоминать про этот адрес.

    Пишем в ту же таблицу уведомлений, откуда сторож берёт историю, — отдельная
    таблица ради одной отметки не нужна, а решение админа переживает рестарт.
    """
    try:
        async with db_service.acquire() as conn:
            await conn.execute(
                "INSERT INTO notifications (admin_id, type, severity, title, body, source, source_id) "
                "VALUES (NULL, $1, $2, $3, $4, $5, $6)",
                "info", "info",
                "Адрес отмечен как разобранный",
                f"{ip} — сигналы отключены на {MUTE_DAYS} дней ({admin_name})",
                MUTE_SOURCE, ip,
            )
    except Exception as e:  # noqa: BLE001
        logger.error("IP mute failed for %s: %s", ip, e)
        await callback.answer("Не удалось отложить", show_alert=True)
        return

    await callback.answer(f"Про {ip} не напомню {MUTE_DAYS} дней")
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
