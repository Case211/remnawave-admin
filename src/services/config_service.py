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

from src.services.database import db_service
from src.utils.logger import logger


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
        "description": "Уровень детализации логов (требует перезапуск)",
        "default_value": "INFO",
        "env_var_name": "LOG_LEVEL",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "sort_order": 2,
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
        """
        if not db_service.is_connected:
            logger.warning("Database not connected, config service running in .env-only mode")
            return False

        try:
            # Загружаем существующие настройки
            await self._load_all_from_db()

            # Добавляем предустановленные настройки если их нет
            await self._ensure_default_configs()

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
