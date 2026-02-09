"""
Pydantic-модели для контракта с Collector API.
Формат должен совпадать с Admin Bot: POST /api/v1/connections/batch
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ConnectionReport(BaseModel):
    """Одно подключение — совпадает с Collector API."""

    user_email: str
    ip_address: str
    node_uuid: str
    connected_at: datetime
    disconnected_at: Optional[datetime] = None
    bytes_sent: int = 0
    bytes_received: int = 0


class SystemMetrics(BaseModel):
    """Системные метрики ноды (CPU, RAM, диск, uptime)."""

    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    memory_total_bytes: int = 0
    memory_used_bytes: int = 0
    disk_percent: float = 0.0
    disk_total_bytes: int = 0
    disk_used_bytes: int = 0
    uptime_seconds: int = 0


class BatchReport(BaseModel):
    """Батч от одной ноды — тело POST /api/v1/connections/batch."""

    node_uuid: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    connections: list[ConnectionReport] = Field(default_factory=list)
    system_metrics: Optional[SystemMetrics] = None
