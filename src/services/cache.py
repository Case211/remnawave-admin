"""Модуль кэширования для API запросов.

Обеспечивает кэширование данных с настраиваемым TTL для снижения
нагрузки на API и ускорения отклика бота.
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from src.utils.logger import logger


@dataclass
class CacheEntry:
    """Запись в кэше с данными и временем истечения."""
    data: Any
    expires_at: float
    created_at: float = field(default_factory=time.time)
    
    def is_expired(self) -> bool:
        """Проверяет, истек ли срок действия записи."""
        return time.time() > self.expires_at
    
    def time_remaining(self) -> float:
        """Возвращает оставшееся время жизни записи в секундах."""
        return max(0, self.expires_at - time.time())


class CacheManager:
    """Менеджер кэширования с поддержкой TTL и инвалидации.
    
    Attributes:
        DEFAULT_TTL: TTL по умолчанию в секундах
        STATS_TTL: TTL для статистики (часто обновляемые данные)
        NODES_TTL: TTL для списка нод
        HOSTS_TTL: TTL для списка хостов
        CONFIG_PROFILES_TTL: TTL для профилей конфигурации (редко меняются)
    """
    
    # TTL в секундах для разных типов данных
    DEFAULT_TTL = 30
    STATS_TTL = 45           # Статистика - обновляется каждые 45 сек
    NODES_TTL = 30           # Ноды - 30 сек
    HOSTS_TTL = 30           # Хосты - 30 сек
    CONFIG_PROFILES_TTL = 60 # Профили конфигов - 60 сек (редко меняются)
    HEALTH_TTL = 15          # Здоровье системы - 15 сек (важно актуальное состояние)
    PROVIDERS_TTL = 60       # Провайдеры - 60 сек
    TEMPLATES_TTL = 60       # Шаблоны - 60 сек
    TOKENS_TTL = 30          # Токены - 30 сек
    
    def __init__(self):
        self._cache: dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
        self._stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }
    
    async def get(self, key: str) -> Any | None:
        """Получает значение из кэша.
        
        Args:
            key: Ключ кэша
            
        Returns:
            Закэшированные данные или None если отсутствует/истек
        """
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._stats["misses"] += 1
                return None
            
            if entry.is_expired():
                del self._cache[key]
                self._stats["misses"] += 1
                logger.debug("Cache expired for key: %s", key)
                return None
            
            self._stats["hits"] += 1
            logger.debug("Cache hit for key: %s (%.1fs remaining)", key, entry.time_remaining())
            return entry.data
    
    async def set(self, key: str, data: Any, ttl: float | None = None) -> None:
        """Сохраняет значение в кэш.
        
        Args:
            key: Ключ кэша
            data: Данные для кэширования
            ttl: Время жизни в секундах (если None, используется DEFAULT_TTL)
        """
        if ttl is None:
            ttl = self.DEFAULT_TTL
            
        async with self._lock:
            self._cache[key] = CacheEntry(
                data=data,
                expires_at=time.time() + ttl,
            )
            logger.debug("Cache set for key: %s (TTL: %.1fs)", key, ttl)
    
    async def invalidate(self, key: str) -> bool:
        """Инвалидирует (удаляет) запись из кэша.
        
        Args:
            key: Ключ кэша для инвалидации
            
        Returns:
            True если запись была удалена, False если не существовала
        """
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats["invalidations"] += 1
                logger.debug("Cache invalidated for key: %s", key)
                return True
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Инвалидирует все записи, ключи которых начинаются с pattern.
        
        Args:
            pattern: Префикс ключей для инвалидации
            
        Returns:
            Количество инвалидированных записей
        """
        async with self._lock:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
            if keys_to_delete:
                self._stats["invalidations"] += len(keys_to_delete)
                logger.debug("Cache invalidated %d keys matching pattern: %s", len(keys_to_delete), pattern)
            return len(keys_to_delete)
    
    async def invalidate_all(self) -> int:
        """Очищает весь кэш.
        
        Returns:
            Количество удаленных записей
        """
        async with self._lock:
            count = len(self._cache)
            self._cache.clear()
            if count:
                self._stats["invalidations"] += count
                logger.debug("Cache cleared: %d entries removed", count)
            return count
    
    async def cleanup_expired(self) -> int:
        """Удаляет все истекшие записи из кэша.
        
        Returns:
            Количество удаленных записей
        """
        async with self._lock:
            expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.debug("Cache cleanup: %d expired entries removed", len(expired_keys))
            return len(expired_keys)
    
    def get_stats(self) -> dict:
        """Возвращает статистику использования кэша."""
        total = self._stats["hits"] + self._stats["misses"]
        hit_rate = (self._stats["hits"] / total * 100) if total > 0 else 0
        return {
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{hit_rate:.1f}%",
            "invalidations": self._stats["invalidations"],
            "entries": len(self._cache),
        }


# Ключи кэша
class CacheKeys:
    """Константы ключей кэша для различных API эндпоинтов."""
    
    STATS = "stats"
    HEALTH = "health"
    BANDWIDTH_STATS = "bandwidth_stats"
    NODES = "nodes"
    HOSTS = "hosts"
    CONFIG_PROFILES = "config_profiles"
    PROVIDERS = "providers"
    TEMPLATES = "templates"
    TOKENS = "tokens"
    SNIPPETS = "snippets"
    BILLING_HISTORY = "billing_history"
    BILLING_NODES = "billing_nodes"
    INTERNAL_SQUADS = "internal_squads"
    EXTERNAL_SQUADS = "external_squads"
    
    @staticmethod
    def node(uuid: str) -> str:
        """Ключ для конкретной ноды."""
        return f"node:{uuid}"
    
    @staticmethod
    def host(uuid: str) -> str:
        """Ключ для конкретного хоста."""
        return f"host:{uuid}"
    
    @staticmethod
    def user(uuid: str) -> str:
        """Ключ для конкретного пользователя."""
        return f"user:{uuid}"


# Глобальный экземпляр кэша
cache = CacheManager()
