"""
ConnectionMonitor — re-export из shared/ для обратной совместимости.

Реальная реализация находится в shared/connection_monitor.py.
"""
from shared.connection_monitor import (  # noqa: F401
    ConnectionMonitor,
    ConnectionStats,
    ActiveConnection,
)
