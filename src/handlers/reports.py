"""Обработчики для раздела отчётов по нарушениям."""
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.types import CallbackQuery
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe
from src.keyboards.reports_menu import (
    reports_back_keyboard,
    reports_custom_period_keyboard,
    reports_history_keyboard,
    reports_menu_keyboard,
    reports_schedule_keyboard,
    reports_view_keyboard,
)
from src.services.config_service import config_service
from src.services.database import db_service
from src.services.report_scheduler import get_report_scheduler
from src.services.violation_reports import ReportType, violation_report_service
from src.utils.logger import logger

router = Router(name="reports")


@router.callback_query(F.data == "menu:reports")
async def show_reports_menu(callback: CallbackQuery) -> None:
    """Показывает главное меню отчётов."""
    text = (
        "<b>📊 Отчёты по нарушениям</b>\n\n"
        "Здесь вы можете:\n"
        "• Сгенерировать отчёт за период\n"
        "• Просмотреть историю отчётов\n"
        "• Настроить расписание автоматических отчётов"
    )
    await _edit_text_safe(callback.message, text, reply_markup=reports_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "reports:menu")
async def show_reports_menu_alt(callback: CallbackQuery) -> None:
    """Альтернативный callback для меню отчётов."""
    await show_reports_menu(callback)


@router.callback_query(F.data.startswith("reports:generate:"))
async def generate_report(callback: CallbackQuery) -> None:
    """Генерирует и отправляет отчёт."""
    report_type_str = callback.data.split(":")[2]

    report_type_map = {
        "daily": ReportType.DAILY,
        "weekly": ReportType.WEEKLY,
        "monthly": ReportType.MONTHLY
    }

    report_type = report_type_map.get(report_type_str)
    if not report_type:
        await callback.answer("Неизвестный тип отчёта", show_alert=True)
        return

    await callback.answer("Генерирую отчёт...")

    try:
        # Настраиваем параметры
        min_score = config_service.get("reports_min_score", 30.0)
        top_count = config_service.get("reports_top_violators_count", 10)

        violation_report_service.set_min_score(min_score)
        violation_report_service.set_top_violators_limit(top_count)

        # Генерируем отчёт
        report = await violation_report_service.generate_report(report_type, save_to_db=True)

        if report.total_violations == 0:
            text = (
                "<b>📊 Отчёт сгенерирован</b>\n\n"
                f"Период: {report.period_start.strftime('%d.%m.%Y')} — "
                f"{(report.period_end - timedelta(seconds=1)).strftime('%d.%m.%Y')}\n\n"
                "✅ <i>За указанный период нарушений не обнаружено</i>"
            )
            await _edit_text_safe(callback.message, text, reply_markup=reports_back_keyboard(), parse_mode="HTML")
        else:
            # Отправляем отчёт
            await callback.message.edit_text(report.message_text, parse_mode="HTML", reply_markup=reports_back_keyboard())

    except Exception as e:
        logger.error("Error generating report: %s", e, exc_info=True)
        await callback.answer("Ошибка при генерации отчёта", show_alert=True)


