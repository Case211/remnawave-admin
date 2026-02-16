"""Shared configuration for modules used by both bot and web panel.

Contains ONLY fields needed by shared modules (database, api_client,
cache, logger, geoip, sync, etc.). Bot and web panel have their own
extended Settings classes for process-specific configuration.
"""
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env from project root
_BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(_BASE_DIR / ".env")


class SharedSettings(BaseSettings):
    """Settings shared between bot and web panel."""

    # API
    api_base_url: AnyHttpUrl = Field(..., alias="API_BASE_URL")
    api_token: str | None = Field(default=None, alias="API_TOKEN")

    # Logging
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    # Database
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_pool_min_size: int = Field(default=2, alias="DB_POOL_MIN_SIZE")
    db_pool_max_size: int = Field(default=10, alias="DB_POOL_MAX_SIZE")
    sync_interval_seconds: int = Field(default=300, alias="SYNC_INTERVAL_SECONDS")

    # GeoIP / MaxMind
    maxmind_license_key: str | None = Field(default=None, alias="MAXMIND_LICENSE_KEY")
    maxmind_city_db: str | None = Field(
        default="/app/geoip/GeoLite2-City.mmdb", alias="MAXMIND_CITY_DB"
    )
    maxmind_asn_db: str | None = Field(
        default="/app/geoip/GeoLite2-ASN.mmdb", alias="MAXMIND_ASN_DB"
    )

    @property
    def database_enabled(self) -> bool:
        """Проверяет, включена ли база данных."""
        return bool(self.database_url)

    model_config = SettingsConfigDict(
        env_file=_BASE_DIR / ".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )


@lru_cache
def get_shared_settings() -> SharedSettings:
    return SharedSettings()
