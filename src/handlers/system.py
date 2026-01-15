"""Обработчики системных операций (health, stats, system nodes)."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin
from src.handlers.state import PENDING_INPUT
from src.keyboards.main_menu import system_menu_keyboard
from src.keyboards.navigation import NavTarget, nav_row
from src.keyboards.stats_menu import stats_menu_keyboard, stats_period_keyboard
from src.keyboards.system_nodes import system_nodes_keyboard
from src.services.api_client import ApiClientError, UnauthorizedError, api_client
from src.utils.formatters import build_bandwidth_stats, format_bytes, format_datetime, format_uptime
from src.utils.logger import logger

# Временные импорты из других модулей
# TODO: Импортировать _fetch_nodes_text из nodes.py после завершения рефакторинга
from src.handlers.nodes import _fetch_nodes_text

router = Router(name="system")


def _system_nodes_profiles_keyboard(profiles: list[dict], prefix: str = "system:nodes:profile:") -> InlineKeyboardMarkup:
    """Клавиатура для выбора профиля конфигурации для системных нод."""
    rows: list[list[InlineKeyboardButton]] = []
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        name = profile.get("name", "n/a")
        uuid = profile.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"{prefix}{uuid}")])
    rows.append(nav_row(NavTarget.NODES_LIST))
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _fetch_health_text() -> str:
    """Получает текст для отображения health check."""
    try:
        data = await api_client.get_health()
        pm2 = data.get("response", {}).get("pm2Stats", [])
        if not pm2:
            return f"*{_('health.title')}*\n\n{_('health.empty')}"
        lines = [f"*{_('health.title')}*", ""]
        for proc in pm2:
            name = proc.get("name", "n/a")
            cpu = proc.get("cpu", "—")
            memory = proc.get("memory", "—")
            lines.append(f"  • *{name}*")
            lines.append(f"    CPU: `{cpu}%` | RAM: `{memory}`")
        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Health check failed")
        return _("errors.generic")


async def _fetch_panel_stats_text() -> str:
    """Статистика панели (пользователи, ноды, хосты, ресурсы)."""
    try:
        # Получаем основную статистику системы
        data = await api_client.get_stats()
        res = data.get("response", {})
        users = res.get("users", {})
        online = res.get("onlineStats", {})
        nodes = res.get("nodes", {})
        status_counts = users.get("statusCounts", {}) or {}
        status_str = ", ".join(f"`{k}`: *{v}*" for k, v in status_counts.items()) if status_counts else "—"

        lines = [
            f"*{_('stats.panel_title')}*",
            "",
            f"*{_('stats.users_section')}*",
            f"  {_('stats.users').format(total=users.get('totalUsers', '—'))}",
            f"  {_('stats.status_counts').format(counts=status_str)}",
            f"  {_('stats.online').format(now=online.get('onlineNow', '—'), day=online.get('lastDay', '—'), week=online.get('lastWeek', '—'))}",
            "",
            f"*{_('stats.infrastructure_section')}*",
            f"  {_('stats.nodes').format(online=nodes.get('totalOnline', '—'))}",
        ]

        # Добавляем статистику по хостам
        try:
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            total_hosts = len(hosts)
            enabled_hosts = sum(1 for h in hosts if not h.get("isDisabled"))
            disabled_hosts = total_hosts - enabled_hosts
            lines.append(f"  {_('stats.hosts').format(total=total_hosts, enabled=enabled_hosts, disabled=disabled_hosts)}")
        except Exception:
            lines.append(f"  {_('stats.hosts').format(total='—', enabled='—', disabled='—')}")

        # Добавляем статистику по нодам
        try:
            nodes_data = await api_client.get_nodes()
            nodes_list = nodes_data.get("response", [])
            total_nodes = len(nodes_list)
            enabled_nodes = sum(1 for n in nodes_list if not n.get("isDisabled"))
            disabled_nodes = total_nodes - enabled_nodes
            online_nodes = sum(1 for n in nodes_list if n.get("isConnected"))
            lines.append(
                f"  {_('stats.nodes_detailed').format(total=total_nodes, enabled=enabled_nodes, disabled=disabled_nodes, online=online_nodes)}"
            )
        except Exception:
            lines.append(f"  {_('stats.nodes_detailed').format(total='—', enabled='—', disabled='—', online='—')}")

        # Добавляем статистику по ресурсам
        lines.append("")
        lines.append(f"*{_('stats.resources_section')}*")
        try:
            templates_data = await api_client.get_templates()
            templates = templates_data.get("response", {}).get("templates", [])
            lines.append(f"  {_('stats.templates').format(count=len(templates))}")
        except Exception:
            lines.append(f"  {_('stats.templates').format(count='—')}")

        try:
            tokens_data = await api_client.get_tokens()
            tokens = tokens_data.get("response", {}).get("apiKeys", [])
            lines.append(f"  {_('stats.tokens').format(count=len(tokens))}")
        except Exception:
            lines.append(f"  {_('stats.tokens').format(count='—')}")

        try:
            snippets_data = await api_client.get_snippets()
            snippets = snippets_data.get("response", {}).get("snippets", [])
            lines.append(f"  {_('stats.snippets').format(count=len(snippets))}")
        except Exception:
            lines.append(f"  {_('stats.snippets').format(count='—')}")

        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Panel stats fetch failed")
        return _("errors.generic")


async def _fetch_server_stats_text() -> str:
    """Статистика сервера (CPU, RAM, нагрузка, системная информация)."""
    try:
        data = await api_client.get_stats()
        res = data.get("response", {})
        mem = res.get("memory", {})
        cpu = res.get("cpu", {})
        uptime = res.get("uptime", 0)

        # Вычисляем использование памяти в процентах
        mem_total = mem.get("total", 0)
        mem_used = mem.get("used", 0)
        mem_percent = (mem_used / mem_total * 100) if mem_total > 0 else 0

        # Получаем дополнительную информацию о системе
        cpu_usage = cpu.get("usage")
        cpu_load = cpu.get("loadAverage") or cpu.get("load")

        lines = [
            f"*{_('stats.server_title')}*",
            "",
            f"*{_('stats.system_section')}*",
            f"  {_('stats.uptime').format(uptime=format_uptime(uptime))}",
            "",
            f"*{_('stats.cpu_section')}*",
            f"  {_('stats.cpu').format(cores=cpu.get('cores', '—'), physical=cpu.get('physicalCores', '—'))}",
        ]

        if cpu_usage is not None:
            try:
                usage_val = float(cpu_usage) if isinstance(cpu_usage, (int, float, str)) else cpu_usage
                if isinstance(usage_val, (int, float)):
                    lines.append(f"  {_('stats.cpu_usage').format(usage=f'{usage_val:.1f}')}")
                else:
                    lines.append(f"  {_('stats.cpu_usage').format(usage=cpu_usage)}")
            except (ValueError, TypeError):
                pass

        if cpu_load:
            try:
                if isinstance(cpu_load, list):
                    load_str = ", ".join(f"`{float(load):.2f}`" for load in cpu_load[:3] if load is not None)
                    if load_str:
                        lines.append(f"  {_('stats.cpu_load').format(load=load_str)}")
                elif isinstance(cpu_load, (int, float)):
                    lines.append(f"  {_('stats.cpu_load').format(load=f'`{float(cpu_load):.2f}`')}")
            except (ValueError, TypeError):
                pass

        lines.append("")
        lines.append(f"*{_('stats.memory_section')}*")
        lines.append(f"  {_('stats.memory').format(used=format_bytes(mem_used), total=format_bytes(mem_total))}")
        lines.append(f"  {_('stats.memory_percent').format(percent=f'{mem_percent:.1f}%')}")

        mem_free = mem_total - mem_used
        if mem_free > 0:
            lines.append(f"  {_('stats.memory_free').format(free=format_bytes(mem_free))}")

        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Server stats fetch failed")
        return _("errors.generic")


async def _fetch_stats_text() -> str:
    """Получает общую статистику системы."""
    try:
        # Получаем основную статистику системы
        data = await api_client.get_stats()
        res = data.get("response", {})
        mem = res.get("memory", {})
        cpu = res.get("cpu", {})
        users = res.get("users", {})
        online = res.get("onlineStats", {})
        nodes = res.get("nodes", {})
        status_counts = users.get("statusCounts", {}) or {}
        status_str = ", ".join(f"`{k}`: *{v}*" for k, v in status_counts.items()) if status_counts else "—"

        lines = [
            f"*{_('stats.title')}*",
            "",
            f"*{_('stats.system_section')}*",
            f"  {_('stats.uptime').format(uptime=format_uptime(res.get('uptime')))}",
            f"  {_('stats.cpu').format(cores=cpu.get('cores', '—'), physical=cpu.get('physicalCores', '—'))}",
            f"  {_('stats.memory').format(used=format_bytes(mem.get('used')), total=format_bytes(mem.get('total')))}",
            "",
            f"*{_('stats.users_section')}*",
            f"  {_('stats.users').format(total=users.get('totalUsers', '—'))}",
            f"  {_('stats.status_counts').format(counts=status_str)}",
            f"  {_('stats.online').format(now=online.get('onlineNow', '—'), day=online.get('lastDay', '—'), week=online.get('lastWeek', '—'))}",
            "",
            f"*{_('stats.infrastructure_section')}*",
            f"  {_('stats.nodes').format(online=nodes.get('totalOnline', '—'))}",
        ]

        # Добавляем статистику по хостам
        try:
            hosts_data = await api_client.get_hosts()
            hosts = hosts_data.get("response", [])
            total_hosts = len(hosts)
            enabled_hosts = sum(1 for h in hosts if not h.get("isDisabled"))
            disabled_hosts = total_hosts - enabled_hosts
            lines.append(f"  {_('stats.hosts').format(total=total_hosts, enabled=enabled_hosts, disabled=disabled_hosts)}")
        except Exception:
            lines.append(f"  {_('stats.hosts').format(total='—', enabled='—', disabled='—')}")

        # Добавляем статистику по нодам
        try:
            nodes_data = await api_client.get_nodes()
            nodes_list = nodes_data.get("response", [])
            total_nodes = len(nodes_list)
            enabled_nodes = sum(1 for n in nodes_list if not n.get("isDisabled"))
            disabled_nodes = total_nodes - enabled_nodes
            online_nodes = sum(1 for n in nodes_list if n.get("isConnected"))
            lines.append(
                f"  {_('stats.nodes_detailed').format(total=total_nodes, enabled=enabled_nodes, disabled=disabled_nodes, online=online_nodes)}"
            )
        except Exception:
            lines.append(f"  {_('stats.nodes_detailed').format(total='—', enabled='—', disabled='—', online='—')}")

        # Добавляем статистику по ресурсам
        lines.append("")
        lines.append(f"*{_('stats.resources_section')}*")
        try:
            templates_data = await api_client.get_templates()
            templates = templates_data.get("response", {}).get("templates", [])
            lines.append(f"  {_('stats.templates').format(count=len(templates))}")
        except Exception:
            lines.append(f"  {_('stats.templates').format(count='—')}")

        try:
            tokens_data = await api_client.get_tokens()
            tokens = tokens_data.get("response", {}).get("apiKeys", [])
            lines.append(f"  {_('stats.tokens').format(count=len(tokens))}")
        except Exception:
            lines.append(f"  {_('stats.tokens').format(count='—')}")

        try:
            snippets_data = await api_client.get_snippets()
            snippets = snippets_data.get("response", {}).get("snippets", [])
            lines.append(f"  {_('stats.snippets').format(count=len(snippets))}")
        except Exception:
            lines.append(f"  {_('stats.snippets').format(count='—')}")

        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Stats fetch failed")
        return _("errors.generic")


async def _fetch_bandwidth_text() -> str:
    """Получает текст для отображения статистики трафика."""
    try:
        data = await api_client.get_bandwidth_stats()
        return build_bandwidth_stats(data, _)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Bandwidth fetch failed")
        return _("errors.generic")


@router.callback_query(F.data == "menu:health")
async def cb_health(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Здоровье'."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = await _fetch_health_text()
    await _edit_text_safe(callback.message, text, reply_markup=system_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data == "menu:stats")
async def cb_stats(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Статистика'."""
    if await _not_admin(callback):
        return
    await callback.answer()
    text = _("stats.menu_title")
    await _edit_text_safe(callback.message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")


@router.callback_query(F.data.in_(["stats:panel", "stats:server", "stats:traffic"]))
async def cb_stats_type(callback: CallbackQuery) -> None:
    """Обработчик выбора типа статистики."""
    if await _not_admin(callback):
        return
    await callback.answer()
    stats_type = callback.data.split(":")[-1]

    if stats_type == "panel":
        text = await _fetch_panel_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")
    elif stats_type == "server":
        text = await _fetch_server_stats_text()
        await _edit_text_safe(callback.message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")
    elif stats_type == "traffic":
        # Показываем меню выбора периода
        text = _("stats.traffic_select_period")
        await _edit_text_safe(callback.message, text, reply_markup=stats_period_keyboard(), parse_mode="Markdown")
    else:
        await callback.answer(_("errors.generic"), show_alert=True)


@router.callback_query(F.data == "menu:system_nodes")
async def cb_system_nodes(callback: CallbackQuery) -> None:
    """Обработчик кнопки 'Управление нодами'."""
    if await _not_admin(callback):
        return
    await callback.answer()
    await _edit_text_safe(callback.message, _("system_nodes.overview"), reply_markup=system_nodes_keyboard())


@router.callback_query(F.data.startswith("system:nodes:"))
async def cb_system_nodes_actions(callback: CallbackQuery) -> None:
    """Обработчик действий с системными нодами."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    action = parts[-1]

    if action == "list":
        text = await _fetch_nodes_text()
        await _edit_text_safe(callback.message, text, reply_markup=system_nodes_keyboard())
        return

    # Все массовые операции перенесены в bulk.py
    await callback.answer(_("errors.generic"), show_alert=True)


async def _fetch_traffic_stats_text(start: str, end: str) -> str:
    """Получает статистику трафика за период."""
    try:
        data = await api_client.get_nodes_usage_range(start, end, top_nodes_limit=20)
        
        # Логируем структуру ответа для отладки
        logger.info("API response for traffic stats: type=%s, keys=%s", type(data).__name__, list(data.keys()) if isinstance(data, dict) else "N/A")
        if isinstance(data, dict):
            logger.info("API response content: %s", str(data)[:500])  # Первые 500 символов
        
        # API возвращает структуру: {'response': {'series': [...], 'topNodes': [...], ...}}
        # Данные находятся в response['series'] или response['topNodes']
        from datetime import timedelta
        
        nodes_usage = []
        if isinstance(data, dict):
            response = data.get("response", {})
            if isinstance(response, dict):
                # Используем topNodes если есть, иначе series
                nodes_usage = response.get("topNodes", response.get("series", []))
            else:
                nodes_usage = response if isinstance(response, list) else []
        elif isinstance(data, list):
            nodes_usage = data

        # Фильтруем только словари (объекты), игнорируя строки
        nodes_usage = [node for node in nodes_usage if isinstance(node, dict)]

        # Для отображения: если формат только дата (YYYY-MM-DD), показываем как есть
        # Для end показываем текущий день (end - 1 день), так как мы используем следующий день для API
        if len(end) == 10:
            # end это следующий день для API, для отображения показываем текущий день
            from datetime import datetime as dt
            end_date = dt.strptime(end, "%Y-%m-%d")
            end_display = (end_date - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            end_display = format_datetime(end.replace("Z", "+00:00"))
        
        start_display = start if len(start) == 10 else format_datetime(start.replace("Z", "+00:00"))
        
        lines = [
            f"*{_('stats.traffic_title')}*",
            "",
            _("stats.traffic_period").format(
                start=start_display,
                end=end_display,
            ),
        ]

        if not nodes_usage:
            lines.append("")
            lines.append(_("stats.traffic_empty"))
        else:
            # Подсчитываем общий трафик
            # API возвращает данные в формате: {'total': ..., 'data': [...]}
            total_traffic = sum(node.get("total", node.get("totalTrafficBytes", 0)) for node in nodes_usage)
            # Для download/upload используем data если есть, иначе ищем в других полях
            total_download = 0
            total_upload = 0
            for node in nodes_usage:
                # Если есть массив data, суммируем его (обычно это трафик по дням)
                data_array = node.get("data", [])
                if data_array:
                    node_total = sum(data_array)
                    # Предполагаем, что это общий трафик (download + upload)
                    total_download += node_total // 2  # Примерное разделение
                    total_upload += node_total // 2
                else:
                    total_download += node.get("totalDownloadBytes", node.get("download", 0))
                    total_upload += node.get("totalUploadBytes", node.get("upload", 0))

            lines.append("")
            lines.append(f"*{_('stats.traffic_summary')}*")
            lines.append(_("stats.traffic_total").format(total=format_bytes(total_traffic)))
            lines.append(_("stats.traffic_download").format(download=format_bytes(total_download)))
            lines.append(_("stats.traffic_upload").format(upload=format_bytes(total_upload)))

            lines.append("")
            lines.append(f"*{_('stats.traffic_by_node')}*")
            # Сортируем по трафику (по убыванию)
            # API возвращает данные с полем 'total' вместо 'totalTrafficBytes'
            sorted_nodes = sorted(nodes_usage, key=lambda x: x.get("total", x.get("totalTrafficBytes", 0)), reverse=True)
            for node in sorted_nodes[:20]:  # Показываем топ-20
                node_name = node.get("name", node.get("nodeName", "n/a"))
                country = node.get("countryCode", node.get("nodeCountryCode", "—"))
                traffic_bytes = node.get("total", node.get("totalTrafficBytes", 0))
                # Для download/upload используем data если есть
                data_array = node.get("data", [])
                if data_array:
                    node_total = sum(data_array)
                    download_bytes = node_total // 2  # Примерное разделение
                    upload_bytes = node_total // 2
                else:
                    download_bytes = node.get("totalDownloadBytes", node.get("download", 0))
                    upload_bytes = node.get("totalUploadBytes", node.get("upload", 0))
                lines.append(
                    _("stats.traffic_node_item").format(
                        nodeName=node_name,
                        country=country,
                        traffic=format_bytes(traffic_bytes),
                        download=format_bytes(download_bytes),
                        upload=format_bytes(upload_bytes),
                    )
                )

        return "\n".join(lines)
    except UnauthorizedError:
        return _("errors.unauthorized")
    except ApiClientError:
        logger.exception("⚠️ Traffic stats fetch failed")
        return _("errors.generic")


@router.callback_query(F.data.startswith("stats:traffic_period:"))
async def cb_stats_traffic_period(callback: CallbackQuery) -> None:
    """Обработчик выбора периода для статистики трафика."""
    if await _not_admin(callback):
        return
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return

    period = parts[2]

    try:
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        # Убираем микросекунды для совместимости с API
        now = now.replace(microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        # API для /api/bandwidth-stats/nodes ожидает формат только с датой (YYYY-MM-DD)
        # Для end используем завтрашний день, чтобы включить весь последний день периода
        def format_date_only(dt: datetime) -> str:
            return dt.strftime("%Y-%m-%d")

        if period == "today":
            # Для "сегодня" используем сегодня и завтра
            start = format_date_only(today_start)
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "week":
            start = format_date_only(today_start - timedelta(days=7))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "month":
            start = format_date_only(today_start - timedelta(days=30))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "3months":
            start = format_date_only(today_start - timedelta(days=90))
            end = format_date_only(today_start + timedelta(days=1))
        elif period == "year":
            start = format_date_only(today_start - timedelta(days=365))
            end = format_date_only(today_start + timedelta(days=1))
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return

        text = await _fetch_traffic_stats_text(start, end)
        await _edit_text_safe(callback.message, text, reply_markup=stats_menu_keyboard(), parse_mode="Markdown")
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=stats_menu_keyboard())
    except ApiClientError:
        logger.exception("⚠️ Traffic stats period fetch failed period=%s", period)
        await _edit_text_safe(callback.message, _("errors.generic"), reply_markup=stats_menu_keyboard())

