"""
Pydantic-модели для контракта с Collector API.
Формат: POST /api/v2/collector/batch (Web Backend)
"""
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    """Возвращает текущее UTC время без timezone info (для совместимости с API)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConnectionReport(BaseModel):
    """Одно подключение — совпадает с Collector API."""

    user_email: str
    ip_address: str
    node_uuid: str
    connected_at: datetime
    disconnected_at: Optional[datetime] = None
    bytes_sent: int = 0
    bytes_received: int = 0
    # Тег инбаунда, через который зашёл клиент. Панель по нему определяет
    # транспорт подключения: у ноды с несколькими инбаундами иначе не понять,
    # каким именно классом пользовался человек.
    inbound_tag: str = ""


class TorrentEvent(BaseModel):
    """Событие обнаружения торрент-трафика."""

    user_email: str
    ip_address: str
    destination: str       # e.g. "tracker.example.com:6881"
    inbound_tag: str       # e.g. "vless_tls"
    outbound_tag: str      # e.g. "TORRENT"
    node_uuid: str
    detected_at: datetime


class SystemMetrics(BaseModel):
    """Системные метрики ноды (CPU, RAM, диск, uptime)."""

    cpu_percent: float = 0.0
    cpu_cores: int = 0
    memory_percent: float = 0.0
    memory_total_bytes: int = 0
    memory_used_bytes: int = 0
    disk_percent: float = 0.0
    disk_total_bytes: int = 0
    disk_used_bytes: int = 0
    disk_read_speed_bps: int = 0
    disk_write_speed_bps: int = 0
    uptime_seconds: int = 0


class NetworkMetrics(BaseModel):
    """Сетевые метрики хоста: сырой трафик интерфейсов и давление на TCP-стек.

    Панель уже знает трафик из статистики Xray, но там виден только трафик,
    который прошёл через прокси. Атака бьёт по интерфейсу и до Xray не доходит,
    поэтому её видно только здесь.

    Метрики отправляются, только если агент дотянулся до сетевого namespace
    хоста. Иначе поле остаётся пустым: ноль вместо данных читался бы как
    «на ноде тишина».
    """

    rx_bps: int = 0
    tx_bps: int = 0
    rx_pps: int = 0
    tx_pps: int = 0
    # Дропы на интерфейсах: очередь не справляется с потоком
    rx_drop_ps: int = 0
    tx_drop_ps: int = 0
    # Таблица conntrack: забита под завязку — новые соединения не проходят
    conntrack_count: Optional[int] = None
    conntrack_max: Optional[int] = None
    # Давление на TCP: живые соединения, syncookies и отказы accept-очереди
    tcp_established: int = 0
    tcp_syncookies_ps: int = 0
    tcp_listen_drop_ps: int = 0


class BatchReport(BaseModel):
    """Батч от одной ноды — тело POST /api/v2/collector/batch."""

    node_uuid: str
    timestamp: datetime = Field(default_factory=_utcnow)
    connections: list[ConnectionReport] = Field(default_factory=list)
    torrent_events: list[TorrentEvent] = Field(default_factory=list)
    system_metrics: Optional[SystemMetrics] = None
    network_metrics: Optional[NetworkMetrics] = None
    # Версия агента — панель сравнивает с эталоном и подсказывает обновление
    agent_version: Optional[str] = None
