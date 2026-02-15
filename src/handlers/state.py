"""Глобальное состояние бота для хранения данных между запросами."""
import asyncio
import time


class TTLDict:
    """Dictionary with per-entry TTL (time-to-live) and maximum size limit.

    Entries expire automatically after ``ttl`` seconds.  Expired entries are
    cleaned lazily on every read/write access and can also be purged explicitly
    via :meth:`cleanup`.  When *max_size* is reached the oldest entry is evicted
    before inserting a new one.
    """

    def __init__(self, ttl: int = 3600, max_size: int = 5000):
        self._data: dict = {}          # key -> value
        self._timestamps: dict = {}    # key -> float (time.monotonic)
        self.ttl = ttl
        self.max_size = max_size

    # --- internal helpers ---------------------------------------------------

    def _is_expired(self, key) -> bool:
        ts = self._timestamps.get(key)
        if ts is None:
            return True
        return (time.monotonic() - ts) > self.ttl

    def _evict_expired(self):
        """Remove all expired keys."""
        now = time.monotonic()
        expired = [k for k, ts in self._timestamps.items() if (now - ts) > self.ttl]
        for k in expired:
            self._data.pop(k, None)
            self._timestamps.pop(k, None)

    def _evict_oldest(self):
        """Remove the oldest entry to make room for a new one."""
        if self._timestamps:
            oldest_key = min(self._timestamps, key=self._timestamps.get)
            self._data.pop(oldest_key, None)
            self._timestamps.pop(oldest_key, None)

    # --- public dict-like interface -----------------------------------------

    def __setitem__(self, key, value):
        self._evict_expired()
        if key not in self._data and len(self._data) >= self.max_size:
            self._evict_oldest()
        self._data[key] = value
        self._timestamps[key] = time.monotonic()

    def __getitem__(self, key):
        if key in self._timestamps and not self._is_expired(key):
            return self._data[key]
        # Clean up the expired key if it exists
        self._data.pop(key, None)
        self._timestamps.pop(key, None)
        raise KeyError(key)

    def __contains__(self, key) -> bool:
        if key in self._timestamps and not self._is_expired(key):
            return True
        # Clean up the expired key if it exists
        self._data.pop(key, None)
        self._timestamps.pop(key, None)
        return False

    def __delitem__(self, key):
        if key in self._data:
            del self._data[key]
            self._timestamps.pop(key, None)
        else:
            raise KeyError(key)

    def __len__(self) -> int:
        self._evict_expired()
        return len(self._data)

    def get(self, key, default=None):
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key, *args):
        """Remove and return value for *key*.  Accepts an optional default."""
        if key in self._timestamps and not self._is_expired(key):
            self._timestamps.pop(key, None)
            return self._data.pop(key)
        # Clean up expired key if present
        self._data.pop(key, None)
        self._timestamps.pop(key, None)
        if args:
            return args[0]
        raise KeyError(key)

    def keys(self):
        self._evict_expired()
        return self._data.keys()

    def values(self):
        self._evict_expired()
        return self._data.values()

    def items(self):
        self._evict_expired()
        return self._data.items()

    def cleanup(self):
        """Explicitly purge all expired entries."""
        self._evict_expired()

    def __repr__(self):
        self._evict_expired()
        return f"TTLDict(ttl={self.ttl}, max_size={self.max_size}, len={len(self._data)})"


# ---------------------------------------------------------------------------
# Global state dictionaries
# ---------------------------------------------------------------------------

# Словарь для хранения ожидаемого ввода от пользователей
# Ключ: user_id, Значение: dict с информацией о текущем действии
PENDING_INPUT: TTLDict = TTLDict(ttl=3600, max_size=5000)

# Кэш для статистики
# Ключ: cache_key (str), Значение: dict с полями "data" и "timestamp"
STATS_CACHE: dict[str, dict] = {}

# Время жизни кэша статистики в секундах
STATS_CACHE_TTL = 45  # 45 секунд

