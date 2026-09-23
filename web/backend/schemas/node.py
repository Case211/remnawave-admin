"""Node schemas for web panel API."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, model_validator


class NodeBase(BaseModel):
    """Base node fields."""
    model_config = ConfigDict(extra='ignore')

    name: str = ''
    address: str = ''
    port: int = 443


class NodeListItem(NodeBase):
    """Node item in list."""

    uuid: str
    is_disabled: bool = False
    is_connected: bool = False
    is_xray_running: bool = False
    xray_version: Optional[str] = None
    message: Optional[str] = None
    traffic_limit_bytes: Optional[int] = None
    traffic_used_bytes: int = 0
    traffic_total_bytes: int = 0
    traffic_today_bytes: int = 0
    users_online: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None
    # Когда нода последний раз сменила статус в панели: «в сети с» / «офлайн с».
    # Поля «последний раз была» панель не присылает — last_seen_at всегда пуст.
    last_status_change: Optional[datetime] = None
    # Порядок в панели и профиль — для правки ноды и сортировки «как в панели»
    view_position: Optional[int] = None
    config_profile_uuid: Optional[str] = None
    active_inbound_uuids: List[str] = []
    node_version: Optional[str] = None
    country_code: Optional[str] = None
    # Счётчик трафика ноды (traffic_total_bytes) обнуляется в этот день месяца
    traffic_reset_day: Optional[int] = None
    is_traffic_tracking_active: bool = False
    memory_total_bytes: Optional[int] = None
    # Extended metrics
    cpu_usage: Optional[float] = None
    cpu_cores: Optional[int] = None
    memory_usage: Optional[float] = None
    uptime_seconds: Optional[int] = None
    download_speed_bps: int = 0
    upload_speed_bps: int = 0
    disk_read_speed_bps: int = 0
    disk_write_speed_bps: int = 0
    # Node-agent state (independent of Panel's is_connected)
    has_agent_token: bool = False
    agent_v2_connected: bool = False
    agent_v2_last_ping: Optional[datetime] = None
    agent_version: Optional[str] = None
    # Шейпер ноды для бейджа: active | rough | error | waiting; None — выключен
    shaper_state: Optional[str] = None
    # 2.8.0: заметка, SOCKS5-прокси, отдельный множитель потребления ноды
    note: Optional[str] = None
    proxy_url: Optional[str] = None
    node_consumption_multiplier: Optional[float] = None
    # Access-policy scope for the current admin:
    # None = no restriction, list = allowed actions (e.g. ["view","edit"])
    allowed_actions: Optional[List[str]] = None

    class Config:
        from_attributes = True


class NodeDetail(NodeListItem):
    """Detailed node information."""


class NodeCreate(BaseModel):
    """Create node request."""

    name: str
    address: str
    port: int = 443
    config_profile_uuid: str
    active_inbounds: List[str]
    note: Optional[str] = None
    proxy_url: Optional[str] = None
    node_consumption_multiplier: Optional[float] = None


class NodeUpdate(BaseModel):
    """Update node request."""

    name: Optional[str] = None
    address: Optional[str] = None
    port: Optional[int] = Field(None, ge=1, le=65535)
    note: Optional[str] = None
    proxy_url: Optional[str] = None
    node_consumption_multiplier: Optional[float] = Field(None, ge=0)
    # Профиль и inbound'ы меняются только вместе: панель принимает их парой
    config_profile_uuid: Optional[str] = None
    active_inbounds: Optional[List[str]] = None

    @model_validator(mode="after")
    def _profile_with_inbounds(self):
        if (self.config_profile_uuid is None) != (self.active_inbounds is None):
            raise ValueError("config_profile_uuid and active_inbounds go together")
        if self.active_inbounds is not None and not self.active_inbounds:
            raise ValueError("at least one inbound is required")
        return self


class NodeReorder(BaseModel):
    """Порядок нод в панели (он же порядок в подписке): uuid по порядку."""

    uuids: List[str] = Field(..., min_length=1, max_length=500)


class NodeStats(BaseModel):
    """Node statistics."""

    uuid: str
    name: str
    connections_count: int = 0
    traffic_today_bytes: int = 0
    traffic_week_bytes: int = 0
    avg_latency_ms: Optional[float] = None
