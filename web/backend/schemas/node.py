"""Node schemas for web panel API."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, ConfigDict


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
    # Extended metrics
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    uptime_seconds: Optional[int] = None
    download_speed_bps: int = 0
    upload_speed_bps: int = 0

    class Config:
        from_attributes = True


class NodeDetail(NodeListItem):
    """Detailed node information."""


class NodeCreate(BaseModel):
    """Create node request."""

    name: str
    address: str
    port: int = 443


class NodeUpdate(BaseModel):
    """Update node request."""

    name: Optional[str] = None
    address: Optional[str] = None
    port: Optional[int] = None
    is_disabled: Optional[bool] = None


class NodeStats(BaseModel):
    """Node statistics."""

    uuid: str
    name: str
    connections_count: int = 0
    traffic_today_bytes: int = 0
    traffic_week_bytes: int = 0
    avg_latency_ms: Optional[float] = None
