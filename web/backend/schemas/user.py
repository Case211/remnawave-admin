"""User schemas for web panel API."""
from typing import Optional, List
from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, model_validator


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
    description: Optional[str] = None
    tag: Optional[str] = None
    expire_at: Optional[datetime] = None
    traffic_limit_bytes: Optional[int] = None
    traffic_limit_strategy: Optional[str] = None
    used_traffic_bytes: Optional[int] = 0
    lifetime_used_traffic_bytes: Optional[int] = 0
    hwid_device_limit: Optional[int] = 0
    hwid_device_count: Optional[int] = 0
    external_squad_uuid: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    online_at: Optional[datetime] = None
    last_triggered_threshold: Optional[int] = None

    @model_validator(mode='before')
    @classmethod
    def _coerce_nulls(cls, values):
        """Coerce None to 0 for numeric fields that the API may return as null."""
        if isinstance(values, dict):
            if values.get('used_traffic_bytes') is None:
                values['used_traffic_bytes'] = 0
            if values.get('lifetime_used_traffic_bytes') is None:
                values['lifetime_used_traffic_bytes'] = 0
            if values.get('hwid_device_limit') is None:
                values['hwid_device_limit'] = 0
            if values.get('hwid_device_count') is None:
                values['hwid_device_count'] = 0
            # Normalize status to lowercase (Remnawave API returns ACTIVE, DISABLED, etc.)
            status = values.get('status')
            if isinstance(status, str):
                values['status'] = status.lower()
        return values

    class Config:
        from_attributes = True


class UserDetail(UserListItem):
    """Detailed user information."""

    subscription_uuid: Optional[str] = None
    subscription_url: Optional[str] = None
    online_at: Optional[datetime] = None
    sub_last_user_agent: Optional[str] = None
    sub_last_opened_at: Optional[datetime] = None
    sub_revoked_at: Optional[datetime] = None
    last_traffic_reset_at: Optional[datetime] = None
    trojan_password: Optional[str] = None
    vless_uuid: Optional[str] = None
    ss_password: Optional[str] = None
    active_internal_squads: Optional[list] = None
    updated_at: Optional[datetime] = None
    last_triggered_threshold: Optional[int] = None
    first_connected_at: Optional[datetime] = None
    last_connected_node_uuid: Optional[str] = None

    # Anti-abuse info
    trust_score: Optional[int] = None
    violation_count_30d: int = 0
    active_connections: int = 0
    unique_ips_24h: int = 0


class UserCreate(BaseModel):
    """Create user request."""
    model_config = ConfigDict(extra='ignore')

    username: str
    expire_at: Optional[datetime] = None
    status: Optional[str] = None
    short_uuid: Optional[str] = None
    trojan_password: Optional[str] = None
    vless_uuid: Optional[str] = None
    ss_password: Optional[str] = None
    traffic_limit_bytes: Optional[int] = None
    traffic_limit_strategy: str = "NO_RESET"
    created_at: Optional[datetime] = None
    last_traffic_reset_at: Optional[datetime] = None
    description: Optional[str] = None
    tag: Optional[str] = None
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    hwid_device_limit: Optional[int] = None
    active_internal_squads: Optional[List[str]] = None
    uuid: Optional[str] = None
    external_squad_uuid: Optional[str] = None


class UserUpdate(BaseModel):
    """Update user request."""
    model_config = ConfigDict(extra='ignore')

    username: Optional[str] = None
    uuid: Optional[str] = None
    status: Optional[str] = None
    traffic_limit_bytes: Optional[int] = None
    traffic_limit_strategy: Optional[str] = None
    expire_at: Optional[datetime] = None
    description: Optional[str] = None
    tag: Optional[str] = None
    telegram_id: Optional[int] = None
    email: Optional[str] = None
    hwid_device_limit: Optional[int] = None
    active_internal_squads: Optional[List[str]] = None
    external_squad_uuid: Optional[str] = None


class HwidDevice(BaseModel):
    """HWID device record."""
    model_config = ConfigDict(extra='ignore')

    hwid: str
    platform: Optional[str] = None
    os_version: Optional[str] = None
    device_model: Optional[str] = None
    app_version: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


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
