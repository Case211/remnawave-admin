"""Глобальное состояние бота для хранения данных между запросами."""

# Словарь для хранения ожидаемого ввода от пользователей
# Ключ: user_id, Значение: dict с информацией о текущем действии
PENDING_INPUT: dict[int, dict] = {}

# Словарь для хранения ID последних сообщений бота в каждом чате
# Ключ: chat_id, Значение: message_id
LAST_BOT_MESSAGES: dict[int, int] = {}

# Словарь для хранения контекста поиска пользователей
# Ключ: user_id, Значение: dict с query и results
USER_SEARCH_CONTEXT: dict[int, dict] = {}

# Словарь для хранения целевого меню для возврата из детального просмотра пользователя
# Ключ: user_id, Значение: NavTarget строка
USER_DETAIL_BACK_TARGET: dict[int, str] = {}

# Словарь для хранения текущей страницы подписок для каждого пользователя
# Ключ: user_id, Значение: номер страницы (int)
SUBS_PAGE_BY_USER: dict[int, int] = {}

# Константы
ADMIN_COMMAND_DELETE_DELAY = 2.0
SEARCH_PAGE_SIZE = 100
MAX_SEARCH_RESULTS = 10
SUBS_PAGE_SIZE = 8

