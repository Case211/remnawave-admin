import os
from functools import lru_cache
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings(BaseSettings):
    bot_token: str = Field(..., alias="BOT_TOKEN")
    api_base_url: AnyHttpUrl = Field(..., alias="API_BASE_URL")
    api_token: str | None = Field(default=None, alias="API_TOKEN")
    default_locale: str = Field("ru", alias="DEFAULT_LOCALE")
    admins: List[int] = Field(default_factory=list, alias="ADMINS", json_schema_extra={"type": "string"})
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    notifications_chat_id: int | None = Field(default=None, alias="NOTIFICATIONS_CHAT_ID")
    notifications_topic_id: int | None = Field(default=None, alias="NOTIFICATIONS_TOPIC_ID")

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
        """Парсит список администраторов из строки, int или списка."""
        raw_env_value = os.getenv("ADMINS", "NOT_SET")
        print(f"DEBUG parse_admins: raw_env_value={repr(raw_env_value)}, value={repr(value)}, type={type(value)}")
        
        if value is None or value == "":
            print("DEBUG parse_admins: value is None or empty, returning []")
            return []
        
        # Если значение уже int (pydantic-settings иногда преобразует строку в int)
        if isinstance(value, int):
            print(f"DEBUG parse_admins: value is already int={value}, returning [{value}]")
            return [value] if value > 0 else []
        
        if isinstance(value, str):
            # Разделяем по запятой и убираем пробелы
            parts = [x.strip() for x in value.split(",")]
            print(f"DEBUG parse_admins: parts after split={parts}")
            # Фильтруем только цифры и конвертируем в int
            admins = []
            for part in parts:
                if not part:  # Пропускаем пустые строки
                    continue
                try:
                    admin_id = int(part)
                    if admin_id > 0:  # Telegram user IDs всегда положительные
                        admins.append(admin_id)
                except ValueError:
                    # Игнорируем нечисловые значения
                    print(f"DEBUG parse_admins: failed to parse part={repr(part)}")
                    continue
            print(f"DEBUG parse_admins: final admins={admins}")
            return admins
        
        if isinstance(value, list):
            result = [int(x) for x in value if isinstance(x, (int, str)) and (isinstance(x, int) or str(x).isdigit())]
            print(f"DEBUG parse_admins: value is list, result={result}")
            return result
        
        print(f"DEBUG parse_admins: value type not handled, returning []")
        return []
    
    @model_validator(mode="after")
    def parse_admins_from_env(self):
        """Дополнительная проверка: если admins пустой, но ADMINS в окружении есть, парсим его."""
        if not self.admins:
            raw_env_value = os.getenv("ADMINS")
            if raw_env_value:
                print(f"DEBUG parse_admins_from_env: admins is empty, but ADMINS env var exists: {repr(raw_env_value)}")
                # Парсим из окружения напрямую
                parts = [x.strip() for x in raw_env_value.split(",")]
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
                if admins:
                    print(f"DEBUG parse_admins_from_env: parsed admins={admins}, setting self.admins")
                    self.admins = admins
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
