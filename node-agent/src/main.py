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
from .collectors import XrayLogCollector, XrayLogRealtimeCollector, SystemMetricsCollector
from .models import ConnectionReport
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

    # Уровень логирования
    log_level = settings.log_level.upper()
    if log_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        logging.getLogger().setLevel(getattr(logging, log_level))
    else:
        logging.getLogger().setLevel(logging.INFO)

    # Коллектор
    if settings.log_parsing_mode.lower() == "realtime":
        collector = XrayLogRealtimeCollector(settings)
        logger.info("Mode: realtime, interval: %ss", settings.interval_seconds)
    else:
        collector = XrayLogCollector(settings)
        logger.info("Mode: polling, interval: %ss", settings.interval_seconds)

    sender = CollectorSender(settings)
    system_metrics_collector = SystemMetricsCollector()

    # Инициализация CPU baseline
    await system_metrics_collector.collect()

    # Проверяем связь
    if not await sender.check_connectivity():
        logger.warning("Cannot reach Collector API at %s", settings.collector_url)

    # Проверяем файл логов
    log_path = Path(settings.xray_log_path)
    if log_path.exists():
        logger.info("Log file: %s (%d bytes)", settings.xray_log_path, log_path.stat().st_size)
    else:
        logger.warning("Log file not found: %s", settings.xray_log_path)

    # Auto-restart
    max_uptime_sec = settings.max_uptime_hours * 3600 if settings.max_uptime_hours > 0 else 0
    start_time = time.monotonic()
    if max_uptime_sec > 0:
        logger.info(
            "Node Agent started (node=%s, auto-restart in %.1fh)",
            settings.node_uuid, settings.max_uptime_hours,
        )
    else:
        logger.info("Node Agent started (node=%s)", settings.node_uuid)

    cycle_count = 0
    check_interval = settings.realtime_check_interval_seconds or settings.interval_seconds
    send_interval = settings.interval_seconds

    accumulated_connections: list[ConnectionReport] = []
    last_send_time = time.monotonic()
    total_sent = 0  # общий счётчик отправленных подключений

    # ── Agent v2: WebSocket command channel ──
    ws_task = None
    if settings.command_enabled and (settings.ws_url or settings.collector_url):
        from .ws_client import AgentWSClient
        from .command_runner import CommandRunner

        ws_client = AgentWSClient(settings)
        cmd_runner = CommandRunner(settings, ws_client.send)
        ws_client._command_handler = cmd_runner.handle
        logger.info("Agent v2 command channel enabled")
    else:
        ws_client = None
        logger.info("Agent v2 command channel disabled (AGENT_COMMAND_ENABLED=false)")

    # Graceful shutdown
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

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

                if connections:
                    if settings.log_parsing_mode.lower() == "realtime":
                        accumulated_connections.extend(connections)

                        # Защита от утечки памяти
                        if len(accumulated_connections) > settings.max_buffer_size:
                            dropped = len(accumulated_connections) - settings.max_buffer_size
                            accumulated_connections = accumulated_connections[-settings.max_buffer_size:]
                            logger.warning("Buffer overflow: dropped %d connections", dropped)

                        # Отправка по таймеру
                        current_time = time.monotonic()
                        if accumulated_connections and (current_time - last_send_time >= send_interval):
                            metrics = await system_metrics_collector.collect()
                            count = len(accumulated_connections)
                            ok = await sender.send_batch(accumulated_connections, system_metrics=metrics)
                            if ok:
                                total_sent += count
                                accumulated_connections.clear()
                                last_send_time = current_time
                                logger.debug("Batch sent: %d connections", count)
                    else:
                        # polling — отправляем сразу
                        metrics = await system_metrics_collector.collect()
                        count = len(connections)
                        ok = await sender.send_batch(connections, system_metrics=metrics)
                        if ok:
                            total_sent += count
                            logger.debug("Batch sent: %d connections", count)
                else:
                    # Метрики без подключений
                    current_time = time.monotonic()
                    if current_time - last_send_time >= send_interval:
                        metrics = await system_metrics_collector.collect()
                        ok = await sender.send_batch([], system_metrics=metrics)
                        if ok:
                            last_send_time = current_time

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
        if accumulated_connections:
            logger.info("Shutdown: sending remaining %d connections...", len(accumulated_connections))
            ok = await sender.send_batch(accumulated_connections)
            if ok:
                total_sent += len(accumulated_connections)

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
