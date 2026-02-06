"""Node schemas for web panel API."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel


class NodeBase(BaseModel):
    """Base node fields."""

    name: str
    address: str
    port: int = 443


class NodeListItem(NodeBase):
    """Node item in list."""

    uuid: str
    is_disabled: bool = False
    is_connected: bool = False
    traffic_limit_bytes: Optional[int] = None
    traffic_used_bytes: int = 0
    users_online: int = 0
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NodeDetail(NodeListItem):
    """Detailed node information."""

    # Extended stats
    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    uptime_seconds: Optional[int] = None
    last_seen_at: Optional[datetime] = None


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
