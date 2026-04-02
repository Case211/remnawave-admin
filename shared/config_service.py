"""
Dynamic configuration service for bot settings.
Allows managing configuration through database with .env fallback.
"""
import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from shared.database import db_service
from shared.logger import logger


class ConfigValueType(str, Enum):
    """Типы значений конфигурации."""
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    JSON = "json"


class ConfigCategory(str, Enum):
    """Категории настроек."""
    GENERAL = "general"
    NOTIFICATIONS = "notifications"
    SYNC = "sync"
    REPORTS = "reports"
    VIOLATIONS = "violations"
    MAILSERVER = "mailserver"
    PERFORMANCE = "performance"


@dataclass
class ConfigItem:
    """Элемент конфигурации."""
    key: str
    value: Optional[str]
    value_type: ConfigValueType
    category: ConfigCategory
    subcategory: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    env_var_name: Optional[str] = None
    is_secret: bool = False
    is_readonly: bool = False
    validation_regex: Optional[str] = None
    options: Optional[List[str]] = None
    sort_order: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def get_typed_value(self) -> Any:
        """Возвращает значение в правильном типе."""
        if self.value is None:
            return self._convert_value(self.default_value)
        return self._convert_value(self.value)

    def _convert_value(self, val: Optional[str]) -> Any:
        """Конвертирует строковое значение в нужный тип."""
        if val is None:
            return None

        try:
            if self.value_type == ConfigValueType.INT:
                return int(val)
            elif self.value_type == ConfigValueType.FLOAT:
                return float(val)
            elif self.value_type == ConfigValueType.BOOL:
                return val.lower() in ("true", "1", "yes", "on")
            elif self.value_type == ConfigValueType.JSON:
                return json.loads(val)
            else:
                return val
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("Failed to convert config value %s: %s", self.key, e)
            return val


