"""
Remnawave Node Agent — entry point.

Цикл: собрать подключения из Xray (access.log) → отправить в Collector API → sleep(interval).
"""
import asyncio
import logging
import signal
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import Settings
from .collectors import (
    NdpiDaemon,
    NdpiTorrentWatcher,
    NetworkMetricsCollector,
    SystemMetricsCollector,
    XrayLogCollector,
    XrayLogRealtimeCollector,
)
from .models import ConnectionReport, NetworkMetrics, SystemMetrics, TorrentEvent
from .sender import CollectorSender

# ── Logging setup ─────────────────────────────────────────────────

_FILE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s"
_FILE_DATEFMT = "%Y-%m-%d %H:%M:%S"
_CONSOLE_FMT = "%(asctime)s | %(levelname)-7s | %(name)-10s | %(message)s"
_CONSOLE_DATEFMT = "%H:%M:%S"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 3
_LOG_DIR = Path("/app/logs")

# Подавляем шумные сторонние логгеры
_SUPPRESSED_LOGGERS = (
    "httpx", "httpcore", "asyncio", "hpack", "h2",
)


def _setup_logging() -> logging.Logger:
    """Configure logging with console + optional file handlers."""
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(fmt=_CONSOLE_FMT, datefmt=_CONSOLE_DATEFMT))
    root.addHandler(console)

    # Подавляем шумные логгеры
    for name in _SUPPRESSED_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # File handlers (optional — volume may not be mounted)
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_fmt = logging.Formatter(fmt=_FILE_FMT, datefmt=_FILE_DATEFMT)

        info_h = RotatingFileHandler(
            str(_LOG_DIR / "nodeagent_INFO.log"),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        info_h.setLevel(logging.INFO)
        info_h.setFormatter(file_fmt)
        root.addHandler(info_h)

        warn_h = RotatingFileHandler(
            str(_LOG_DIR / "nodeagent_WARNING.log"),
            maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8",
        )
        warn_h.setLevel(logging.WARNING)
        warn_h.setFormatter(file_fmt)
        root.addHandler(warn_h)
    except OSError:
        pass  # no file logging — ok

    return logging.getLogger(__name__)


logger = _setup_logging()


async def run_agent() -> None:
    settings = Settings()

    # Уровень логирования: двигаем и root, и ХЕНДЛЕРЫ. Раньше root опускался
    # до DEBUG, но console/file-хендлеры были зажаты на INFO — из-за этого
    # AGENT_LOG_LEVEL=DEBUG не показывал ни одной debug-строки.
    log_level = settings.log_level.upper()
    effective = getattr(logging, log_level, logging.INFO) \
        if log_level in ("DEBUG", "INFO", "WARNING", "ERROR") else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(effective)
    for handler in root_logger.handlers:
        # WARNING-файл оставляем как есть (он и задуман для warning+)
        if handler.level < logging.WARNING or effective < handler.level:
            if not (isinstance(handler, RotatingFileHandler)
                    and handler.baseFilename.endswith("nodeagent_WARNING.log")):
                handler.setLevel(effective)

    # Auto-restart
    max_uptime_sec = settings.max_uptime_hours * 3600 if settings.max_uptime_hours > 0 else 0
    start_time = time.monotonic()

    # ── Сводка запуска: версия и вся конфигурация одной рамкой ─────
    from .version import AGENT_VERSION
    logger.info("─" * 60)
    logger.info("Remnawave Node Agent v%s", AGENT_VERSION)
    logger.info("  node=%s", settings.node_uuid)
    logger.info("  collector=%s · interval=%ss · mode=%s",
                settings.collector_url, settings.interval_seconds,
                settings.log_parsing_mode)
    logger.info("  host_mode=%s · commands=%s · log_level=%s%s",
                settings.host_mode, settings.command_enabled,
                log_level,
                f" · auto-restart={settings.max_uptime_hours:.1f}h" if max_uptime_sec > 0 else "")
    logger.info("─" * 60)

    # Коллектор
    if settings.log_parsing_mode.lower() == "realtime":
        collector = XrayLogRealtimeCollector(settings)
    else:
        collector = XrayLogCollector(settings)

    sender = CollectorSender(settings)
    system_metrics_collector = SystemMetricsCollector()
    network_metrics_collector = NetworkMetricsCollector()

    async def collect_metrics() -> tuple[SystemMetrics, NetworkMetrics | None]:
        """Системные и сетевые метрики одним снимком."""
        return (
            await system_metrics_collector.collect(),
            await network_metrics_collector.collect(),
        )

    # Инициализация baseline: скорости считаются по дельте с прошлого замера
    await collect_metrics()

    # Проверяем связь
    if not await sender.check_connectivity():
        logger.warning("Cannot reach Collector API at %s", settings.collector_url)

    # Проверяем файл логов
    log_path = Path(settings.xray_log_path)
    if log_path.exists():
        logger.info("Log file: %s (%d bytes)", settings.xray_log_path, log_path.stat().st_size)
    else:
        logger.warning("Log file not found: %s", settings.xray_log_path)

    cycle_count = 0
    check_interval = settings.realtime_check_interval_seconds or settings.interval_seconds
    send_interval = settings.interval_seconds

    accumulated_connections: list[ConnectionReport] = []
    accumulated_torrent_events: list[TorrentEvent] = []
    last_send_time = time.monotonic()
    total_sent = 0  # общий счётчик отправленных подключений
    # Отступ сверх интервала, пока коллектор не принимает. Растёт вдвое с
    # каждой неудачей: без него неотправленный батч уходил на повтор тем же
    # витком цикла, и агент бил по лежащему коллектору без пауз.
    send_backoff = 0.0

    # ── nDPI: второй источник правды про торренты ──
    # Тег роутинга Xray ловит только открытое рукопожатие BitTorrent;
    # шифрованный поток, DHT и uTP видит nDPI. Демон ставится на ноду
    # отдельно, поэтому включается флагом и молча простаивает, если сокета
    # нет: связь с ним не должна мешать основному делу агента.
    ndpi_watcher = None
    ndpi_daemon = None
    if settings.ndpi_enabled and settings.torrent_detection_enabled:
        ndpi_watcher = NdpiTorrentWatcher(
            settings.ndpi_socket_path, window_seconds=settings.ndpi_window_seconds,
        )
        await ndpi_watcher.start()
        collector.torrent_oracle = ndpi_watcher
        logger.info("nDPI torrent detection enabled (socket: %s)", settings.ndpi_socket_path)

    async def control_ndpi(enabled: bool, socket_path=None, window_seconds=None) -> dict:
        """Включить/выключить чтение вердиктов nDPI по команде из панели.

        Возвращает состояние, по которому панель отличит «включено и
        работает» от «включено, но демона на ноде нет».
        """
        nonlocal ndpi_watcher, ndpi_daemon
        if not enabled:
            if ndpi_watcher is not None:
                await ndpi_watcher.stop()
                collector.torrent_oracle = None
                ndpi_watcher = None
            if ndpi_daemon is not None:
                await ndpi_daemon.stop()
                ndpi_daemon = None
            logger.info("nDPI torrent detection disabled by panel")
            return {"enabled": False, "connected": False}

        path = socket_path or settings.ndpi_socket_path
        window = int(window_seconds or settings.ndpi_window_seconds)

        # Демон едет в образе агента, поэтому «установка» — это запуск.
        # Если оператор поднял nDPId сам, снаружи, мы это увидим по живому
        # сокету и второй раз плодить процессы не станем.
        daemon_state = {}
        from .collectors.ndpi_daemon import socket_alive

        if settings.ndpi_manage_daemon and not await socket_alive(path):
            if ndpi_daemon is None:
                ndpi_daemon = NdpiDaemon(path, interface=settings.ndpi_interface or None)
            daemon_state = await ndpi_daemon.start()
            if not daemon_state.get("started"):
                logger.warning("nDPI: демон не поднялся — %s", daemon_state.get("reason"))

        if ndpi_watcher is not None:
            await ndpi_watcher.stop()
        ndpi_watcher = NdpiTorrentWatcher(path, window_seconds=window)
        await ndpi_watcher.start()
        collector.torrent_oracle = ndpi_watcher
        # Даём подключению мгновение: панели полезнее сразу увидеть, что
        # сокета нет, чем узнать об этом из отсутствия событий.
        await asyncio.sleep(0.5)
        state = {"enabled": True, "socket_path": path, "window_seconds": window}
        state.update(ndpi_watcher.stats())
        if daemon_state:
            state["daemon"] = daemon_state
        logger.info("nDPI torrent detection enabled by panel: %s", state)
        return state

    # ── Agent v2: WebSocket command channel ──
    ws_task = None
    if settings.command_enabled and (settings.ws_url or settings.collector_url):
        from .ws_client import AgentWSClient
        from .command_runner import CommandRunner

        ws_client = AgentWSClient(settings)
        cmd_runner = CommandRunner(settings, ws_client.send, ndpi_control=control_ndpi)
        ws_client._command_handler = cmd_runner.handle
        logger.info("Agent v2 command channel enabled")
    else:
        ws_client = None
        logger.info("Agent v2 command channel disabled (AGENT_COMMAND_ENABLED=false)")

    # Graceful shutdown
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler(sig_name: str) -> None:
        logger.info("Shutdown signal received: %s", sig_name)
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler, sig.name)

    # Start WS client as a concurrent task
    if ws_client:
        ws_task = asyncio.create_task(ws_client.run(shutdown_event))

    try:
        while not shutdown_event.is_set():
            cycle_count += 1

            # ── Auto-restart по uptime ──
            if max_uptime_sec > 0:
                uptime = time.monotonic() - start_time
                if uptime >= max_uptime_sec:
                    logger.info(
                        "Max uptime reached (%.1fh), restarting... (sent %d connections total)",
                        uptime / 3600, total_sent,
                    )
                    break

            try:
                connections = await collector.collect()
                torrent_events = collector.last_torrent_events if hasattr(collector, 'last_torrent_events') else []

                if connections or torrent_events:
                    if settings.log_parsing_mode.lower() == "realtime":
                        accumulated_connections.extend(connections)
                        accumulated_torrent_events.extend(torrent_events)

                        # Защита от утечки памяти
                        if len(accumulated_connections) > settings.max_buffer_size:
                            dropped = len(accumulated_connections) - settings.max_buffer_size
                            accumulated_connections = accumulated_connections[-settings.max_buffer_size:]
                            logger.warning("Buffer overflow: dropped %d connections", dropped)
                        if len(accumulated_torrent_events) > settings.max_buffer_size:
                            accumulated_torrent_events = accumulated_torrent_events[-settings.max_buffer_size:]

                        # Отправка по таймеру
                        current_time = time.monotonic()
                        if (accumulated_connections or accumulated_torrent_events) and (current_time - last_send_time >= send_interval + send_backoff):
                            metrics, net_metrics = await collect_metrics()
                            sent_conns, sent_events = await sender.send_in_chunks(
                                accumulated_connections,
                                torrent_events=accumulated_torrent_events if accumulated_torrent_events else None,
                                system_metrics=metrics,
                                network_metrics=net_metrics,
                            )
                            # Время попытки отмечаем всегда, удачной она была
                            # или нет: иначе условие выше остаётся истинным и
                            # следующий виток повторяет отправку немедленно.
                            last_send_time = current_time
                            if sent_conns:
                                total_sent += sent_conns
                                del accumulated_connections[:sent_conns]
                            if sent_events:
                                del accumulated_torrent_events[:sent_events]

                            if accumulated_connections or accumulated_torrent_events:
                                send_backoff = min(
                                    max(send_backoff * 2, send_interval),
                                    settings.send_backoff_max_seconds,
                                )
                                logger.warning(
                                    "Batch partially sent: %d connections left, next try in %.0fs",
                                    len(accumulated_connections), send_interval + send_backoff,
                                )
                            else:
                                send_backoff = 0.0
                                logger.debug("Batch sent: %d connections", sent_conns)
                    else:
                        # polling — отправляем сразу
                        metrics, net_metrics = await collect_metrics()
                        count = len(connections)
                        ok = await sender.send_batch(
                            connections,
                            torrent_events=torrent_events if torrent_events else None,
                            system_metrics=metrics,
                            network_metrics=net_metrics,
                        )
                        if ok:
                            total_sent += count
                            logger.debug("Batch sent: %d connections", count)
                else:
                    # Метрики без подключений
                    current_time = time.monotonic()
                    if current_time - last_send_time >= send_interval + send_backoff:
                        metrics, net_metrics = await collect_metrics()
                        ok = await sender.send_batch(
                            [], system_metrics=metrics, network_metrics=net_metrics
                        )
                        last_send_time = current_time
                        send_backoff = 0.0 if ok else min(
                            max(send_backoff * 2, send_interval),
                            settings.send_backoff_max_seconds,
                        )

                # Heartbeat — каждые 100 циклов (примерно раз в 50 мин при интервале 30с)
                if cycle_count % 100 == 0:
                    uptime = time.monotonic() - start_time
                    logger.info(
                        "Heartbeat: cycle #%d, uptime %.1fh, total sent %d",
                        cycle_count, uptime / 3600, total_sent,
                    )

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Cycle #%d error: %s", cycle_count, e)

            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=check_interval)
            except asyncio.TimeoutError:
                pass

        # Graceful shutdown: отправляем остаток
        if accumulated_connections or accumulated_torrent_events:
            logger.info(
                "Shutdown: sending remaining %d connections, %d torrent events...",
                len(accumulated_connections), len(accumulated_torrent_events),
            )
            sent_conns, _ = await sender.send_in_chunks(
                accumulated_connections,
                torrent_events=accumulated_torrent_events if accumulated_torrent_events else None,
            )
            total_sent += sent_conns

    finally:
        # Stop WS client
        if ws_client:
            ws_client.stop()
        if ws_task and not ws_task.done():
            ws_task.cancel()
            try:
                await ws_task
            except asyncio.CancelledError:
                pass

        if ndpi_watcher is not None:
            await ndpi_watcher.stop()
        if ndpi_daemon is not None:
            await ndpi_daemon.stop()

        await sender.close()
        uptime = time.monotonic() - start_time
        logger.info("Node Agent stopped (uptime %.1fh, total sent %d)", uptime / 3600, total_sent)


def main() -> None:
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
