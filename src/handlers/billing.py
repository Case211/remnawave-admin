"""Обработчики для работы с биллингом и провайдерами."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin, _send_clean_message
from src.handlers.state import PENDING_INPUT
from src.keyboards.billing_menu import billing_menu_keyboard
from src.keyboards.billing_nodes_menu import billing_nodes_menu_keyboard
from src.keyboards.navigation import NavTarget, input_keyboard, nav_row
from src.keyboards.providers_menu import providers_menu_keyboard
from src.services.api_client import ApiClientError, UnauthorizedError, api_client
from src.utils.formatters import build_billing_history, build_billing_nodes, build_infra_providers, format_datetime
from src.utils.logger import logger

# Функции перенесены из basic.py

router = Router(name="billing")


def _billing_providers_keyboard(providers: list[dict], action_prefix: str, nav_target: str = NavTarget.BILLING_MENU) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера в биллинге."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"billing:provider:{action_prefix}:{uuid}")])
    rows.append(nav_row(nav_target))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _providers_select_keyboard(providers: list[dict], action: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера для обновления или удаления."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"providers:{action}_select:{uuid}")])
    rows.append(nav_row(NavTarget.BILLING_OVERVIEW))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _fetch_billing_text() -> str:
    """Получает текст со списком записей биллинга."""
    try:
        data = await api_client.get_infra_billing_history()
        records = data.get("response", {}).get("records", [])
        return build_billing_history(records, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing fetch failed")
        return _("errors.generic")


async def _fetch_providers_text() -> str:
    """Получает текст со списком провайдеров."""
    try:
        data = await api_client.get_infra_providers()
        providers = data.get("response", {}).get("providers", [])
        return build_infra_providers(providers, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Providers fetch failed")
        return _("errors.generic")


async def _fetch_billing_nodes_text() -> str:
    """Получает текст со списком биллинга нод."""
    try:
        data = await api_client.get_infra_billing_nodes()
        return build_billing_nodes(data, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing nodes fetch failed")
        return _("errors.generic")


async def _fetch_billing_stats_text() -> str:
    """Статистика по биллингу (история платежей)."""
    try:
        data = await api_client.get_infra_billing_history()
        records = data.get("response", {}).get("records", [])

        if not records:
            return f"*{_('billing.stats_title')}*\n\n{_('billing.empty')}"

        # Вычисляем статистику
        total_amount = sum(float(rec.get("amount", 0)) for rec in records)
        total_records = len(records)

        # Группируем по провайдерам
        by_provider: dict[str, dict] = {}
        for rec in records:
            provider = rec.get("provider", {})
            provider_name = provider.get("name", "Unknown")
            amount = float(rec.get("amount", 0))
            if provider_name not in by_provider:
                by_provider[provider_name] = {"count": 0, "amount": 0.0}
            by_provider[provider_name]["count"] += 1
            by_provider[provider_name]["amount"] += amount

        # Сортируем по сумме
        sorted_providers = sorted(by_provider.items(), key=lambda x: x[1]["amount"], reverse=True)

        lines = [
            f"*{_('billing.stats_title')}*",
            "",
            f"*{_('billing.stats_summary')}*",
            f"  {_('billing.stats_total_amount').format(amount=f'*{total_amount:.2f}*')}",
            f"  {_('billing.stats_total_records').format(count=f'*{total_records}*')}",
            "",
            f"*{_('billing.stats_by_provider')}*",
        ]

        for provider_name, stats in sorted_providers[:10]:
            lines.append(f"  • *{provider_name}*: `{stats['count']}` записей, сумма `{stats['amount']:.2f}`")

        if len(sorted_providers) > 10:
            lines.append("")
            lines.append(_("billing.more").format(count=len(sorted_providers) - 10))

        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing stats fetch failed")
        return _("errors.generic")


async def _fetch_billing_nodes_stats_text() -> str:
    """Статистика по биллингу нод."""
    try:
        data = await api_client.get_infra_billing_nodes()
        resp = data.get("response", data) or {}
        nodes = resp.get("billingNodes", []) or []
        stats = resp.get("stats", {}) or {}

        if not nodes:
            return f"*{_('billing_nodes.stats_title')}*\n\n{_('billing_nodes.empty')}"

        # Группируем по провайдерам
        by_provider: dict[str, dict] = {}
        upcoming_count = 0
        from datetime import datetime

        for item in nodes:
            provider = item.get("provider", {})
            provider_name = provider.get("name", "Unknown")
            if provider_name not in by_provider:
                by_provider[provider_name] = {"count": 0}
            by_provider[provider_name]["count"] += 1

            # Проверяем ближайшие платежи (в течение 7 дней)
            next_billing = item.get("nextBillingAt")
            if next_billing:
                try:
                    billing_date = datetime.fromisoformat(next_billing.replace("Z", "+00:00"))
                    days_until = (billing_date - datetime.now(billing_date.tzinfo)).days
                    if 0 <= days_until <= 7:
                        upcoming_count += 1
                except Exception:
                    pass

        upcoming_val = stats.get("upcomingNodesCount", upcoming_count)
        month_val = stats.get("currentMonthPayments", "—")
        total_val = stats.get("totalSpent", "—")

        lines = [
            f"*{_('billing_nodes.stats_title')}*",
            "",
            f"*{_('billing_nodes.stats_summary')}*",
            f"  {_('billing_nodes.stats_text').format(upcoming=f'*{upcoming_val}*', month=f'`{month_val}`', total=f'*{total_val}*')}",
            "",
            f"*{_('billing_nodes.stats_by_provider')}*",
        ]

        # Сортируем по количеству нод
        sorted_providers = sorted(by_provider.items(), key=lambda x: x[1]["count"], reverse=True)
        for provider_name, provider_stats in sorted_providers[:10]:
            lines.append(f"  • *{provider_name}*: `{provider_stats['count']}` нод")

        if len(sorted_providers) > 10:
            lines.append("")
            lines.append(_("billing_nodes.more").format(count=len(sorted_providers) - 10))

        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Billing nodes stats fetch failed")
        return _("errors.generic")


def _billing_providers_keyboard(providers: list[dict], action_prefix: str, nav_target: str = NavTarget.BILLING_MENU) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера в биллинге."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"billing:provider:{action_prefix}:{uuid}")])
    rows.append(nav_row(nav_target))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _providers_select_keyboard(providers: list[dict], action: str) -> InlineKeyboardMarkup:
    """Клавиатура для выбора провайдера для обновления или удаления."""
    rows: list[list[InlineKeyboardButton]] = []
    for provider in sorted(providers, key=lambda p: p.get("name", ""))[:10]:
        name = provider.get("name", "n/a")
        uuid = provider.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"providers:{action}_select:{uuid}")])
    rows.append(nav_row(NavTarget.BILLING_OVERVIEW))
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _billing_nodes_keyboard(nodes: list[dict], action_prefix: str, provider_uuid: str = "", nav_target: str = NavTarget.BILLING_NODES_MENU) -> InlineKeyboardMarkup:
    """Клавиатура для выбора ноды в биллинге."""
    rows: list[list[InlineKeyboardButton]] = []
    for node in sorted(nodes, key=lambda n: n.get("name", ""))[:10]:
        name = node.get("name", "n/a")
        uuid = node.get("uuid", "")
        country = node.get("countryCode", "")
        label = f"{name} ({country})" if country else name
        callback_data = f"billing_nodes:node:{action_prefix}:{uuid}"
        if provider_uuid:
            callback_data += f":{provider_uuid}"
        rows.append([InlineKeyboardButton(text=label, callback_data=callback_data)])
    rows.append(nav_row(nav_target))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _handle_provider_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод для создания/обновления/удаления провайдера."""
    action = ctx.get("action")
    user_id = message.from_user.id
    text = message.text.strip()
    data = ctx.setdefault("data", {})
    stage = ctx.get("stage", None)

    try:
        if action == "provider_create":
            # Пошаговый ввод для создания провайдера
            if stage == "name":
                if not text:
                    await _send_clean_message(message, _("provider.prompt_name"), reply_markup=input_keyboard(action), parse_mode="Markdown")
                    PENDING_INPUT[user_id] = ctx
                    return
                data["name"] = text
                ctx["stage"] = "favicon"
                PENDING_INPUT[user_id] = ctx
                await _send_clean_message(
                    message,
                    _("provider.prompt_favicon").format(name=data["name"]),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:favicon"),
                    parse_mode="Markdown",
                )
                return

            elif stage == "favicon":
                favicon = text if text else None
                data["favicon"] = favicon if favicon else "—"
                ctx["stage"] = "login_url"
                PENDING_INPUT[user_id] = ctx
                favicon_display = favicon if favicon else "—"
                await _send_clean_message(
                    message,
                    _("provider.prompt_login_url").format(name=data["name"], favicon=favicon_display),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:login_url"),
                    parse_mode="Markdown",
                )
                return

            elif stage == "login_url":
                login_url = text if text else None
                data["login_url"] = login_url
                # Создаем провайдера
                await api_client.create_infra_provider(
                    name=data["name"],
                    favicon_link=data.get("favicon") if data.get("favicon") != "—" else None,
                    login_url=login_url,
                )
                PENDING_INPUT.pop(user_id, None)
                await _send_clean_message(message, _("provider.created"), reply_markup=providers_menu_keyboard())
                return

        elif action == "provider_update":
            # Пошаговый ввод для обновления провайдера
            if stage == "name":
                # Обновляем имя
                new_name = text if text else None
                if new_name:
                    data["name"] = new_name
                else:
                    data["name"] = data.get("current_name", "")
                ctx["stage"] = "favicon"
                PENDING_INPUT[user_id] = ctx
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_favicon").format(
                        current_name=data["name"], current_favicon=data.get("current_favicon", "—") or "—"
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:favicon"),
                    parse_mode="Markdown",
                )
                return

            elif stage == "favicon":
                # Обновляем favicon
                new_favicon = text if text else None
                if new_favicon:
                    data["favicon"] = new_favicon
                else:
                    data["favicon"] = data.get("current_favicon") or None
                ctx["stage"] = "login_url"
                PENDING_INPUT[user_id] = ctx
                favicon_display = data["favicon"] if data["favicon"] else "—"
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_login_url").format(
                        current_name=data.get("name", ""),
                        current_favicon=favicon_display,
                        current_login_url=data.get("current_login_url", "—") or "—",
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:login_url"),
                    parse_mode="Markdown",
                )
                return

            elif stage == "login_url":
                # Обновляем login_url
                new_login_url = text if text else None
                if new_login_url:
                    data["login_url"] = new_login_url
                else:
                    # Оставляем текущее значение
                    data["login_url"] = data.get("current_login_url") or None

                # Обновляем провайдера - передаем только измененные значения
                provider_uuid = ctx.get("provider_uuid")
                current_name = data.get("current_name", "")
                current_favicon = data.get("current_favicon") or ""
                current_login_url = data.get("current_login_url") or ""

                # Определяем, что изменилось
                name = None
                if data.get("name") and data.get("name") != current_name:
                    name = data.get("name")

                favicon = None
                new_favicon_val = data.get("favicon") or ""
                if new_favicon_val != current_favicon:
                    favicon = new_favicon_val if new_favicon_val else None

                login_url = None
                new_login_url_val = data.get("login_url") or ""
                if new_login_url_val != current_login_url:
                    login_url = new_login_url_val if new_login_url_val else None

                await api_client.update_infra_provider(provider_uuid, name=name, favicon_link=favicon, login_url=login_url)
                PENDING_INPUT.pop(user_id, None)
                await _send_clean_message(message, _("provider.updated"), reply_markup=providers_menu_keyboard())
                return
        elif action == "provider_delete":
            parts = text.split()
            if len(parts) != 1:
                raise ValueError
            await api_client.delete_infra_provider(parts[0])
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, _("provider.deleted"), reply_markup=providers_menu_keyboard())
        else:
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, _("errors.generic"), reply_markup=providers_menu_keyboard())
            return
    except ValueError:
        if action == "provider_create" and stage:
            # Сохраняем контекст для повторного запроса
            PENDING_INPUT[user_id] = ctx
            if stage == "name":
                await _send_clean_message(message, _("provider.prompt_name"), reply_markup=input_keyboard(action), parse_mode="Markdown")
            elif stage == "favicon":
                await _send_clean_message(
                    message,
                    _("provider.prompt_favicon").format(name=data.get("name", "")),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:favicon"),
                    parse_mode="Markdown",
                )
            elif stage == "login_url":
                await _send_clean_message(
                    message,
                    _("provider.prompt_login_url").format(name=data.get("name", ""), favicon=data.get("favicon", "—")),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_create:login_url"),
                    parse_mode="Markdown",
                )
        elif action == "provider_update" and stage:
            # Сохраняем контекст для повторного запроса
            PENDING_INPUT[user_id] = ctx
            if stage == "name":
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_name").format(current_name=data.get("current_name", "")),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:name"),
                    parse_mode="Markdown",
                )
            elif stage == "favicon":
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_favicon").format(
                        current_name=data.get("name", data.get("current_name", "")),
                        current_favicon=data.get("current_favicon", "—") or "—",
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:favicon"),
                    parse_mode="Markdown",
                )
            elif stage == "login_url":
                await _send_clean_message(
                    message,
                    _("provider.prompt_update_login_url").format(
                        current_name=data.get("name", data.get("current_name", "")),
                        current_favicon=data.get("favicon", data.get("current_favicon", "—")) or "—",
                        current_login_url=data.get("current_login_url", "—") or "—",
                    ),
                    reply_markup=input_keyboard(action, allow_skip=True, skip_callback="input:skip:provider_update:login_url"),
                    parse_mode="Markdown",
                )
        elif action == "provider_delete":
            prompt_key = "provider.prompt_delete"
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _(prompt_key), reply_markup=input_keyboard(action))
        else:
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("errors.generic"), reply_markup=input_keyboard(action))
    except UnauthorizedError:
        PENDING_INPUT.pop(user_id, None)
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=providers_menu_keyboard())
    except ApiClientError:
        PENDING_INPUT.pop(user_id, None)
        logger.exception("❌ Provider action failed: %s", action)
        await _send_clean_message(message, _("provider.invalid"), reply_markup=providers_menu_keyboard())