# Предустановленные настройки с их метаданными
DEFAULT_CONFIG_DEFINITIONS: List[Dict[str, Any]] = [
    # === GENERAL ===
    {
        "key": "bot_language",
        "value_type": "string",
        "category": "general",
        "display_name": "Язык бота",
        "description": "Язык интерфейса бота",
        "default_value": "ru",
        "env_var_name": "DEFAULT_LOCALE",
        "options": ["ru", "en"],
        "sort_order": 1,
    },
    {
        "key": "log_level",
        "value_type": "string",
        "category": "general",
        "display_name": "Уровень логирования",
        "description": "Уровень детализации логов (применяется мгновенно)",
        "default_value": "INFO",
        "env_var_name": "LOG_LEVEL",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "sort_order": 2,
    },
    {
        "key": "log_max_size_mb",
        "value_type": "int",
        "category": "general",
        "display_name": "Макс. размер лог-файла (MB)",
        "description": "Максимальный размер одного лог-файла перед ротацией",
        "default_value": "10",
        "sort_order": 3,
    },
    {
        "key": "log_backup_count",
        "value_type": "int",
        "category": "general",
        "display_name": "Кол-во бэкапов логов",
        "description": "Количество сжатых бэкап-файлов при ротации",
        "default_value": "5",
        "sort_order": 4,
    },

    {
        "key": "panel_name",
        "value_type": "string",
        "category": "general",
        "display_name": "Название панели",
        "description": "Отображаемое название проекта в боковом меню (рядом с логотипом)",
        "default_value": "",
        "sort_order": 6,
    },

    # === GEOIP ===
    {
        "key": "maxmind_source",
        "value_type": "string",
        "category": "general",
        "display_name": "Источник MaxMind GeoIP",
        "description": "auto — GitHub (ltsdev/maxmind) затем MaxMind; github — только GitHub (без ключа); maxmind — только официальный (нужен ключ)",
        "default_value": "auto",
        "env_var_name": "MAXMIND_SOURCE",
        "options": ["auto", "github", "maxmind"],
        "sort_order": 5,
    },

    # === NOTIFICATIONS ===
    {
        "key": "notifications_chat_id",
        "value_type": "int",
        "category": "notifications",
        "display_name": "ID чата уведомлений",
        "description": "Telegram ID чата/группы для уведомлений",
        "env_var_name": "NOTIFICATIONS_CHAT_ID",
        "sort_order": 1,
    },
    {
        "key": "notifications_topic_id",
        "value_type": "int",
        "category": "notifications",
        "subcategory": "topics",
        "display_name": "Топик: Общий (fallback)",
        "description": "ID топика по умолчанию, используется если специфический топик не задан",
        "env_var_name": "NOTIFICATIONS_TOPIC_ID",
        "sort_order": 9,
    },
    {
        "key": "notifications_topic_users",
        "value_type": "int",
        "category": "notifications",
        "subcategory": "topics",
        "display_name": "Топик: Пользователи",
        "description": "ID топика для уведомлений о пользователях",
        "env_var_name": "NOTIFICATIONS_TOPIC_USERS",
        "sort_order": 10,
    },
    {
        "key": "notifications_topic_nodes",
        "value_type": "int",
        "category": "notifications",
        "subcategory": "topics",
        "display_name": "Топик: Ноды",
        "description": "ID топика для уведомлений о нодах",
        "env_var_name": "NOTIFICATIONS_TOPIC_NODES",
        "sort_order": 11,
    },
    {
        "key": "notifications_topic_service",
        "value_type": "int",
        "category": "notifications",
        "subcategory": "topics",
        "display_name": "Топик: Сервис",
        "description": "ID топика для сервисных уведомлений",
        "env_var_name": "NOTIFICATIONS_TOPIC_SERVICE",
        "sort_order": 12,
    },
    {
        "key": "notifications_topic_hwid",
        "value_type": "int",
        "category": "notifications",
        "subcategory": "topics",
        "display_name": "Топик: HWID",
        "description": "ID топика для HWID уведомлений",
        "env_var_name": "NOTIFICATIONS_TOPIC_HWID",
        "sort_order": 13,
    },
    {
        "key": "notifications_topic_violations",
        "value_type": "int",
        "category": "notifications",
        "subcategory": "topics",
        "display_name": "Топик: Нарушения",
        "description": "ID топика для уведомлений о нарушениях",
        "env_var_name": "NOTIFICATIONS_TOPIC_VIOLATIONS",
        "sort_order": 14,
    },
    {
        "key": "notifications_topic_errors",
        "value_type": "int",
        "category": "notifications",
        "subcategory": "topics",
        "display_name": "Топик: Ошибки",
        "description": "ID топика для уведомлений об ошибках",
        "env_var_name": "NOTIFICATIONS_TOPIC_ERRORS",
        "sort_order": 15,
    },

    # === SYNC ===
    {
        "key": "sync_interval_seconds",
        "value_type": "int",
        "category": "sync",
        "display_name": "Интервал синхронизации",
        "description": "Интервал синхронизации данных с API (секунды, требует перезапуск)",
        "default_value": "300",
        "env_var_name": "SYNC_INTERVAL_SECONDS",
        "sort_order": 1,
    },

    # === REPORTS ===
    {
        "key": "reports_enabled",
        "value_type": "bool",
        "category": "reports",
        "display_name": "Отчёты включены",
        "description": "Глобальное включение/выключение автоматических отчётов",
        "default_value": "true",
        "sort_order": 1,
    },
    {
        "key": "reports_daily_enabled",
        "value_type": "bool",
        "category": "reports",
        "display_name": "Ежедневные отчёты",
        "description": "Включить ежедневные отчёты по нарушениям",
        "default_value": "true",
        "sort_order": 2,
    },
    {
        "key": "reports_daily_time",
        "value_type": "string",
        "category": "reports",
        "display_name": "Время дневного отчёта",
        "description": "Время отправки ежедневного отчёта (HH:MM по UTC)",
        "default_value": "09:00",
        "sort_order": 3,
    },
    {
        "key": "reports_weekly_enabled",
        "value_type": "bool",
        "category": "reports",
        "display_name": "Еженедельные отчёты",
        "description": "Включить еженедельные отчёты по нарушениям",
        "default_value": "true",
        "sort_order": 4,
    },
    {
        "key": "reports_weekly_day",
        "value_type": "int",
        "category": "reports",
        "display_name": "День недельного отчёта",
        "description": "День недели для еженедельного отчёта (0=Пн, 6=Вс)",
        "default_value": "0",
        "sort_order": 5,
    },
    {
        "key": "reports_weekly_time",
        "value_type": "string",
        "category": "reports",
        "display_name": "Время недельного отчёта",
        "description": "Время отправки еженедельного отчёта (HH:MM по UTC)",
        "default_value": "10:00",
        "sort_order": 6,
    },
    {
        "key": "reports_monthly_enabled",
        "value_type": "bool",
        "category": "reports",
        "display_name": "Ежемесячные отчёты",
        "description": "Включить ежемесячные отчёты по нарушениям",
        "default_value": "true",
        "sort_order": 7,
    },
    {
        "key": "reports_monthly_day",
        "value_type": "int",
        "category": "reports",
        "display_name": "День месячного отчёта",
        "description": "День месяца для ежемесячного отчёта (1-28)",
        "default_value": "1",
        "sort_order": 8,
    },
    {
        "key": "reports_monthly_time",
        "value_type": "string",
        "category": "reports",
        "display_name": "Время месячного отчёта",
        "description": "Время отправки ежемесячного отчёта (HH:MM по UTC)",
        "default_value": "10:00",
        "sort_order": 9,
    },
    {
        "key": "reports_min_score",
        "value_type": "float",
        "category": "reports",
        "display_name": "Минимальный скор",
        "description": "Минимальный скор нарушения для включения в отчёт",
        "default_value": "30.0",
        "sort_order": 10,
    },
    {
        "key": "reports_top_violators_count",
        "value_type": "int",
        "category": "reports",
        "display_name": "Топ нарушителей",
        "description": "Количество пользователей в топе нарушителей",
        "default_value": "10",
        "sort_order": 11,
    },
    {
        "key": "reports_send_empty",
        "value_type": "bool",
        "category": "reports",
        "display_name": "Отправлять пустые",
        "description": "Отправлять отчёт если нет нарушений за период",
        "default_value": "false",
        "sort_order": 12,
    },
    {
        "key": "reports_topic_id",
        "value_type": "int",
        "category": "reports",
        "display_name": "Топик отчётов",
        "description": "ID топика для отправки отчётов (0 = основной чат)",
        "env_var_name": "NOTIFICATIONS_TOPIC_REPORTS",
        "sort_order": 13,
    },

    # === VIOLATIONS ===
    {
        "key": "violations_enabled",
        "value_type": "bool",
        "category": "violations",
        "display_name": "Детектирование нарушений",
        "description": "Глобальное включение/выключение детектирования нарушений",
        "default_value": "true",
        "sort_order": 1,
    },
    {
        "key": "violations_min_score",
        "value_type": "float",
        "category": "violations",
        "display_name": "Минимальный скор уведомления",
        "description": "Минимальный скор нарушения для отправки уведомления (по умолчанию 50)",
        "default_value": "50.0",
        "sort_order": 2,
    },
    {
        "key": "violations_analyzer_temporal",
        "value_type": "bool",
        "category": "violations",
        "display_name": "Временной анализатор",
        "description": "Анализ одновременных подключений и паттернов переключения",
        "default_value": "true",
        "sort_order": 3,
    },
    {
        "key": "violations_analyzer_geo",
        "value_type": "bool",
        "category": "violations",
        "display_name": "Гео-анализатор",
        "description": "Определение невозможных перемещений и подозрительной географии",
        "default_value": "true",
        "sort_order": 4,
    },
    {
        "key": "violations_analyzer_asn",
        "value_type": "bool",
        "category": "violations",
        "display_name": "ASN-анализатор",
        "description": "Классификация провайдеров (VPN, датацентр, мобильный оператор)",
        "default_value": "true",
        "sort_order": 5,
    },
    {
        "key": "violations_analyzer_profile",
        "value_type": "bool",
        "category": "violations",
        "display_name": "Профильный анализатор",
        "description": "Анализ отклонений от обычного поведения пользователя",
        "default_value": "true",
        "sort_order": 6,
    },
    {
        "key": "violations_analyzer_device",
        "value_type": "bool",
        "category": "violations",
        "display_name": "Анализатор устройств",
        "description": "Определение уникальных fingerprint устройств (ОС, клиент)",
        "default_value": "true",
        "sort_order": 7,
    },
    {
        "key": "violations_analyzer_hwid",
        "value_type": "bool",
        "category": "violations",
        "display_name": "HWID кросс-аккаунт анализатор",
        "description": "Обнаружение одного HWID на нескольких аккаунтах (триальный абьюз)",
        "default_value": "true",
        "sort_order": 8,
    },
    {
        "key": "violations_max_simultaneous_ips",
        "value_type": "int",
        "category": "violations",
        "subcategory": "thresholds",
        "display_name": "Макс. одновременных IP",
        "description": "Максимальное количество одновременных IP сверх лимита устройств для срабатывания (0 = авто по кол-ву устройств)",
        "default_value": "0",
        "sort_order": 10,
    },
    {
        "key": "violations_geo_max_city_distance_km",
        "value_type": "int",
        "category": "violations",
        "subcategory": "thresholds",
        "display_name": "Макс. расстояние между городами (км)",
        "description": "Расстояние между городами ниже которого не считается подозрительным",
        "default_value": "50",
        "sort_order": 11,
    },
    {
        "key": "violations_hwid_max_accounts",
        "value_type": "int",
        "category": "violations",
        "subcategory": "thresholds",
        "display_name": "Макс. аккаунтов на один HWID",
        "description": "Количество аккаунтов на одном HWID для срабатывания (по умолчанию 2)",
        "default_value": "2",
        "sort_order": 12,
    },
    {
        "key": "violations_max_unique_ips_per_day",
        "value_type": "int",
        "category": "violations",
        "subcategory": "thresholds",
        "display_name": "Макс. уникальных IP в день",
        "description": "Превышение этого количества уникальных IP за день вызывает предупреждение (0 = авто по профилю)",
        "default_value": "0",
        "sort_order": 13,
    },
    {
        "key": "violations_notification_cooldown_minutes",
        "value_type": "int",
        "category": "violations",
        "subcategory": "thresholds",
        "display_name": "Кулдаун уведомлений (мин)",
        "description": "Минимальный интервал между уведомлениями по одному пользователю",
        "default_value": "30",
        "sort_order": 14,
    },
    {
        "key": "violations_hard_block_ips",
        "value_type": "int",
        "category": "violations",
        "subcategory": "hard_block",
        "display_name": "Жёсткая блокировка: макс. IP",
        "description": "Количество уникальных IP для автоматической жёсткой блокировки",
        "default_value": "50",
        "sort_order": 20,
    },
    {
        "key": "violations_hard_block_simultaneous",
        "value_type": "int",
        "category": "violations",
        "subcategory": "hard_block",
        "display_name": "Жёсткая блокировка: макс. одновременных",
        "description": "Количество одновременных подключений для жёсткой блокировки",
        "default_value": "20",
        "sort_order": 21,
    },
    {
        "key": "violations_hard_block_devices",
        "value_type": "int",
        "category": "violations",
        "subcategory": "hard_block",
        "display_name": "Жёсткая блокировка: макс. устройств",
        "description": "Количество уникальных fingerprint устройств для жёсткой блокировки",
        "default_value": "80",
        "sort_order": 22,
    },
    {
        "key": "violations_hard_block_hwid_matches",
        "value_type": "int",
        "category": "violations",
        "subcategory": "hard_block",
        "display_name": "Жёсткая блокировка: макс. совпадений HWID",
        "description": "Количество совпадающих HWID (одна модель) для жёсткой блокировки",
        "default_value": "10",
        "sort_order": 23,
    },
    {
        "key": "violations_trial_tags",
        "value_type": "string",
        "category": "violations",
        "subcategory": "trial",
        "display_name": "Теги триальных пользователей",
        "description": "Теги через запятую, при наличии которых пользователь считается триальным (например: trial,test,free)",
        "default_value": "trial",
        "sort_order": 30,
    },
    {
        "key": "violations_trial_squad_uuids",
        "value_type": "json",
        "category": "violations",
        "subcategory": "trial",
        "display_name": "Internal squad триальных",
        "description": "Выберите internal squad, пользователи которых считаются триальными",
        "default_value": "[]",
        "sort_order": 31,
    },

    # === TORRENT DETECTION ===
    {
        "key": "torrent_detection_enabled",
        "value_type": "bool",
        "category": "violations",
        "subcategory": "torrent",
        "display_name": "Обнаружение торрентов",
        "description": "Включение/выключение обнаружения торрент-трафика через Xray routing",
        "default_value": "true",
        "sort_order": 40,
    },
    {
        "key": "torrent_auto_action",
        "value_type": "string",
        "category": "violations",
        "subcategory": "torrent",
        "display_name": "Авто-действие при торренте",
        "description": "Действие при обнаружении торрент-трафика: notify (только уведомление), block_user (блокировка)",
        "default_value": "notify",
        "sort_order": 41,
    },
    {
        "key": "torrent_notification_cooldown_minutes",
        "value_type": "int",
        "category": "violations",
        "subcategory": "torrent",
        "display_name": "Кулдаун торрент-уведомлений (мин)",
        "description": "Минимальный интервал между уведомлениями о торрентах по одному пользователю",
        "default_value": "30",
        "sort_order": 42,
    },

    # === TRAFFIC RATE MONITOR ===
    {
        "key": "traffic_rate_enabled",
        "value_type": "bool",
        "category": "violations",
        "subcategory": "traffic_rate",
        "display_name": "Монитор скорости трафика",
        "description": "Отслеживание аномально высокого потребления трафика за период",
        "default_value": "false",
        "sort_order": 50,
    },
    {
        "key": "traffic_rate_threshold_gb",
        "value_type": "float",
        "category": "violations",
        "subcategory": "traffic_rate",
        "display_name": "Порог (GB за период)",
        "description": "Уведомление если пользователь потребил больше указанного объёма за период",
        "default_value": "10.0",
        "sort_order": 51,
    },
    {
        "key": "traffic_rate_window_minutes",
        "value_type": "int",
        "category": "violations",
        "subcategory": "traffic_rate",
        "display_name": "Окно проверки (мин)",
        "description": "Период времени для подсчёта трафика (по умолчанию 60 = 1 час)",
        "default_value": "60",
        "sort_order": 52,
    },
    {
        "key": "traffic_rate_check_interval_minutes",
        "value_type": "int",
        "category": "violations",
        "subcategory": "traffic_rate",
        "display_name": "Интервал проверки (мин)",
        "description": "Как часто проверять потребление трафика",
        "default_value": "5",
        "sort_order": 53,
    },
    {
        "key": "traffic_rate_cooldown_minutes",
        "value_type": "int",
        "category": "violations",
        "subcategory": "traffic_rate",
        "display_name": "Кулдаун уведомлений (мин)",
        "description": "Минимальный интервал между повторными уведомлениями по одному пользователю",
        "default_value": "60",
        "sort_order": 54,
    },

    # === MAILSERVER ===
    {
        "key": "mailserver_enabled",
        "value_type": "bool",
        "category": "mailserver",
        "display_name": "Почтовый сервер включён",
        "description": "Включить встроенный почтовый сервер (отправка/приём писем)",
        "default_value": "false",
        "env_var_name": "MAIL_SERVER_ENABLED",
        "sort_order": 1,
    },
    {
        "key": "mailserver_hostname",
        "value_type": "string",
        "category": "mailserver",
        "display_name": "Хост SMTP-сервера",
        "description": "IP-адрес для входящего SMTP-сервера (0.0.0.0 = все интерфейсы)",
        "default_value": "0.0.0.0",
        "env_var_name": "MAIL_SERVER_HOSTNAME",
        "sort_order": 2,
    },
    {
        "key": "mailserver_inbound_port",
        "value_type": "int",
        "category": "mailserver",
        "display_name": "Порт входящего SMTP",
        "description": "Порт для приёма входящих писем (по умолчанию 2525, в продакшене 25)",
        "default_value": "2525",
        "env_var_name": "MAIL_INBOUND_PORT",
        "sort_order": 3,
    },
    {
        "key": "mailserver_max_send_per_hour",
        "value_type": "int",
        "category": "mailserver",
        "display_name": "Лимит отправки в час",
        "description": "Максимальное количество писем с одного домена в час (по умолчанию)",
        "default_value": "100",
        "sort_order": 4,
    },
    {
        "key": "mailserver_queue_poll_interval",
        "value_type": "int",
        "category": "mailserver",
        "display_name": "Интервал опроса очереди",
        "description": "Как часто проверять очередь писем на отправку (секунды)",
        "default_value": "10",
        "sort_order": 5,
    },
    {
        "key": "mailserver_max_retries",
        "value_type": "int",
        "category": "mailserver",
        "display_name": "Макс. попыток отправки",
        "description": "Максимальное количество попыток отправки одного письма",
        "default_value": "5",
        "sort_order": 6,
    },
    {
        "key": "mailserver_submission_enabled",
        "value_type": "bool",
        "category": "mailserver",
        "display_name": "SMTP Submission включён",
        "description": "Включить SMTP Submission сервер (порт 587) для отправки писем через логин/пароль",
        "default_value": "false",
        "env_var_name": "MAIL_SUBMISSION_ENABLED",
        "sort_order": 7,
    },
    {
        "key": "mailserver_submission_port",
        "value_type": "int",
        "category": "mailserver",
        "display_name": "Порт SMTP Submission",
        "description": "Порт для SMTP Submission сервера (стандарт — 587)",
        "default_value": "587",
        "env_var_name": "MAIL_SUBMISSION_PORT",
        "sort_order": 8,
    },

    # === SECURITY ===
    {
        "key": "auth_telegram_enabled",
        "value_type": "bool",
        "category": "security",
        "subcategory": "auth_methods",
        "display_name": "Авторизация через Telegram",
        "description": "Разрешить вход через Telegram Login Widget",
        "default_value": "true",
        "sort_order": 1,
    },
    {
        "key": "auth_password_enabled",
        "value_type": "bool",
        "category": "security",
        "subcategory": "auth_methods",
        "display_name": "Авторизация по паролю",
        "description": "Разрешить вход по логину и паролю",
        "default_value": "true",
        "sort_order": 2,
    },
    {
        "key": "auth_totp_required",
        "value_type": "bool",
        "category": "security",
        "subcategory": "auth_methods",
        "display_name": "Обязательная 2FA (TOTP)",
        "description": "Требовать настройку TOTP для всех аккаунтов (при входе без 2FA будет предложено настроить)",
        "default_value": "false",
        "sort_order": 3,
    },
    {
        "key": "auth_max_attempts",
        "value_type": "int",
        "category": "security",
        "subcategory": "brute_force",
        "display_name": "Макс. попыток до блокировки",
        "description": "Количество неудачных попыток входа до блокировки IP-адреса",
        "default_value": "5",
        "sort_order": 4,
    },
    {
        "key": "auth_lockout_minutes",
        "value_type": "int",
        "category": "security",
        "subcategory": "brute_force",
        "display_name": "Длительность блокировки (мин)",
        "description": "На сколько минут блокируется IP после превышения лимита попыток",
        "default_value": "15",
        "sort_order": 5,
    },
    {
        "key": "auth_fail2ban_logging",
        "value_type": "bool",
        "category": "security",
        "subcategory": "brute_force",
        "display_name": "Fail2ban логирование",
        "description": "Записывать неудачные попытки входа в auth_failures.log (для интеграции с fail2ban)",
        "default_value": "true",
        "sort_order": 6,
    },
    {
        "key": "auth_notify_on_block",
        "value_type": "bool",
        "category": "security",
        "subcategory": "brute_force",
        "display_name": "Уведомление при блокировке IP",
        "description": "Отправлять уведомление в Telegram при блокировке IP-адреса",
        "default_value": "true",
        "sort_order": 7,
    },
    {
        "key": "auth_notify_on_failure",
        "value_type": "bool",
        "category": "security",
        "subcategory": "brute_force",
        "display_name": "Уведомление при неудачном входе",
        "description": "Отправлять уведомление в Telegram при каждой неудачной попытке входа",
        "default_value": "true",
        "sort_order": 8,
    },

    # === PERFORMANCE ===
    {
        "key": "db_pool_min_size",
        "value_type": "int",
        "category": "performance",
        "subcategory": "database",
        "display_name": "DB Pool: минимум соединений",
        "description": "Минимальное количество соединений в пуле PostgreSQL. Требуется перезапуск.",
        "default_value": "5",
        "env_var_name": "DB_POOL_MIN_SIZE",
        "sort_order": 1,
    },
    {
        "key": "db_pool_max_size",
        "value_type": "int",
        "category": "performance",
        "subcategory": "database",
        "display_name": "DB Pool: максимум соединений",
        "description": "Максимальное количество соединений в пуле PostgreSQL. Увеличьте при высокой нагрузке. Требуется перезапуск.",
        "default_value": "50",
        "env_var_name": "DB_POOL_MAX_SIZE",
        "sort_order": 2,
    },
    {
        "key": "db_statement_timeout",
        "value_type": "int",
        "category": "performance",
        "subcategory": "database",
        "display_name": "DB: таймаут запросов (сек)",
        "description": "Максимальное время выполнения SQL-запроса в секундах. 0 = без ограничений. Требуется перезапуск.",
        "default_value": "60",
        "sort_order": 3,
    },
    {
        "key": "db_idle_connection_lifetime",
        "value_type": "int",
        "category": "performance",
        "subcategory": "database",
        "display_name": "DB: время жизни простаивающего соединения (сек)",
        "description": "Через сколько секунд закрывать неиспользуемое соединение в пуле. Требуется перезапуск.",
        "default_value": "300",
        "sort_order": 4,
    },
    {
        "key": "sync_interval_seconds",
        "value_type": "int",
        "category": "performance",
        "subcategory": "intervals",
        "display_name": "Интервал синхронизации (сек)",
        "description": "Как часто синхронизировать данные с API панели Remnawave. Меньше = актуальнее данные, но выше нагрузка.",
        "default_value": "120",
        "env_var_name": "SYNC_INTERVAL",
        "sort_order": 10,
    },
    {
        "key": "alert_check_interval",
        "value_type": "int",
        "category": "performance",
        "subcategory": "intervals",
        "display_name": "Интервал проверки алертов (сек)",
        "description": "Как часто проверять правила алертов. Меньше = быстрее реакция, но выше нагрузка на БД.",
        "default_value": "60",
        "sort_order": 11,
    },
    {
        "key": "config_auto_reload_interval",
        "value_type": "int",
        "category": "performance",
        "subcategory": "intervals",
        "display_name": "Автообновление конфига (сек)",
        "description": "Как часто перезагружать конфигурацию из БД. Влияет на скорость применения настроек.",
        "default_value": "30",
        "sort_order": 12,
    },
    {
        "key": "api_rate_limit_per_minute",
        "value_type": "int",
        "category": "performance",
        "subcategory": "rate_limits",
        "display_name": "API: лимит запросов/мин (общий)",
        "description": "Максимальное количество API-запросов в минуту на один IP. 0 = без ограничений.",
        "default_value": "120",
        "sort_order": 20,
    },
    {
        "key": "collector_rate_limit",
        "value_type": "string",
        "category": "performance",
        "subcategory": "rate_limits",
        "display_name": "Collector: лимит запросов",
        "description": "Rate limit для эндпоинта сбора метрик от нод-агентов (формат: '1/second').",
        "default_value": "1/second",
        "sort_order": 21,
    },
    {
        "key": "cache_max_entries",
        "value_type": "int",
        "category": "performance",
        "subcategory": "cache",
        "display_name": "Кэш: максимум записей",
        "description": "Максимальное количество записей в in-memory кэше. При превышении используется LRU-вытеснение.",
        "default_value": "5000",
        "sort_order": 30,
    },
    {
        "key": "cache_default_ttl",
        "value_type": "int",
        "category": "performance",
        "subcategory": "cache",
        "display_name": "Кэш: TTL по умолчанию (сек)",
        "description": "Время жизни записей в кэше по умолчанию. Меньше = актуальнее данные, но больше запросов к БД.",
        "default_value": "300",
        "sort_order": 31,
    },
    {
        "key": "violation_drain_interval",
        "value_type": "float",
        "category": "performance",
        "subcategory": "violation_pipeline",
        "display_name": "Очередь нарушений: интервал обработки (сек)",
        "description": "Как часто worker забирает порцию пользователей из очереди. Меньше = быстрее реакция, но выше нагрузка.",
        "default_value": "3.0",
        "sort_order": 40,
    },
    {
        "key": "violation_chunk_size",
        "value_type": "int",
        "category": "performance",
        "subcategory": "violation_pipeline",
        "display_name": "Очередь нарушений: размер порции",
        "description": "Сколько пользователей обрабатывать за один цикл. Больше = быстрее разгребается очередь, но пиковая нагрузка выше.",
        "default_value": "200",
        "sort_order": 41,
    },
    {
        "key": "violation_max_background_tasks",
        "value_type": "int",
        "category": "performance",
        "subcategory": "violation_pipeline",
        "display_name": "Макс. фоновых задач (торренты и пр.)",
        "description": "Максимальное количество одновременных фоновых задач. При превышении новые задачи отбрасываются.",
        "default_value": "20",
        "sort_order": 42,
    },
]


