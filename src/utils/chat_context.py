"""Тип чата текущего апдейта — для клавиатур, которые строятся без Message.

Клавиатуры бота собираются в чистых функциях (src/keyboards/*), у которых нет
доступа к событию. Обычно это не мешает, но WebApp-кнопки Telegram принимает
ТОЛЬКО в приватных чатах: попади такая кнопка в сообщение для группы —
отклоняется всё сообщение целиком (BUTTON_TYPE_INVALID), и меню бота
перестаёт открываться. Поэтому AdminMiddleware кладёт тип чата в contextvar,
а клавиатура спрашивает его перед добавлением кнопки.
"""
from contextvars import ContextVar

_current_chat_type: ContextVar[str | None] = ContextVar(
    "rw_current_chat_type", default=None
)


def set_current_chat_type(chat_type: str | None) -> None:
    """Запомнить тип чата обрабатываемого апдейта."""
    _current_chat_type.set(chat_type)


def is_private_chat() -> bool:
    """Обрабатывается ли сейчас апдейт из приватного чата."""
    return _current_chat_type.get() == "private"
