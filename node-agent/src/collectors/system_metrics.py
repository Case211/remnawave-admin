"""
Коллектор системных метрик ноды: CPU, RAM, диск, uptime.

Читает данные из /proc (Linux) без внешних зависимостей.
"""
import logging
import os
from pathlib import Path

from ..models import SystemMetrics

logger = logging.getLogger(__name__)


class SystemMetricsCollector:
    """Собирает системные метрики из /proc и os.statvfs."""

    def __init__(self):
        self._prev_cpu_times: tuple[int, int] | None = None  # (idle, total)

    async def collect(self) -> SystemMetrics:
        """Собрать текущие метрики системы."""
        metrics = SystemMetrics()

        try:
            metrics.cpu_percent = self._read_cpu()
        except Exception as e:
            logger.debug("Failed to read CPU: %s", e)

        try:
            mem = self._read_memory()
            metrics.memory_total_bytes = mem[0]
            metrics.memory_used_bytes = mem[1]
            if mem[0] > 0:
                metrics.memory_percent = round(mem[1] / mem[0] * 100, 1)
        except Exception as e:
            logger.debug("Failed to read memory: %s", e)

        try:
            disk = self._read_disk()
            metrics.disk_total_bytes = disk[0]
            metrics.disk_used_bytes = disk[1]
            if disk[0] > 0:
                metrics.disk_percent = round(disk[1] / disk[0] * 100, 1)
        except Exception as e:
            logger.debug("Failed to read disk: %s", e)

        try:
            metrics.uptime_seconds = self._read_uptime()
        except Exception as e:
            logger.debug("Failed to read uptime: %s", e)

        return metrics

    def _read_cpu(self) -> float:
        """Прочитать загрузку CPU из /proc/stat (дельта между вызовами)."""
        stat_path = Path("/proc/stat")
        if not stat_path.exists():
            return 0.0

        line = stat_path.read_text().split("\n")[0]  # "cpu  user nice system idle ..."
        parts = line.split()
        if len(parts) < 5:
            return 0.0

        values = [int(v) for v in parts[1:]]
        idle = values[3]
        total = sum(values)

        if self._prev_cpu_times is None:
            self._prev_cpu_times = (idle, total)
            return 0.0

        prev_idle, prev_total = self._prev_cpu_times
        self._prev_cpu_times = (idle, total)

        diff_idle = idle - prev_idle
        diff_total = total - prev_total

        if diff_total == 0:
            return 0.0

        usage = (1.0 - diff_idle / diff_total) * 100.0
        return round(max(0.0, min(100.0, usage)), 1)

    def _read_memory(self) -> tuple[int, int]:
        """Прочитать RAM из /proc/meminfo. Возвращает (total, used) в байтах."""
        meminfo_path = Path("/proc/meminfo")
        if not meminfo_path.exists():
            return (0, 0)

        data: dict[str, int] = {}
        for line in meminfo_path.read_text().split("\n"):
            if ":" not in line:
                continue
            key, val = line.split(":", 1)
            parts = val.strip().split()
            if parts:
                try:
                    kb = int(parts[0])
                    data[key.strip()] = kb * 1024  # kB -> bytes
                except ValueError:
                    pass

        total = data.get("MemTotal", 0)
        available = data.get("MemAvailable", 0)
        used = total - available if available else total
        return (total, used)

    def _read_disk(self) -> tuple[int, int]:
        """Прочитать использование диска через os.statvfs('/').
        Возвращает (total, used) в байтах."""
        st = os.statvfs("/")
        total = st.f_blocks * st.f_frsize
        free = st.f_bfree * st.f_frsize
        used = total - free
        return (total, used)

    def _read_uptime(self) -> int:
        """Прочитать uptime из /proc/uptime."""
        uptime_path = Path("/proc/uptime")
        if not uptime_path.exists():
            return 0

        text = uptime_path.read_text().strip()
        return int(float(text.split()[0]))