class DynamicConfigService:
    """
    Сервис динамической конфигурации.
    Приоритет: БД > .env > default_value
    """

    def __init__(self):
        self._cache: Dict[str, ConfigItem] = {}
        self._initialized: bool = False
        self._auto_reload_task: Optional[asyncio.Task] = None
        self._auto_reload_interval: int = 30  # seconds

    async def initialize(self) -> bool:
        """
        Инициализация сервиса конфигурации.
        Создаёт предустановленные настройки в БД если их нет.
        Удаляет настройки, которых больше нет в DEFAULT_CONFIG_DEFINITIONS.
        """
        if not db_service.is_connected:
            logger.warning("Database not connected, config service running in .env-only mode")
            return False

        try:
            # Загружаем существующие настройки
            await self._load_all_from_db()

            # Добавляем предустановленные настройки если их нет
            await self._ensure_default_configs()

            # Удаляем настройки, которых больше нет в определениях
            await self._cleanup_stale_configs()

            self._initialized = True
            logger.info("✅ Dynamic config: %d settings loaded", len(self._cache))
            return True

        except Exception as e:
            logger.error("Failed to initialize config service: %s", e, exc_info=True)
            return False

    async def _load_all_from_db(self) -> None:
        """Загружает все настройки из БД в кэш."""
        if not db_service.is_connected:
            return

        try:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT key, value, value_type, category, subcategory,
                           display_name, description, default_value, env_var_name,
                           is_secret, is_readonly, validation_regex, options_json,
                           sort_order, created_at, updated_at
                    FROM bot_config
                    ORDER BY category, sort_order
                    """
                )

                for row in rows:
                    options = None
                    if row['options_json']:
                        try:
                            options = json.loads(row['options_json'])
                        except json.JSONDecodeError:
                            pass

                    item = ConfigItem(
                        key=row['key'],
                        value=row['value'],
                        value_type=ConfigValueType(row['value_type']),
                        category=ConfigCategory(row['category']) if row['category'] in [c.value for c in ConfigCategory] else ConfigCategory.GENERAL,
                        subcategory=row['subcategory'],
                        display_name=row['display_name'],
                        description=row['description'],
                        default_value=row['default_value'],
                        env_var_name=row['env_var_name'],
                        is_secret=row['is_secret'],
                        is_readonly=row['is_readonly'],
                        validation_regex=row['validation_regex'],
                        options=options,
                        sort_order=row['sort_order'],
                        created_at=row['created_at'],
                        updated_at=row['updated_at'],
                    )
                    self._cache[item.key] = item

        except Exception as e:
            logger.error("Failed to load config from DB: %s", e, exc_info=True)

    async def _ensure_default_configs(self) -> None:
        """Создаёт предустановленные настройки если их нет в БД."""
        if not db_service.is_connected:
            return

        for config_def in DEFAULT_CONFIG_DEFINITIONS:
            key = config_def['key']
            if key not in self._cache:
                await self._create_config(config_def)

    async def _create_config(self, config_def: Dict[str, Any]) -> None:
        """Создаёт новую настройку в БД."""
        try:
            async with db_service.acquire() as conn:
                options_json = None
                if config_def.get('options'):
                    options_json = json.dumps(config_def['options'])

                await conn.execute(
                    """
                    INSERT INTO bot_config (
                        key, value, value_type, category, subcategory,
                        display_name, description, default_value, env_var_name,
                        is_secret, is_readonly, validation_regex, options_json,
                        sort_order
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
                    ON CONFLICT (key) DO NOTHING
                    """,
                    config_def['key'],
                    config_def.get('value'),
                    config_def.get('value_type', 'string'),
                    config_def.get('category', 'general'),
                    config_def.get('subcategory'),
                    config_def.get('display_name'),
                    config_def.get('description'),
                    config_def.get('default_value'),
                    config_def.get('env_var_name'),
                    config_def.get('is_secret', False),
                    config_def.get('is_readonly', False),
                    config_def.get('validation_regex'),
                    options_json,
                    config_def.get('sort_order', 0),
                )

                # Добавляем в кэш
                options = config_def.get('options')
                item = ConfigItem(
                    key=config_def['key'],
                    value=config_def.get('value'),
                    value_type=ConfigValueType(config_def.get('value_type', 'string')),
                    category=ConfigCategory(config_def.get('category', 'general')),
                    subcategory=config_def.get('subcategory'),
                    display_name=config_def.get('display_name'),
                    description=config_def.get('description'),
                    default_value=config_def.get('default_value'),
                    env_var_name=config_def.get('env_var_name'),
                    is_secret=config_def.get('is_secret', False),
                    is_readonly=config_def.get('is_readonly', False),
                    validation_regex=config_def.get('validation_regex'),
                    options=options,
                    sort_order=config_def.get('sort_order', 0),
                )
                self._cache[item.key] = item

        except Exception as e:
            logger.error("Failed to create config %s: %s", config_def['key'], e, exc_info=True)

    async def _cleanup_stale_configs(self) -> None:
        """Удаляет из БД настройки, которых больше нет в DEFAULT_CONFIG_DEFINITIONS."""
        if not db_service.is_connected:
            return

        valid_keys = {d['key'] for d in DEFAULT_CONFIG_DEFINITIONS}
        stale_keys = [k for k in self._cache if k not in valid_keys]

        if not stale_keys:
            return

        try:
            async with db_service.acquire() as conn:
                await conn.execute(
                    "DELETE FROM bot_config WHERE key = ANY($1)",
                    stale_keys
                )
            for k in stale_keys:
                del self._cache[k]
            logger.info("Cleaned up %d stale config entries: %s", len(stale_keys), ", ".join(stale_keys))
        except Exception as e:
            logger.error("Failed to cleanup stale configs: %s", e, exc_info=True)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Получает значение настройки.
        Приоритет: БД > .env > default_value > default параметр
        """
        item = self._cache.get(key)

        if item:
            # 1. Если в БД есть явно установленное значение — оно главнее всего
            if item.value is not None:
                return item.get_typed_value()

            # 2. Проверяем .env как fallback
            if item.env_var_name:
                env_value = os.getenv(item.env_var_name)
                if env_value is not None and env_value != "":
                    temp_item = ConfigItem(
                        key=key,
                        value=env_value,
                        value_type=item.value_type,
                        category=item.category,
                    )
                    return temp_item.get_typed_value()

            # 3. default_value из определения
            if item.default_value is not None:
                return item._convert_value(item.default_value)

        return default

    def get_raw(self, key: str) -> Optional[ConfigItem]:
        """Получает ConfigItem напрямую."""
        return self._cache.get(key)

    async def set(self, key: str, value: Any) -> bool:
        """
        Устанавливает значение настройки в БД.
        БД значение имеет наивысший приоритет и перекрывает .env.
        """
        # Конвертируем значение в строку для хранения
        str_value = self._value_to_string(value)

        try:
            if db_service.is_connected:
                async with db_service.acquire() as conn:
                    await conn.execute(
                        """
                        UPDATE bot_config
                        SET value = $2, updated_at = NOW()
                        WHERE key = $1
                        """,
                        key, str_value
                    )

                # Обновляем кэш
                if key in self._cache:
                    self._cache[key].value = str_value
                    self._cache[key].updated_at = datetime.utcnow()

                return True

        except Exception as e:
            logger.error("Failed to set config %s: %s", key, e, exc_info=True)

        return False

    def _value_to_string(self, value: Any) -> str:
        """Конвертирует значение в строку для хранения."""
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)

    def get_by_category(self, category: Union[str, ConfigCategory]) -> List[ConfigItem]:
        """Получает все настройки категории."""
        if isinstance(category, ConfigCategory):
            category = category.value

        items = [
            item for item in self._cache.values()
            if item.category.value == category
        ]
        return sorted(items, key=lambda x: x.sort_order)

    def get_categories(self) -> List[str]:
        """Возвращает список всех категорий с настройками."""
        categories = set()
        for item in self._cache.values():
            categories.add(item.category.value)
        return sorted(categories)

    def get_all(self) -> Dict[str, ConfigItem]:
        """Возвращает все настройки."""
        return self._cache.copy()

    def get_effective_value(self, key: str) -> tuple[Any, str]:
        """
        Возвращает эффективное значение и его источник.
        Приоритет: БД > .env > default
        Returns: (value, source) где source: "db", "env", "default", "none"
        """
        item = self._cache.get(key)
        if not item:
            return (None, "unknown")

        # 1. БД значение — наивысший приоритет
        if item.value is not None:
            return (item.get_typed_value(), "db")

        # 2. .env как fallback
        if item.env_var_name:
            env_value = os.getenv(item.env_var_name)
            if env_value is not None and env_value != "":
                temp_item = ConfigItem(
                    key=key,
                    value=env_value,
                    value_type=item.value_type,
                    category=item.category,
                )
                return (temp_item.get_typed_value(), "env")

        # 3. Default
        if item.default_value is not None:
            return (item._convert_value(item.default_value), "default")

        return (None, "none")

    async def reset_to_default(self, key: str) -> bool:
        """Сбрасывает настройку к значению по умолчанию."""
        item = self._cache.get(key)
        if not item:
            return False

        return await self.set(key, None)

    def start_auto_reload(self, interval_seconds: int = 30) -> None:
        """Запускает фоновую задачу периодической перезагрузки конфигурации из БД."""
        self._auto_reload_interval = interval_seconds
        if self._auto_reload_task is not None:
            return
        self._auto_reload_task = asyncio.create_task(self._auto_reload_loop())
        logger.info("Config auto-reload started (every %ds)", interval_seconds)

    def stop_auto_reload(self) -> None:
        """Останавливает фоновую задачу перезагрузки конфигурации."""
        if self._auto_reload_task is not None:
            self._auto_reload_task.cancel()
            self._auto_reload_task = None
            logger.info("Config auto-reload stopped")

    async def _auto_reload_loop(self) -> None:
        """Периодически перезагружает настройки из БД."""
        while True:
            try:
                await asyncio.sleep(self._auto_reload_interval)
                await self._load_all_from_db()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Config auto-reload error: %s", e)

    async def reload(self) -> None:
        """Перезагружает все настройки из БД."""
        self._cache.clear()
        await self._load_all_from_db()
        logger.info("Config service reloaded, %d settings in cache", len(self._cache))


# Глобальный экземпляр сервиса
config_service = DynamicConfigService()