@router.callback_query(F.data == "reports:custom")
async def show_custom_period_menu(callback: CallbackQuery) -> None:
    """Показывает меню выбора периода для кастомного отчёта."""
    text = (
        "<b>📅 Отчёт за произвольный период</b>\n\n"
        "Выберите период для генерации отчёта:"
    )
    await _edit_text_safe(callback.message, text, reply_markup=reports_custom_period_keyboard(), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:custom:"))
async def generate_custom_report(callback: CallbackQuery) -> None:
    """Генерирует отчёт за произвольный период."""
    try:
        days = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный период", show_alert=True)
        return

    await callback.answer("Генерирую отчёт...")

    try:
        # Рассчитываем период
        now = datetime.now(timezone.utc)
        end_date = now
        start_date = now - timedelta(days=days)

        # Настраиваем параметры
        min_score = config_service.get("reports_min_score", 30.0)
        top_count = config_service.get("reports_top_violators_count", 10)

        violation_report_service.set_min_score(min_score)
        violation_report_service.set_top_violators_limit(top_count)

        # Генерируем отчёт
        report = await violation_report_service.get_custom_report(start_date, end_date, min_score)

        if report.total_violations == 0:
            text = (
                "<b>📊 Отчёт сгенерирован</b>\n\n"
                f"Период: последние {days} дней\n\n"
                "✅ <i>За указанный период нарушений не обнаружено</i>"
            )
            await _edit_text_safe(callback.message, text, reply_markup=reports_back_keyboard(), parse_mode="HTML")
        else:
            # Модифицируем заголовок отчёта
            report.message_text = report.message_text.replace(
                "Ежедневный отчёт по нарушениям",
                f"Отчёт за последние {days} дней"
            )
            await callback.message.edit_text(report.message_text, parse_mode="HTML", reply_markup=reports_back_keyboard())

    except Exception as e:
        logger.error("Error generating custom report: %s", e, exc_info=True)
        await callback.answer("Ошибка при генерации отчёта", show_alert=True)


@router.callback_query(F.data == "reports:history")
async def show_reports_history(callback: CallbackQuery) -> None:
    """Показывает историю отчётов."""
    reports = await db_service.get_reports_history(limit=50)

    if not reports:
        text = (
            "<b>📜 История отчётов</b>\n\n"
            "<i>Отчёты пока не генерировались</i>"
        )
        await _edit_text_safe(callback.message, text, reply_markup=reports_back_keyboard(), parse_mode="HTML")
        return

    text = (
        "<b>📜 История отчётов</b>\n\n"
        "Выберите отчёт для просмотра:"
    )
    await _edit_text_safe(callback.message, text, reply_markup=reports_history_keyboard(reports), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:history:page:"))
async def show_reports_history_page(callback: CallbackQuery) -> None:
    """Показывает страницу истории отчётов."""
    try:
        page = int(callback.data.split(":")[3])
    except (IndexError, ValueError):
        page = 0

    reports = await db_service.get_reports_history(limit=50)

    text = (
        "<b>📜 История отчётов</b>\n\n"
        "Выберите отчёт для просмотра:"
    )
    await _edit_text_safe(callback.message, text, reply_markup=reports_history_keyboard(reports, page), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:view:"))
async def view_report(callback: CallbackQuery) -> None:
    """Показывает сохранённый отчёт."""
    try:
        report_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID отчёта", show_alert=True)
        return

    # Получаем отчёт из БД
    reports = await db_service.get_reports_history(limit=100)
    report = next((r for r in reports if r.get('id') == report_id), None)

    if not report:
        await callback.answer("Отчёт не найден", show_alert=True)
        return

    message_text = report.get('message_text')
    if message_text:
        await callback.message.edit_text(message_text, parse_mode="HTML", reply_markup=reports_view_keyboard(report_id))
    else:
        # Если текст не сохранён, показываем сводку
        text = (
            f"<b>📊 Отчёт #{report_id}</b>\n\n"
            f"Тип: {report.get('report_type', 'неизвестен')}\n"
            f"Период: {report.get('period_start', '?').strftime('%d.%m.%Y') if report.get('period_start') else '?'} — "
            f"{report.get('period_end', '?').strftime('%d.%m.%Y') if report.get('period_end') else '?'}\n"
            f"Нарушений: {report.get('total_violations', 0)}\n"
            f"Критичных: {report.get('critical_count', 0)}\n"
            f"Предупреждений: {report.get('warning_count', 0)}\n"
            f"Пользователей: {report.get('unique_users', 0)}"
        )
        await _edit_text_safe(callback.message, text, reply_markup=reports_view_keyboard(report_id), parse_mode="HTML")


@router.callback_query(F.data.startswith("reports:forward:"))
async def forward_report(callback: CallbackQuery) -> None:
    """Пересылает отчёт в текущий чат."""
    try:
        report_id = int(callback.data.split(":")[2])
    except (IndexError, ValueError):
        await callback.answer("Некорректный ID отчёта", show_alert=True)
        return

    # Получаем отчёт из БД
    reports = await db_service.get_reports_history(limit=100)
    report = next((r for r in reports if r.get('id') == report_id), None)

    if not report or not report.get('message_text'):
        await callback.answer("Отчёт не найден или текст недоступен", show_alert=True)
        return

    # Отправляем как новое сообщение
    await callback.message.answer(report['message_text'], parse_mode="HTML")
    await callback.answer("Отчёт отправлен")


@router.callback_query(F.data == "reports:schedule")
async def show_reports_schedule(callback: CallbackQuery) -> None:
    """Показывает расписание отчётов."""
    scheduler = get_report_scheduler()

    if scheduler:
        schedule = await scheduler.get_next_report_times()
    else:
        schedule = {"reports_enabled": False}

    # Формируем текст
    lines = ["<b>⏰ Расписание отчётов</b>", ""]

    if not schedule.get("reports_enabled", True):
        lines.append("❌ <i>Автоматические отчёты отключены</i>")
    else:
        lines.append("✅ <i>Автоматические отчёты включены</i>")
        lines.append("")

        # Ежедневные
        daily = schedule.get("daily")
        if daily and daily.get("enabled"):
            lines.append(f"📅 <b>Ежедневный:</b> {daily.get('time', '09:00')} UTC")
            if daily.get("last_sent"):
                lines.append(f"   <i>Последний: {daily['last_sent']}</i>")
        else:
            lines.append("📅 <b>Ежедневный:</b> <i>выключен</i>")

        # Еженедельные
        weekly = schedule.get("weekly")
        if weekly and weekly.get("enabled"):
            lines.append(f"📆 <b>Еженедельный:</b> {weekly.get('day', 'Пн')} {weekly.get('time', '10:00')} UTC")
            if weekly.get("last_sent"):
                lines.append(f"   <i>Последний: {weekly['last_sent']}</i>")
        else:
            lines.append("📆 <b>Еженедельный:</b> <i>выключен</i>")

        # Ежемесячные
        monthly = schedule.get("monthly")
        if monthly and monthly.get("enabled"):
            lines.append(f"🗓️ <b>Ежемесячный:</b> {monthly.get('day', 1)}-го числа в {monthly.get('time', '10:00')} UTC")
            if monthly.get("last_sent"):
                lines.append(f"   <i>Последний: {monthly['last_sent']}</i>")
        else:
            lines.append("🗓️ <b>Ежемесячный:</b> <i>выключен</i>")

    lines.append("")
    lines.append("<i>Для изменения расписания используйте настройки</i>")

    text = "\n".join(lines)
    await _edit_text_safe(callback.message, text, reply_markup=reports_schedule_keyboard(schedule), parse_mode="HTML")


@router.callback_query(F.data == "reports:toggle")
async def toggle_reports(callback: CallbackQuery) -> None:
    """Переключает глобальное включение/выключение отчётов."""
    current = config_service.get("reports_enabled", True)
    new_value = not current

    success = await config_service.set("reports_enabled", new_value)

    if success:
        status = "включены" if new_value else "выключены"
        await callback.answer(f"Автоматические отчёты {status}", show_alert=False)
        # Обновляем экран расписания
        await show_reports_schedule(callback)
    else:
        await callback.answer("Ошибка при сохранении настройки", show_alert=True)
