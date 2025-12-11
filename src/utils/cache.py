import time
from typing import Any, Callable, TypeVar
from collections import defaultdict

from src.config import get_settings
from src.utils.logger import logger

T = TypeVar("T")


class CacheEntry:
    """Запись в кэше с временем истечения."""

    def __init__(self, value: Any, ttl: float):
        self.value = value
        self.expires_at = time.time() + ttl
        self.created_at = time.time()

    def is_expired(self) -> bool:
        """Проверяет, истекла ли запись."""
        return time.time() > self.expires_at


class SimpleCache:
    """Простой in-memory кэш с TTL."""

    def __init__(self, default_ttl: float = 60.0):
        """
        Args:
            default_ttl: Время жизни кэша по умолчанию в секундах
        """
        self._cache: dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl
        self._hits = defaultdict(int)
        self._misses = defaultdict(int)

    def get(self, key: str) -> Any | None:
        """Получает значение из кэша."""
        entry = self._cache.get(key)
        if entry is None:
            self._misses[key] += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._misses[key] += 1
            logger.debug("Cache expired for key: %s", key)
            return None

        self._hits[key] += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """Устанавливает значение в кэш."""
        ttl = ttl or self.default_ttl
        self._cache[key] = CacheEntry(value, ttl)
        logger.debug("Cache set for key: %s (TTL: %s)", key, ttl)

    def delete(self, key: str) -> None:
        """Удаляет значение из кэша."""
        if key in self._cache:
            del self._cache[key]
            logger.debug("Cache deleted for key: %s", key)

    def clear(self, pattern: str | None = None) -> None:
        """
        Очищает кэш.
        
        Args:
            pattern: Если указан, удаляет только ключи, начинающиеся с pattern
        """
        if pattern:
            keys_to_delete = [k for k in self._cache.keys() if k.startswith(pattern)]
            for key in keys_to_delete:
                del self._cache[key]
            logger.debug("Cache cleared for pattern: %s (%d keys)", pattern, len(keys_to_delete))
        else:
            count = len(self._cache)
            self._cache.clear()
            logger.debug("Cache cleared completely (%d keys)", count)

    def invalidate(self, pattern: str) -> None:
        """Инвалидирует кэш по паттерну (алиас для clear)."""
        self.clear(pattern)

    def get_stats(self) -> dict[str, Any]:
        """Возвращает статистику использования кэша."""
        total_hits = sum(self._hits.values())
        total_misses = sum(self._misses.values())
        total_requests = total_hits + total_misses
        hit_rate = (total_hits / total_requests * 100) if total_requests > 0 else 0

        return {
            "entries": len(self._cache),
            "hits": total_hits,
            "misses": total_misses,
            "hit_rate": f"{hit_rate:.1f}%",
            "keys": list(self._cache.keys()),
        }

    async def get_or_set(
        self,
        key: str,
        fetch_func: Callable[[], Any],
        ttl: float | None = None,
    ) -> Any:
        """
        Получает значение из кэша или выполняет функцию и кэширует результат.
        
        Args:
            key: Ключ кэша
            fetch_func: Асинхронная функция для получения данных
            ttl: Время жизни кэша в секундах (опционально)
        
        Returns:
            Значение из кэша или результат fetch_func
        """
        cached = self.get(key)
        if cached is not None:
            return cached

        # Выполняем функцию и кэшируем результат
        value = await fetch_func()
        self.set(key, value, ttl)
        return value


# Глобальный экземпляр кэша
_cache_instance: SimpleCache | None = None


def get_cache() -> SimpleCache:
    """Получает глобальный экземпляр кэша."""
    global _cache_instance
    if _cache_instance is None:
        settings = get_settings()
        # Можно добавить CACHE_TTL в настройки, пока используем значения по умолчанию
        default_ttl = getattr(settings, "cache_ttl", 60.0)
        _cache_instance = SimpleCache(default_ttl=default_ttl)
    return _cache_instance


# Константы для ключей кэша
class CacheKeys:
    """Ключи для кэширования различных данных."""
    NODES = "nodes"
    NODES_REALTIME = "nodes:realtime"
    NODES_RANGE = "nodes:range"
    HOSTS = "hosts"
    STATS = "stats"
    STATS_PANEL = "stats:panel"
    STATS_SERVER = "stats:server"
    STATS_BANDWIDTH = "stats:bandwidth"
    HEALTH = "health"
    TOKENS = "tokens"
    TEMPLATES = "templates"
    SNIPPETS = "snippets"
    CONFIGS = "configs"
    BILLING = "billing"
    BILLING_NODES = "billing:nodes"
    PROVIDERS = "providers"
