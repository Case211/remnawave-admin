"""
Remnawave Node Agent — entry point.

Цикл: собрать подключения из Xray (access.log) → отправить в Collector API → sleep(interval).
"""
import asyncio
import logging
import signal
import sys
import time
from pathlib import Path

from .config import Settings
from .collectors import XrayLogCollector, XrayLogRealtimeCollector, SystemMetricsCollector
from .models import ConnectionReport
from .sender import CollectorSender

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


async def run_agent() -> None:
    settings = Settings()
    # Устанавливаем уровень логирования
    log_level = settings.log_level.upper()
    if log_level in ("DEBUG", "INFO", "WARNING", "ERROR"):
        logging.getLogger().setLevel(getattr(logging, log_level))
        logger.info("Log level set to: %s", log_level)
    else:
        logger.warning("Invalid log level '%s', using INFO", log_level)
        logging.getLogger().setLevel(logging.INFO)

    # Выбираем коллектор в зависимости от режима парсинга
    if settings.log_parsing_mode.lower() == "realtime":
        collector = XrayLogRealtimeCollector(settings)
        logger.info("Using real-time log collector (tracks file position)")
    else:
        collector = XrayLogCollector(settings)
        logger.info("Using polling log collector (reads tail every interval)")

    sender = CollectorSender(settings)
    system_metrics_collector = SystemMetricsCollector()

    # Первый вызов CPU — инициализация baseline (первое значение всегда 0)
    await system_metrics_collector.collect()
    logger.info("System metrics collector initialized")

    # Проверяем связь с Collector API при старте
    connectivity_ok = await sender.check_connectivity()
    if not connectivity_ok:
        logger.warning(
            "Could not reach Collector API at %s — agent will keep trying to send batches",
            settings.collector_url,
        )

    # Проверяем доступность файла логов при старте
    log_path = Path(settings.xray_log_path)
    if log_path.exists():
        stat = log_path.stat()
        logger.info(
            "Log file found: %s (size: %d bytes)",
            settings.xray_log_path,
            stat.st_size
        )
    else:
        logger.warning(
            "Log file not found: %s - agent will wait for file to appear",
            settings.xray_log_path
        )

    logger.info(
        "Node Agent started: node_uuid=%s, collector=%s, mode=%s, interval=%ss",
        settings.node_uuid,
        settings.collector_url,
        settings.log_parsing_mode,
        settings.interval_seconds,
    )

    cycle_count = 0
    # В real-time режиме можем проверять новые строки чаще, чем отправлять батчи
    check_interval = settings.realtime_check_interval_seconds or settings.interval_seconds
    send_interval = settings.interval_seconds

    # Накопленные подключения для батч-отправки
    accumulated_connections: list[ConnectionReport] = []
    last_send_time = asyncio.get_event_loop().time()
    
    while True:
        cycle_count += 1
        try:
            logger.debug("Cycle #%d: collecting connections...", cycle_count)
            connections = await collector.collect()
            
            if connections:
                # В real-time режиме накапливаем подключения для батч-отправки
                if settings.log_parsing_mode.lower() == "realtime":
                    accumulated_connections.extend(connections)
                    logger.debug("Cycle #%d: collected %d connections (accumulated: %d)",
                               cycle_count, len(connections), len(accumulated_connections))

                    # Проверяем, пора ли отправлять батч
                    current_time = asyncio.get_event_loop().time()
                    if accumulated_connections and (current_time - last_send_time >= send_interval):
                        # Собираем метрики перед отправкой
                        metrics = await system_metrics_collector.collect()
                        logger.info("Cycle #%d: sending accumulated batch (%d connections)...",
                                  cycle_count, len(accumulated_connections))
                        ok = await sender.send_batch(accumulated_connections, system_metrics=metrics)
    last_send_time = time.monotonic()

    # Graceful shutdown через asyncio.Event
    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _signal_handler() -> None:
        logger.info("Received shutdown signal, finishing current cycle...")
        shutdown_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _signal_handler)

    try:
        while not shutdown_event.is_set():
            cycle_count += 1
            try:
                logger.debug("Cycle #%d: collecting connections...", cycle_count)
                connections = await collector.collect()

                if connections:
                    # В real-time режиме накапливаем подключения для батч-отправки
                    if settings.log_parsing_mode.lower() == "realtime":
                        accumulated_connections.extend(connections)
                        logger.debug("Cycle #%d: collected %d connections (accumulated: %d)",
                                     cycle_count, len(connections), len(accumulated_connections))

                        # Ограничиваем буфер, чтобы избежать утечки памяти
                        if len(accumulated_connections) > settings.max_buffer_size:
                            dropped = len(accumulated_connections) - settings.max_buffer_size
                            accumulated_connections = accumulated_connections[-settings.max_buffer_size:]
                            logger.warning(
                                "Buffer overflow: dropped %d oldest connections (max_buffer_size=%d)",
                                dropped, settings.max_buffer_size,
                            )

                        # Проверяем, пора ли отправлять батч
                        current_time = time.monotonic()
                        if accumulated_connections and (current_time - last_send_time >= send_interval):
                            logger.info("Cycle #%d: sending accumulated batch (%d connections)...",
                                        cycle_count, len(accumulated_connections))
                            ok = await sender.send_batch(accumulated_connections)
                            if ok:
                                logger.info("Cycle #%d: batch sent successfully", cycle_count)
                                accumulated_connections.clear()
                                last_send_time = current_time
                            else:
                                logger.warning("Cycle #%d: send failed, will retry next cycle", cycle_count)
                    else:
                        # В polling режиме отправляем сразу
                        logger.info("Cycle #%d: collected %d connections, sending batch...", cycle_count, len(connections))
                        ok = await sender.send_batch(connections)
                        if ok:
                            logger.info("Cycle #%d: batch sent successfully", cycle_count)
                        else:
                            logger.warning("Cycle #%d: send failed, will retry next cycle", cycle_count)
                else:
                    # В polling режиме отправляем сразу
                    metrics = await system_metrics_collector.collect()
                    logger.info("Cycle #%d: collected %d connections, sending batch...", cycle_count, len(connections))
                    ok = await sender.send_batch(connections, system_metrics=metrics)
                    if ok:
                        logger.info("Cycle #%d: batch sent successfully", cycle_count)
                    # Показываем INFO каждые 10 циклов, чтобы видеть что агент работает
                    if cycle_count % 10 == 0:
                        logger.info("Cycle #%d: no connections found in log (agent is running)", cycle_count)
                    else:
                        logger.debug("Cycle #%d: no connections found in log", cycle_count)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.exception("Cycle #%d error: %s", cycle_count, e)

            # Используем wait с таймаутом вместо sleep, чтобы реагировать на shutdown
            try:
                await asyncio.wait_for(shutdown_event.wait(), timeout=check_interval)
            except asyncio.TimeoutError:
                pass

        # Graceful shutdown: отправляем оставшиеся данные
        if accumulated_connections:
            logger.info("Shutdown: sending remaining %d accumulated connections...", len(accumulated_connections))
            ok = await sender.send_batch(accumulated_connections)
            if ok:
                logger.info("Shutdown: remaining batch sent successfully")
            else:
                # Даже без подключений отправляем метрики периодически
                current_time = asyncio.get_event_loop().time()
                if current_time - last_send_time >= send_interval:
                    metrics = await system_metrics_collector.collect()
                    logger.debug("Cycle #%d: no connections, sending metrics only...", cycle_count)
                    ok = await sender.send_batch([], system_metrics=metrics)
                    if ok:
                        last_send_time = current_time

                # Показываем INFO каждые 10 циклов, чтобы видеть что агент работает
                if cycle_count % 10 == 0:
                    logger.info("Cycle #%d: no connections found in log (agent is running)", cycle_count)
                else:
                    logger.debug("Cycle #%d: no connections found in log", cycle_count)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Cycle #%d error: %s", cycle_count, e)
                logger.warning("Shutdown: failed to send remaining %d connections", len(accumulated_connections))

    finally:
        await sender.close()
        logger.info("Node Agent stopped")


def main() -> None:
    try:
        asyncio.run(run_agent())
    except KeyboardInterrupt:
        logger.info("Stopped by user")


if __name__ == "__main__":
    main()
