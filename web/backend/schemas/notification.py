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
    from_name: str = "Remnawave Admin"
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


# ── Alert Rules ──────────────────────────────────────────────────

class AlertRuleBase(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str
    description: Optional[str] = None
    rule_type: str = "threshold"  # threshold
    metric: Optional[str] = None
    operator: Optional[str] = None  # gt, gte, lt, lte, eq
    threshold: Optional[float] = None
    duration_minutes: int = 0
    channels: List[str] = Field(default_factory=lambda: ["in_app"])
    severity: str = "warning"  # info, warning, critical
    cooldown_minutes: int = 30
    escalation_admin_id: Optional[int] = None
    escalation_minutes: int = 0


class AlertRuleCreate(AlertRuleBase):
    is_enabled: bool = True


class AlertRuleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    rule_type: Optional[str] = None
    metric: Optional[str] = None
    operator: Optional[str] = None
    threshold: Optional[float] = None
    duration_minutes: Optional[int] = None
    channels: Optional[List[str]] = None
    severity: Optional[str] = None
    cooldown_minutes: Optional[int] = None
    escalation_admin_id: Optional[int] = None
    escalation_minutes: Optional[int] = None


class AlertRuleItem(AlertRuleBase):
    id: int
    is_enabled: bool
    group_key: Optional[str] = None
    last_triggered_at: Optional[datetime] = None
    last_value: Optional[float] = None
    trigger_count: int = 0
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ── Alert Rule Logs ──────────────────────────────────────────────

class AlertLogItem(BaseModel):
    id: int
    rule_id: Optional[int] = None
    rule_name: Optional[str] = None
    metric_value: Optional[float] = None
    threshold_value: Optional[float] = None
    severity: Optional[str] = None
    channels_notified: List[str] = Field(default_factory=list)
    acknowledged: bool = False
    acknowledged_by: Optional[int] = None
    acknowledged_at: Optional[datetime] = None
    details: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AlertLogAcknowledge(BaseModel):
    ids: List[int] = Field(default_factory=list)
