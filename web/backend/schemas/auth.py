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
    """Token refresh request."""

    refresh_token: str


class ChangePasswordRequest(BaseModel):
    """Change admin password request."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=200)


class PermissionEntry(BaseModel):
    """Single permission entry."""

    resource: str
    action: str


class AdminInfo(BaseModel):
    """Current admin info with RBAC data."""

    telegram_id: Optional[int] = None
    username: str
    role: str
    role_id: Optional[int] = None
    auth_method: str = "telegram"
    password_is_generated: bool = False
    permissions: List[PermissionEntry] = []
