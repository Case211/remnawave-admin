from functools import lru_cache
from pathlib import Path
from typing import List

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
    admins: List[int] = Field(default_factory=list, alias="ADMINS")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    @property
    def allowed_admins(self) -> set[int]:
        return set(self.admins)

    @field_validator("admins", mode="before")
    @classmethod
    def parse_admins(cls, value):
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [int(x) for x in value.split(",") if x.strip().isdigit()]
        if isinstance(value, list):
            return [int(x) for x in value]
        return []


@lru_cache
def get_settings() -> Settings:
    return Settings()
