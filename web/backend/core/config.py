"""Web panel configuration."""
import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class WebSettings(BaseSettings):
    """Settings for web panel."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    # App
    debug: bool = Field(default=False, alias="WEB_DEBUG")
    secret_key: str = Field(..., alias="WEB_SECRET_KEY")
    host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    port: int = Field(default=8081, alias="WEB_PORT")

    # JWT
    jwt_algorithm: str = Field(default="HS256", alias="WEB_JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=30, alias="WEB_JWT_EXPIRE_MINUTES")  # 30 min access token
    jwt_refresh_hours: int = Field(default=6, alias="WEB_JWT_REFRESH_HOURS")  # 6 hour session

    # Password auth (optional, alongside Telegram)
    admin_login: Optional[str] = Field(default=None, alias="WEB_ADMIN_LOGIN")
    admin_password: Optional[str] = Field(default=None, alias="WEB_ADMIN_PASSWORD")

    # IP whitelist (optional, comma-separated IPs/CIDRs — empty = allow all)
    allowed_ips: str = Field(default="", alias="WEB_ALLOWED_IPS")

    # CORS
    cors_origins_raw: str = Field(
        default="http://localhost:3000,http://localhost:5173",
        alias="WEB_CORS_ORIGINS"
    )

    # Telegram (for auth verification)
    telegram_bot_token: str = Field(..., alias="BOT_TOKEN")

    # Database (shared with bot)
    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")

    # API (shared with bot)
    api_base_url: str = Field(..., alias="API_BASE_URL")
    api_token: Optional[str] = Field(default=None, alias="API_TOKEN")

    # Admins list (shared with bot)
    admins_raw: str = Field(default="", alias="ADMINS")

    @field_validator("jwt_algorithm", mode="before")
    @classmethod
    def validate_jwt_algorithm(cls, v):
        """Only allow secure HMAC-based JWT algorithms."""
        allowed = {"HS256", "HS384", "HS512"}
        if v not in allowed:
            raise ValueError(f"JWT algorithm must be one of {allowed}, got: {v}")
        return v

    @field_validator("admins_raw", mode="before")
    @classmethod
    def coerce_admins_to_str(cls, v):
        """Ensure admins_raw is always a string (env vars may be parsed as int)."""
        if v is None:
            return ""
        return str(v)

    @property
    def cors_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if not self.cors_origins_raw:
            return []
        return [origin.strip() for origin in self.cors_origins_raw.split(",") if origin.strip()]

    @property
    def admins(self) -> List[int]:
        """Parse admins list from comma-separated string."""
        if not self.admins_raw:
            return []
        admins = []
        for admin_id in str(self.admins_raw).split(","):
            admin_id = admin_id.strip()
            if admin_id:
                try:
                    admins.append(int(admin_id))
                except ValueError:
                    pass
        return admins


@lru_cache()
def get_web_settings() -> WebSettings:
    """Get cached web settings."""
    return WebSettings()
