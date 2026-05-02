"""Re-export `shared.push_service` для обратной совместимости.

Реальная реализация переехала в shared/, чтобы её мог использовать и web-backend,
и бот (бот ловит часть событий от Panel-webhook напрямую и тоже должен пушить).
Этот файл оставлен пока тонкой ре-экспортной заглушкой — старые импорты не сломаются.
"""
from shared.push_service import (  # noqa: F401
    broadcast_to_admins,
    is_enabled,
    send_to_admin,
)
