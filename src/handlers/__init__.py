from aiogram import Dispatcher

from src.handlers.basic import router as basic_router
from src.handlers.errors import errors_handler


def register_handlers(dp: Dispatcher) -> None:
    dp.include_router(basic_router)
    dp.errors.register(errors_handler)
