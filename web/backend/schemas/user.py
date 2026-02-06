"""User schemas for web panel API."""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """Base user fields."""
    model_config = ConfigDict(extra='ignore')

    username: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    status: str = 'active'


class UserListItem(UserBase):
    """User item in list."""

    uuid: str
    short_uuid: Optional[str] = None
    expire_at: Optional[datetime] = None
    traffic_limit_bytes: Optional[int] = None
    used_traffic_bytes: int = 0
    hwid_device_limit: int = 0
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class UserDetail(UserListItem):
    """Detailed user information."""

    subscription_uuid: Optional[str] = None
    online_at: Optional[datetime] = None
    sub_last_user_agent: Optional[str] = None

    # Anti-abuse info
    trust_score: Optional[int] = None
    violation_count_30d: int = 0
    active_connections: int = 0
    unique_ips_24h: int = 0


class UserCreate(BaseModel):
    """Create user request."""

    username: str
    traffic_limit_bytes: Optional[int] = None
    expire_days: Optional[int] = None
    hwid_device_limit: int = 3


class UserUpdate(BaseModel):
    """Update user request."""

    status: Optional[str] = None
    traffic_limit_bytes: Optional[int] = None
    expire_at: Optional[datetime] = None
    hwid_device_limit: Optional[int] = None


class UserConnection(BaseModel):
    """User connection record."""

    ip_address: str
    node_uuid: Optional[str] = None
    node_name: Optional[str] = None
    connected_at: datetime
    disconnected_at: Optional[datetime] = None
    country_code: Optional[str] = None
    city: Optional[str] = None
    asn_org: Optional[str] = None
