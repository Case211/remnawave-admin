import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")
    api_base_url: AnyHttpUrl = Field(..., alias="API_BASE_URL")
    api_token: str | None = Field(default=None, alias="API_TOKEN")
    default_locale: str = Field("ru", alias="DEFAULT_LOCALE")
    admins_raw: str | None = Field(default=None, alias="ADMINS", exclude=True)
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    notifications_chat_id: int | None = Field(default=None, alias="NOTIFICATIONS_CHAT_ID")
    notifications_topic_id: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_ID")
    # Отдельные топики для разных типов уведомлений (fallback на notifications_topic_id)
    notifications_topic_users: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_USERS")
    notifications_topic_nodes: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_NODES")
    notifications_topic_service: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_SERVICE")
    notifications_topic_hwid: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_HWID")
    notifications_topic_crm: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_CRM")
    notifications_topic_errors: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_ERRORS")
    webhook_port: int = Field(default=8080, alias="WEBHOOK_PORT")
    webhook_secret: str | None = Field(default=None, alias="WEBHOOK_SECRET")
    
    # Database configuration
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    db_pool_min_size: int = Field(default=2, alias="DB_POOL_MIN_SIZE")
    db_pool_max_size: int = Field(default=10, alias="DB_POOL_MAX_SIZE")
    sync_interval_seconds: int = Field(default=300, alias="SYNC_INTERVAL_SECONDS")
    
    @property
    def database_enabled(self) -> bool:
        """Проверяет, включена ли база данных."""
        return bool(self.database_url)

    def get_topic_for_users(self) -> int | None:
        """Возвращает топик для пользовательских уведомлений."""
        return self.notifications_topic_users or self.notifications_topic_id

    def get_topic_for_nodes(self) -> int | None:
        """Возвращает топик для уведомлений о нодах."""
        return self.notifications_topic_nodes or self.notifications_topic_id

    def get_topic_for_service(self) -> int | None:
        """Возвращает топик для сервисных уведомлений."""
        return self.notifications_topic_service or self.notifications_topic_id

    def get_topic_for_hwid(self) -> int | None:
        """Возвращает топик для HWID уведомлений."""
        return self.notifications_topic_hwid or self.notifications_topic_id

    def get_topic_for_crm(self) -> int | None:
        """Возвращает топик для CRM/биллинг уведомлений."""
        return self.notifications_topic_crm or self.notifications_topic_id

    def get_topic_for_errors(self) -> int | None:
        """Возвращает топик для уведомлений об ошибках."""
        return self.notifications_topic_errors or self.notifications_topic_id

    @field_validator("notifications_chat_id", mode="before")
    @classmethod
    def parse_notifications_chat_id(cls, value):
        """Парсит NOTIFICATIONS_CHAT_ID в int или возвращает None."""
        raw_env_value = os.getenv("NOTIFICATIONS_CHAT_ID", "NOT_SET")
        print(f"DEBUG parse_notifications_chat_id: value={repr(value)}, type={type(value)}, raw_env={repr(raw_env_value)}")
        
        if value is None or value == "":
            print(f"DEBUG parse_notifications_chat_id: value is None or empty, returning None")
            return None
        if isinstance(value, int):
            print(f"DEBUG parse_notifications_chat_id: value is already int={value}, returning {value}")
            return value
        if isinstance(value, str):
            try:
                result = int(value)
                print(f"DEBUG parse_notifications_chat_id: parsed string '{value}' to int={result}")
                return result
            except ValueError:
                print(f"DEBUG parse_notifications_chat_id: failed to parse '{value}' as int, returning None")
                return None
        print(f"DEBUG parse_notifications_chat_id: value type not handled, returning None")
        return None
    
    @field_validator(
        "notifications_topic_id",
        "notifications_topic_users",
        "notifications_topic_nodes",
        "notifications_topic_service",
        "notifications_topic_hwid",
        "notifications_topic_crm",
        "notifications_topic_errors",
        mode="before",
    )
    @classmethod
    def parse_notifications_topic(cls, value):
        """Парсит topic ID в int или возвращает None."""
        if value is None or value == "":
            return None
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return None
        return None

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @property
    def admins(self) -> List[int]:
        """Парсит список администраторов из строки через запятую."""
        if not self.admins_raw:
            return []
        
        parts = [x.strip() for x in self.admins_raw.split(",")]
        admins = []
        for part in parts:
            if not part:
                continue
            try:
                admin_id = int(part)
                if admin_id > 0:
                    admins.append(admin_id)
            except ValueError:
                continue
        return admins

    @property
    def allowed_admins(self) -> set[int]:
        return set(self.admins)


@lru_cache
def get_settings() -> Settings:
    return Settings()
