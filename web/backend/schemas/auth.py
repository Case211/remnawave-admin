"""Auth schemas for web panel API."""
from typing import Optional, List
from pydantic import BaseModel, Field


class TelegramAuthData(BaseModel):
    """Telegram Login Widget auth data."""

    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class LoginRequest(BaseModel):
    """Username/password login request."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=200)


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Token refresh request.

    refresh_token опционален: веб-фронт на cookie-аутентификации шлёт
    пустое тело — сервер берёт токен из HttpOnly cookie rw_refresh.
    """

    refresh_token: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    """Change admin password request."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=200)


class PermissionEntry(BaseModel):
    """Single permission entry."""

    resource: str
    action: str


class RegisterRequest(BaseModel):
    """First-time admin registration request."""

    username: str = Field(..., min_length=3, max_length=100)
    password: str = Field(..., min_length=8, max_length=200)


class SetupStatusResponse(BaseModel):
    """Setup status — whether initial admin registration is needed."""

    needs_setup: bool


class LoginResponse(BaseModel):
    """Login response — may require 2FA step."""

    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: Optional[int] = None
    requires_2fa: bool = False
    totp_enabled: bool = False
    temp_token: Optional[str] = None


class TotpSetupResponse(BaseModel):
    """Response with TOTP provisioning data for first-time setup."""

    secret: str
    qr_code: str  # base64 PNG
    provisioning_uri: str
    backup_codes: List[str]


class TotpVerifyRequest(BaseModel):
    """TOTP verification or setup confirmation request."""

    code: str = Field(..., min_length=6, max_length=20)


class AdminInfo(BaseModel):
    """Current admin info with RBAC data."""

    telegram_id: Optional[int] = None
    username: str
    email: Optional[str] = None
    role: str
    role_id: Optional[int] = None
    account_id: Optional[int] = None
    # Quota limits (None = unlimited)
    max_users: Optional[int] = None
    max_traffic_gb: Optional[int] = None
    max_nodes: Optional[int] = None
    max_hosts: Optional[int] = None
    # Quota counters
    users_created: int = 0
    traffic_used_bytes: int = 0
    nodes_created: int = 0
    hosts_created: int = 0
    unlimited_traffic_policy: str = "allowed"
    auth_method: str = "telegram"
    password_is_generated: bool = False
    unrestricted_user_access: bool = False
    permissions: List[PermissionEntry] = []


class ForgotPasswordRequest(BaseModel):
    """Request to send password reset email."""

    email: str = Field(..., min_length=5, max_length=255)


class ResetPasswordRequest(BaseModel):
    """Request to reset password using token from email."""

    token: str = Field(..., min_length=10)
    new_password: str = Field(..., min_length=8, max_length=200)
