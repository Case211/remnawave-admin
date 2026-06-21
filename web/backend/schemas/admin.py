"""Admin & RBAC schemas for web panel API."""
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field


# ── Permission ──────────────────────────────────────────────────

class PermissionItem(BaseModel):
    resource: str
    action: str


# ── Roles ───────────────────────────────────────────────────────

class RoleBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    display_name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class RoleCreate(RoleBase):
    permissions: List[PermissionItem] = []


class RoleUpdate(BaseModel):
    display_name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    permissions: Optional[List[PermissionItem]] = None


class RoleResponse(RoleBase):
    id: int
    is_system: bool
    permissions: List[PermissionItem] = []
    permissions_count: Optional[int] = None
    admins_count: Optional[int] = None
    created_at: Optional[datetime] = None


# ── Admin accounts ──────────────────────────────────────────────

class AdminAccountBase(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    telegram_id: Optional[int] = None
    role_id: int
    max_users: Optional[int] = Field(None, ge=0)
    max_traffic_gb: Optional[int] = Field(None, ge=0)
    max_nodes: Optional[int] = Field(None, ge=0)
    max_hosts: Optional[int] = Field(None, ge=0)
    has_bot_access: bool = False
    unlimited_traffic_policy: str = "allowed"
    unrestricted_user_access: bool = False  # scoping ON для НОВЫХ админов (изоляция multi-tenant); снимается опционально


class AdminAccountCreate(AdminAccountBase):
    password: Optional[str] = Field(None, min_length=8, max_length=200)


class AdminAccountUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[str] = Field(None, max_length=255)
    telegram_id: Optional[int] = None
    role_id: Optional[int] = None
    max_users: Optional[int] = Field(None, ge=0)
    max_traffic_gb: Optional[int] = Field(None, ge=0)
    max_nodes: Optional[int] = Field(None, ge=0)
    max_hosts: Optional[int] = Field(None, ge=0)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=200)
    has_bot_access: Optional[bool] = None
    unlimited_traffic_policy: Optional[str] = None
    unrestricted_user_access: Optional[bool] = None


class CounterResetRequest(BaseModel):
    counter: str = Field(..., description="Counter name: users_created, nodes_created, hosts_created, traffic_used_bytes")


class AdminAccountResponse(BaseModel):
    id: int
    username: str
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    role_id: Optional[int] = None
    role_name: Optional[str] = None
    role_display_name: Optional[str] = None
    max_users: Optional[int] = None
    max_traffic_gb: Optional[int] = None
    max_nodes: Optional[int] = None
    max_hosts: Optional[int] = None
    has_bot_access: bool = False
    users_created: int = 0
    traffic_used_bytes: int = 0
    nodes_created: int = 0
    hosts_created: int = 0
    is_active: bool = True
    is_generated_password: bool = False
    unlimited_traffic_policy: str = "allowed"
    unrestricted_user_access: bool = True
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AdminAccountListResponse(BaseModel):
    items: List[AdminAccountResponse]
    total: int


# ── Audit log ───────────────────────────────────────────────────

class AuditLogEntry(BaseModel):
    id: int
    admin_id: Optional[int] = None
    admin_username: str
    action: str
    resource: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[str] = None
    ip_address: Optional[str] = None
    created_at: Optional[datetime] = None


class AuditLogResponse(BaseModel):
    items: List[AuditLogEntry]
    total: int
