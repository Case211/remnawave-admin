"""Pydantic schemas for notifications and alerts."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ── Notifications ────────────────────────────────────────────────

class NotificationBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: str = "info"
    severity: str = "info"
    title: str
    body: Optional[str] = None
    link: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None


class NotificationCreate(NotificationBase):
    admin_id: Optional[int] = None  # None = broadcast to all


class NotificationItem(NotificationBase):
    id: int
    admin_id: Optional[int] = None
    is_read: bool = False
    group_key: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class NotificationMarkRead(BaseModel):
    ids: List[int] = Field(default_factory=list, description="IDs to mark as read. Empty = mark all.")


class NotificationUnreadCount(BaseModel):
    count: int


class NotificationDeleteResult(BaseModel):
    deleted: int


# ── Notification Channels ────────────────────────────────────────

class ChannelConfig(BaseModel):
    model_config = ConfigDict(extra="ignore")

    channel_type: str  # in_app, telegram, webhook, email
    is_enabled: bool = True
    config: Dict[str, Any] = Field(default_factory=dict)


class ChannelConfigItem(ChannelConfig):
    id: int
    admin_id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ChannelConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None


# ── SMTP Config ──────────────────────────────────────────────────

class SmtpConfigRead(BaseModel):
    id: int
    host: str
    port: int = 587
    username: Optional[str] = None
    from_email: str
    from_name: Optional[str] = None
    use_tls: bool = True
    use_ssl: bool = False
    is_enabled: bool = False
    updated_at: Optional[datetime] = None


class SmtpConfigUpdate(BaseModel):
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    use_tls: Optional[bool] = None
    use_ssl: Optional[bool] = None
    is_enabled: Optional[bool] = None


class SmtpTestRequest(BaseModel):
    to_email: str
