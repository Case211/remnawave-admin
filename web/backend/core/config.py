"""Web panel configuration."""
import os
from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class WebSettings(BaseSettings):
    """Settings for web panel."""

    # App
    debug: bool = Field(default=False, alias="WEB_DEBUG")
    secret_key: str = Field(..., alias="WEB_SECRET_KEY")
    host: str = Field(default="0.0.0.0", alias="WEB_HOST")
    port: int = Field(default=8081, alias="WEB_PORT")

    # JWT
    jwt_algorithm: str = Field(default="HS256", alias="WEB_JWT_ALGORITHM")
    jwt_expire_minutes: int = Field(default=1440, alias="WEB_JWT_EXPIRE_MINUTES")  # 24 hours
    jwt_refresh_days: int = Field(default=7, alias="WEB_JWT_REFRESH_DAYS")

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
        for admin_id in self.admins_raw.split(","):
            admin_id = admin_id.strip()
            if admin_id:
                try:
                    admins.append(int(admin_id))
                except ValueError:
                    pass
        return admins

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_web_settings() -> WebSettings:
    """Get cached web settings."""
    return WebSettings()
