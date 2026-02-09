"""
Конфигурация Node Agent.
Переменные окружения или .env в папке node-agent.
"""
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="AGENT_",
        extra="ignore",
    )

    # Идентификация ноды (UUID из Remnawave/Admin Bot)
    node_uuid: str

    # URL Collector API в Admin Bot (без trailing slash)
    # Пример: https://admin.example.com или http://host.docker.internal:8000
    collector_url: str

    # Токен для аутентификации агента (выдаётся в Admin Bot)
    auth_token: str

    # Интервал отправки батчей (секунды)
    # В real-time режиме используется для отправки накопленных подключений
    interval_seconds: int = 30

    # Режим парсинга логов: "polling" (периодический опрос) или "realtime" (отслеживание новых строк)
    log_parsing_mode: str = "realtime"  # "polling" или "realtime"
    
    # Интервал проверки новых строк в real-time режиме (секунды)
    # Может быть меньше interval_seconds для более быстрой реакции
    # По умолчанию равен interval_seconds
    realtime_check_interval_seconds: Optional[float] = None

    # Путь к access.log на ноде (Remnawave использует /var/log/remnanode/access.log)
    # В Docker: монтировать том с логами
    xray_log_path: str = "/var/log/remnanode/access.log"

    # Размер буфера при tail (байт) — сколько читать с конца при старте
    log_read_buffer_bytes: int = 1024 * 1024  # 1 MB

    # Retry при отправке в Collector
    send_max_retries: int = 3
    send_retry_delay_seconds: float = 5.0

    # Максимальный размер буфера накопленных подключений (защита от утечки памяти)
    # Если Collector API недоступен, буфер не будет расти бесконечно
    max_buffer_size: int = 50_000

    # Логирование
    log_level: str = "INFO"
