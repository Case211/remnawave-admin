"""Auth schemas for web panel API."""
from typing import Optional
from pydantic import BaseModel


class TelegramAuthData(BaseModel):
    """Telegram Login Widget auth data."""

    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    photo_url: Optional[str] = None
    auth_date: int
    hash: str


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class RefreshRequest(BaseModel):
    """Token refresh request."""

    refresh_token: str


class AdminInfo(BaseModel):
    """Current admin info."""

    telegram_id: int
    username: str
    role: str