async def _handle_billing_history_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод для создания/удаления записей биллинга."""
    action = ctx.get("action")
    text = message.text.strip()
    user_id = message.from_user.id
    data = ctx.setdefault("data", {})
    stage = ctx.get("stage", None)

    try:
        if action == "billing_history_create":
            # Пошаговый ввод для создания записи биллинга
            if stage == "amount":
                try:
                    amount = float(text)
                except ValueError:
                    PENDING_INPUT[user_id] = ctx
                    await _send_clean_message(message, _("billing.prompt_amount"), reply_markup=input_keyboard(action), parse_mode="Markdown")
                    return
                data["amount"] = amount
                ctx["stage"] = "billed_at"
                PENDING_INPUT[user_id] = ctx
                provider_name = ctx.get("provider_name", "—")
                await _send_clean_message(
                    message, _("billing.prompt_billed_at").format(provider_name=provider_name, amount=amount), reply_markup=input_keyboard(action), parse_mode="Markdown"
                )
                return

            elif stage == "billed_at":
                if not text:
                    PENDING_INPUT[user_id] = ctx
                    provider_name = ctx.get("provider_name", "—")
                    amount = data.get("amount", 0)
                    await _send_clean_message(
                        message, _("billing.prompt_billed_at").format(provider_name=provider_name, amount=amount), reply_markup=input_keyboard(action), parse_mode="Markdown"
                    )
                    return
                # Создаем запись биллинга
                provider_uuid = ctx.get("provider_uuid")
                amount = data.get("amount")
                await api_client.create_infra_billing_record(provider_uuid, amount, text)
                billing_text = await _fetch_billing_text()
                PENDING_INPUT.pop(user_id, None)
                await _send_clean_message(message, billing_text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
                return

        elif action == "billing_history_create_amount":
            # Старый формат для обратной совместимости
            parts = text.split()
            if len(parts) < 2:
                raise ValueError
            provider_uuid = ctx.get("provider_uuid")
            amount = float(parts[0])
            billed_at = parts[1]
            await api_client.create_infra_billing_record(provider_uuid, amount, billed_at)
            billing_text = await _fetch_billing_text()
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, billing_text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        elif action == "billing_history_delete":
            parts = text.split()
            if len(parts) != 1:
                raise ValueError
            await api_client.delete_infra_billing_record(parts[0])
            billing_text = await _fetch_billing_text()
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, billing_text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        else:
            PENDING_INPUT.pop(user_id, None)
            await _send_clean_message(message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
            return
    except ValueError:
        if action == "billing_history_create" and stage:
            PENDING_INPUT[user_id] = ctx
            if stage == "amount":
                await _send_clean_message(message, _("billing.prompt_amount"), reply_markup=input_keyboard(action), parse_mode="Markdown")
            elif stage == "billed_at":
                provider_name = ctx.get("provider_name", "—")
                amount = data.get("amount", 0)
                await _send_clean_message(
                    message, _("billing.prompt_billed_at").format(provider_name=provider_name, amount=amount), reply_markup=input_keyboard(action), parse_mode="Markdown"
                )
        elif action == "billing_history_create_amount":
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing.prompt_amount_date"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        else:
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing.prompt_delete"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    except UnauthorizedError:
        PENDING_INPUT.pop(user_id, None)
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    except ApiClientError:
        PENDING_INPUT.pop(user_id, None)
        logger.exception("❌ Billing history action failed: %s", action)
        await _send_clean_message(message, _("billing.invalid"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


async def _handle_billing_nodes_input(message: Message, ctx: dict) -> None:
    """Обрабатывает ввод для создания/обновления биллинга нод."""
    action = ctx.get("action")
    text = (message.text or "").strip()
    user_id = message.from_user.id

    try:
        if action == "billing_nodes_create_confirm":
            # Провайдер и нода уже выбраны, дата опциональна
            provider_uuid = ctx.get("provider_uuid")
            node_uuid = ctx.get("node_uuid")
            next_billing_at = text if text else None
            await api_client.create_infra_billing_node(provider_uuid, node_uuid, next_billing_at)
            billing_text = await _fetch_billing_nodes_text()
            await _send_clean_message(message, billing_text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            PENDING_INPUT.pop(user_id, None)
        elif action == "billing_nodes_update_date":
            # UUID записи биллинга уже в контексте
            if not text:
                raise ValueError
            record_uuid = ctx.get("record_uuid")
            if not record_uuid:
                await _send_clean_message(message, _("billing_nodes.not_found"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                PENDING_INPUT.pop(user_id, None)
                return
            await api_client.update_infra_billing_nodes([record_uuid], text)
            billing_text = await _fetch_billing_nodes_text()
            await _send_clean_message(message, billing_text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            PENDING_INPUT.pop(user_id, None)
        else:
            await _send_clean_message(message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            PENDING_INPUT.pop(user_id, None)
            return
    except ValueError:
        if action == "billing_nodes_update_date":
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing_nodes.prompt_new_date"), reply_markup=input_keyboard(action), parse_mode="Markdown")
        else:
            PENDING_INPUT[user_id] = ctx
            await _send_clean_message(message, _("billing_nodes.prompt_date_optional"), reply_markup=input_keyboard(action), parse_mode="Markdown")
    except UnauthorizedError:
        await _send_clean_message(message, _("errors.unauthorized"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        PENDING_INPUT.pop(user_id, None)
    except ApiClientError:
        logger.exception("❌ Billing nodes action failed: %s", action)
        await _send_clean_message(message, _("billing_nodes.invalid"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        PENDING_INPUT.pop(user_id, None)


@router.callback_query(F.data == "menu:providers")
async def cb_providers(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Провайдеры' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_providers_text()
    await _edit_text_safe(callback.message, text, reply_markup=providers_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("providers:"))
async def cb_providers_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с провайдерами."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else None

    if action == "create":
        PENDING_INPUT[callback.from_user.id] = {"action": "provider_create", "stage": "name", "data": {}}
        await callback.message.edit_text(_("provider.prompt_name"), reply_markup=input_keyboard("provider_create"), parse_mode="Markdown")
    elif action == "update":
        # Показываем список провайдеров для выбора
        try:
            providers_data = await api_client.get_infra_providers()
            providers = providers_data.get("response", {}).get("providers", [])
            if not providers:
                await callback.message.edit_text(_("provider.empty"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
                return
            keyboard = _providers_select_keyboard(providers, "update")
            await callback.message.edit_text(_("provider.select_update"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
    elif action == "update_select":
        # Начинаем редактирование выбранного провайдера
        if len(parts) < 3:
            await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
            return
        provider_uuid = parts[2]
        try:
            # Получаем данные провайдера
            provider_data = await api_client.get_infra_provider(provider_uuid)
            provider_info = provider_data.get("response", {})
            current_name = provider_info.get("name", "")
            current_favicon = provider_info.get("faviconLink") or ""
            current_login_url = provider_info.get("loginUrl") or ""

            # Начинаем пошаговое редактирование
            PENDING_INPUT[callback.from_user.id] = {
                "action": "provider_update",
                "stage": "name",
                "provider_uuid": provider_uuid,
                "data": {
                    "current_name": current_name,
                    "current_favicon": current_favicon,
                    "current_login_url": current_login_url,
                },
            }
            await callback.message.edit_text(
                _("provider.prompt_update_name").format(current_name=current_name),
                reply_markup=input_keyboard("provider_update", allow_skip=True, skip_callback="input:skip:provider_update:name"),
                parse_mode="Markdown",
            )
        except Exception:
            await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete":
        PENDING_INPUT[callback.from_user.id] = {"action": "provider_delete"}
        await callback.message.edit_text(_("provider.prompt_delete"), reply_markup=providers_menu_keyboard())
    else:
        await callback.message.edit_text(_("errors.generic"), reply_markup=providers_menu_keyboard())


@router.callback_query(F.data == "menu:billing")
async def cb_billing(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Биллинг' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_billing_text()
    await _edit_text_safe(callback.message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("billing:"))
async def cb_billing_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с биллингом."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 2:
        await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        return

    action = parts[1]  # Вторая часть после "billing:"

    if action == "stats":
        text = await _fetch_billing_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "create":
        # Показываем список провайдеров для выбора
        try:
            providers_data = await api_client.get_infra_providers()
            providers = providers_data.get("response", {}).get("providers", [])
            if not providers:
                await _edit_text_safe(callback.message, _("billing.no_providers"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
                return
            keyboard = _billing_providers_keyboard(providers, "billing_history_create")
            await _edit_text_safe(callback.message, _("billing.select_provider"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete":
        # Показываем список записей для удаления
        try:
            billing_data = await api_client.get_infra_billing_history()
            records = billing_data.get("response", {}).get("records", [])
            if not records:
                await _edit_text_safe(callback.message, _("billing.empty"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
                return
            rows: list[list[InlineKeyboardButton]] = []
            for rec in records[:10]:
                provider = rec.get("provider", {})
                amount = rec.get("amount", "—")
                date = format_datetime(rec.get("billedAt"))
                record_uuid = rec.get("uuid", "")
                label = f"{amount} — {provider.get('name', '—')} ({date})"
                rows.append([InlineKeyboardButton(text=label, callback_data=f"billing:delete_confirm:{record_uuid}")])
            rows.append(nav_row(NavTarget.BILLING_MENU))
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            await _edit_text_safe(callback.message, _("billing.select_delete"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete_confirm":
        # Подтверждение удаления записи биллинга
        if len(parts) < 3:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
            return
        record_uuid = parts[2]
        try:
            await api_client.delete_infra_billing_record(record_uuid)
            text = await _fetch_billing_text()
            await _edit_text_safe(callback.message, text, reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
        except ApiClientError:
            logger.exception("❌ Billing record delete failed")
            await _edit_text_safe(callback.message, _("billing.invalid"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    elif action == "provider":
        # Обработка выбора провайдера
        if len(parts) < 4:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
            return
        provider_action = parts[2]  # billing_history_create или billing_nodes_create
        provider_uuid = parts[3]

        if provider_action == "billing_history_create":
            # Для создания записи биллинга запрашиваем сумму, затем дату
            try:
                provider_data = await api_client.get_infra_provider(provider_uuid)
                provider_name = provider_data.get("response", {}).get("name", "—")
            except Exception:
                provider_name = "—"
            PENDING_INPUT[callback.from_user.id] = {
                "action": "billing_history_create",
                "stage": "amount",
                "provider_uuid": provider_uuid,
                "provider_name": provider_name,
                "data": {},
            }
            await _edit_text_safe(
                callback.message, _("billing.prompt_amount"), reply_markup=input_keyboard("billing_history_create"), parse_mode="Markdown"
            )
        elif provider_action == "billing_nodes_create":
            # Для создания биллинга ноды нужно показать все ноды системы
            # (можно создать биллинг для любой ноды с указанным провайдером)
            try:
                nodes_data = await api_client.get_nodes()
                all_nodes = nodes_data.get("response", {}).get("nodes", [])
                if not all_nodes:
                    await _edit_text_safe(callback.message, _("billing_nodes.no_nodes"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                    return
                keyboard = _billing_nodes_keyboard(all_nodes, "billing_nodes_create", provider_uuid)
                await _edit_text_safe(callback.message, _("billing_nodes.select_node"), reply_markup=keyboard, parse_mode="Markdown")
            except Exception:
                await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        else:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")
    else:
        await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "menu:billing_nodes")
async def cb_billing_nodes(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Биллинг нод' в меню."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_billing_nodes_text()
    await _edit_text_safe(callback.message, text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.startswith("billing_nodes:"))
async def cb_billing_nodes_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с биллингом нод."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else None

    if action == "create":
        # Сначала выбираем провайдера
        try:
            providers_data = await api_client.get_infra_providers()
            providers = providers_data.get("response", {}).get("providers", [])
            if not providers:
                await _edit_text_safe(callback.message, _("billing_nodes.no_providers"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                return
            keyboard = _billing_providers_keyboard(providers, "billing_nodes_create", NavTarget.BILLING_NODES_MENU)
            await _edit_text_safe(callback.message, _("billing_nodes.select_provider"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "node":
        # Обработка выбора ноды после выбора провайдера
        if len(parts) < 4:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            return
        node_action = parts[2]  # billing_nodes:node:action:uuid:provider_uuid
        node_uuid = parts[3]
        provider_uuid = parts[4] if len(parts) > 4 else None

        if node_action == "billing_nodes_create" and provider_uuid:
            # Запрашиваем дату следующей оплаты (опционально)
            PENDING_INPUT[callback.from_user.id] = {
                "action": "billing_nodes_create_confirm",
                "provider_uuid": provider_uuid,
                "node_uuid": node_uuid,
            }
            await _edit_text_safe(
                callback.message, _("billing_nodes.prompt_date_optional"), reply_markup=input_keyboard("billing_nodes_create_confirm"), parse_mode="Markdown"
            )
        elif node_action == "billing_nodes_update":
            # Находим UUID записи биллинга для этой ноды
            try:
                nodes_data = await api_client.get_infra_billing_nodes()
                billing_nodes = nodes_data.get("response", {}).get("billingNodes", [])
                record_uuid = None
                for item in billing_nodes:
                    if item.get("node", {}).get("uuid") == node_uuid:
                        record_uuid = item.get("uuid")
                        break
                if not record_uuid:
                    await _edit_text_safe(callback.message, _("billing_nodes.not_found"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                    return
                # Запрашиваем новую дату оплаты
                PENDING_INPUT[callback.from_user.id] = {
                    "action": "billing_nodes_update_date",
                    "record_uuid": record_uuid,
                }
                await _edit_text_safe(
                    callback.message, _("billing_nodes.prompt_new_date"), reply_markup=input_keyboard("billing_nodes_update_date"), parse_mode="Markdown"
                )
            except Exception:
                await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        else:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete_confirm":
        # Подтверждение удаления записи биллинга ноды
        if len(parts) < 3:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
            return
        record_uuid = parts[2]  # billing_nodes:delete_confirm:uuid
        try:
            await api_client.delete_infra_billing_node(record_uuid)
            text = await _fetch_billing_nodes_text()
            await _edit_text_safe(callback.message, text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
        except ApiClientError:
            logger.exception("❌ Billing node delete failed")
            await _edit_text_safe(callback.message, _("billing_nodes.invalid"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "update":
        # Показываем список нод с биллингом для обновления
        try:
            nodes_data = await api_client.get_infra_billing_nodes()
            billing_nodes = nodes_data.get("response", {}).get("billingNodes", [])
            if not billing_nodes:
                await _edit_text_safe(callback.message, _("billing_nodes.empty"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                return
            # Создаем список нод для выбора
            nodes_list = [item.get("node", {}) for item in billing_nodes if item.get("node")]
            keyboard = _billing_nodes_keyboard(nodes_list, "billing_nodes_update")
            await _edit_text_safe(callback.message, _("billing_nodes.select_nodes_update"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "stats":
        # Показываем статистику биллинга нод
        text = await _fetch_billing_nodes_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
    elif action == "delete":
        # Показываем список нод с биллингом для удаления
        try:
            nodes_data = await api_client.get_infra_billing_nodes()
            billing_nodes = nodes_data.get("response", {}).get("billingNodes", [])
            if not billing_nodes:
                await _edit_text_safe(callback.message, _("billing_nodes.empty"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")
                return
            rows: list[list[InlineKeyboardButton]] = []
            for item in billing_nodes[:10]:
                node = item.get("node", {})
                provider = item.get("provider", {})
                next_billing = item.get("nextBillingAt", "—")
                record_uuid = item.get("uuid", "")
                node_name = node.get("name", "—")
                provider_name = provider.get("name", "—")
                label = f"{node_name} ({provider_name}) — {next_billing}"
                rows.append([InlineKeyboardButton(text=label, callback_data=f"billing_nodes:delete_confirm:{record_uuid}")])
            rows.append(nav_row(NavTarget.BILLING_NODES_MENU))
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            await _edit_text_safe(callback.message, _("billing_nodes.select_delete"), reply_markup=keyboard, parse_mode="Markdown")
        except Exception:
            await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=billing_nodes_menu_keyboard(), parse_mode="Markdown")

