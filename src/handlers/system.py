"""Обработчики системных операций (health, stats, system nodes)."""
from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.i18n import gettext as _

from src.handlers.common import _edit_text_safe, _not_admin
from src.handlers.state import PENDING_INPUT
from src.keyboards.navigation import NavTarget, nav_row
from src.keyboards.stats_menu import stats_menu_keyboard
from src.keyboards.system_menu import system_menu_keyboard
from src.keyboards.system_nodes import system_nodes_keyboard
from src.services.api_client import ApiClientError, UnauthorizedError, api_client
from src.utils.formatters import build_bandwidth_stats, format_bytes, format_uptime
from src.utils.logger import logger

# Временные импорты из других модулей
# TODO: Импортировать _fetch_nodes_text из nodes.py после завершения рефакторинга
from src.handlers.nodes import _fetch_nodes_text

router = Router(name="system")


def _system_nodes_profiles_keyboard(profiles: list[dict]) -> InlineKeyboardMarkup:
    """Клавиатура для выбора профиля конфигурации для системных нод."""
    rows: list[list[InlineKeyboardButton]] = []
    for profile in sorted(profiles, key=lambda p: p.get("viewPosition", 0))[:10]:
        name = profile.get("name", "n/a")
        uuid = profile.get("uuid", "")
        rows.append([InlineKeyboardButton(text=name, callback_data=f"system:nodes:profile:{uuid}")])
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


@router.callback_query(F.data.startswith("stats:"))
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

    if action == "assign_profile":
        try:
            data = await api_client.get_config_profiles()
            profiles = data.get("response", {}).get("configProfiles", [])
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=system_nodes_keyboard())
            return
        except ApiClientError:
            logger.exception("❌ System nodes fetch profiles failed")
            await _edit_text_safe(callback.message, _("system_nodes.error"), reply_markup=system_nodes_keyboard())
            return

        if not profiles:
            await _edit_text_safe(callback.message, _("system_nodes.no_profiles"), reply_markup=system_nodes_keyboard())
            return

        await _edit_text_safe(
            callback.message,
            _("system_nodes.select_profile"),
            reply_markup=_system_nodes_profiles_keyboard(profiles),
        )
        return

    if len(parts) >= 4 and parts[2] == "profile":
        profile_uuid = parts[3]
        try:
            profile = await api_client.get_config_profile_computed(profile_uuid)
            info = profile.get("response", profile)
            inbounds = info.get("inbounds", [])
            inbound_uuids = [i.get("uuid") for i in inbounds if i.get("uuid")]

            nodes_data = await api_client.get_nodes()
            nodes = nodes_data.get("response", [])
            uuids = [n.get("uuid") for n in nodes if n.get("uuid")]

            if not uuids:
                await _edit_text_safe(callback.message, _("system_nodes.no_nodes"), reply_markup=system_nodes_keyboard())
                return

            await api_client.bulk_nodes_profile_modification(uuids, profile_uuid, inbound_uuids)
            await _edit_text_safe(callback.message, _("system_nodes.done_assign"), reply_markup=system_nodes_keyboard())
        except UnauthorizedError:
            await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=system_nodes_keyboard())
        except ApiClientError:
            logger.exception("❌ System nodes assign profile failed profile_uuid=%s", profile_uuid)
            await _edit_text_safe(callback.message, _("system_nodes.error"), reply_markup=system_nodes_keyboard())
        return

    try:
        # Получаем все ноды
        nodes_data = await api_client.get_nodes()
        nodes = nodes_data.get("response", [])
        uuids = [n.get("uuid") for n in nodes if n.get("uuid")]

        if not uuids:
            await _edit_text_safe(callback.message, _("system_nodes.no_nodes"), reply_markup=system_nodes_keyboard())
            return

        # Выполняем операцию для каждой ноды
        success_count = 0
        error_count = 0

        if action == "enable_all":
            for uuid in uuids:
                try:
                    await api_client.enable_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "disable_all":
            for uuid in uuids:
                try:
                    await api_client.disable_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "restart_all":
            for uuid in uuids:
                try:
                    await api_client.restart_node(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        elif action == "reset_traffic_all":
            for uuid in uuids:
                try:
                    await api_client.reset_node_traffic(uuid)
                    success_count += 1
                except ApiClientError:
                    error_count += 1
        else:
            await callback.answer(_("errors.generic"), show_alert=True)
            return

        if error_count > 0:
            result_text = _("system_nodes.done_partial").format(success=success_count, errors=error_count)
        else:
            result_text = _("system_nodes.done").format(count=success_count)

        await _edit_text_safe(callback.message, result_text, reply_markup=system_nodes_keyboard())
    except UnauthorizedError:
        await _edit_text_safe(callback.message, _("errors.unauthorized"), reply_markup=system_nodes_keyboard())
    except ApiClientError:
        logger.exception("❌ System nodes action failed action=%s", action)
        await _edit_text_safe(callback.message, _("system_nodes.error"), reply_markup=system_nodes_keyboard())