# Словарь для хранения ID последних сообщений бота в каждом чате
# Ключ: chat_id, Значение: message_id
LAST_BOT_MESSAGES: TTLDict = TTLDict(ttl=7200, max_size=10000)

# Словарь для хранения контекста поиска пользователей
# Ключ: user_id, Значение: dict с query и results
USER_SEARCH_CONTEXT: TTLDict = TTLDict(ttl=3600, max_size=5000)

# Словарь для хранения целевого меню для возврата из детального просмотра пользователя
# Ключ: user_id, Значение: NavTarget строка
USER_DETAIL_BACK_TARGET: TTLDict = TTLDict(ttl=3600, max_size=5000)

# История навигации для каждого пользователя
# Ключ: user_id, Значение: список NavTarget строк (стек навигации)
NAVIGATION_HISTORY: TTLDict = TTLDict(ttl=3600, max_size=5000)

# Максимальная глубина истории навигации
MAX_NAVIGATION_HISTORY = 10

# Словарь для хранения текущей страницы подписок для каждого пользователя
# Ключ: user_id, Значение: номер страницы (int)
SUBS_PAGE_BY_USER: TTLDict = TTLDict(ttl=1800, max_size=5000)

# Словарь для хранения текущей страницы нод для каждого пользователя
# Ключ: user_id, Значение: номер страницы (int)
NODES_PAGE_BY_USER: TTLDict = TTLDict(ttl=1800, max_size=5000)

# Словарь для хранения текущей страницы хостов для каждого пользователя
# Ключ: user_id, Значение: номер страницы (int)
HOSTS_PAGE_BY_USER: TTLDict = TTLDict(ttl=1800, max_size=5000)

# Словарь для хранения активных фильтров для пользователей
# Ключ: user_id, Значение: строка фильтра (ACTIVE, DISABLED, LIMITED, EXPIRED) или None
SUBS_FILTER_BY_USER: TTLDict = TTLDict(ttl=1800, max_size=5000)

# Словарь для хранения активных фильтров для нод
# Ключ: user_id, Значение: dict с полями "status" (ONLINE, OFFLINE, ENABLED, DISABLED) и "tag" (строка) или None
NODES_FILTER_BY_USER: TTLDict = TTLDict(ttl=1800, max_size=5000)

# Словарь для хранения активных фильтров для хостов
# Ключ: user_id, Значение: строка фильтра (ENABLED, DISABLED) или None
HOSTS_FILTER_BY_USER: TTLDict = TTLDict(ttl=1800, max_size=5000)

# Lock for thread-safe access to LAST_BOT_MESSAGES
LAST_BOT_MESSAGES_LOCK = asyncio.Lock()

# Set for tracking background asyncio tasks so they are not garbage-collected
BACKGROUND_TASKS: set = set()

# Константы
ADMIN_COMMAND_DELETE_DELAY = 2.0
SEARCH_PAGE_SIZE = 100
MAX_SEARCH_RESULTS = 10
SUBS_PAGE_SIZE = 8
NODES_PAGE_SIZE = 10
HOSTS_PAGE_SIZE = 10

# Константы для фильтров
SUBS_FILTER_OPTIONS = ["ACTIVE", "DISABLED", "LIMITED", "EXPIRED"]
NODES_STATUS_FILTER_OPTIONS = ["ONLINE", "OFFLINE", "ENABLED", "DISABLED"]
HOSTS_FILTER_OPTIONS = ["ENABLED", "DISABLED"]


async def cleanup_stale_state():
    """Clean up expired entries from all state dictionaries."""
    for d in [PENDING_INPUT, USER_SEARCH_CONTEXT, USER_DETAIL_BACK_TARGET,
              NAVIGATION_HISTORY, SUBS_PAGE_BY_USER, NODES_PAGE_BY_USER,
              HOSTS_PAGE_BY_USER, SUBS_FILTER_BY_USER, NODES_FILTER_BY_USER,
              HOSTS_FILTER_BY_USER, LAST_BOT_MESSAGES]:
        if hasattr(d, 'cleanup'):
            d.cleanup()
