from aiogram import Dispatcher

from src.handlers.basic import router as basic_router
from src.handlers.billing import router as billing_router
from src.handlers.bot_config import router as bot_config_router
from src.handlers.bulk import router as bulk_router
from src.handlers.commands import router as commands_router
from src.handlers.errors import errors_handler
from src.handlers.filters import router as filters_router
from src.handlers.hosts import router as hosts_router
from src.handlers.navigation import router as navigation_router
from src.handlers.nodes import router as nodes_router
from src.handlers.resources import router as resources_router
from src.handlers.system import router as system_router
from src.handlers.users import router as users_router


def register_handlers(dp: Dispatcher) -> None:
    # Регистрируем роутеры в порядке приоритета
    # Сначала общие роутеры (commands, navigation), затем доменные
    dp.include_router(commands_router)
    dp.include_router(navigation_router)
    dp.include_router(filters_router)
    dp.include_router(users_router)
    dp.include_router(nodes_router)
    dp.include_router(hosts_router)
    dp.include_router(resources_router)
    dp.include_router(billing_router)
    dp.include_router(bulk_router)
    dp.include_router(system_router)
    dp.include_router(bot_config_router)
    # Старый basic_router оставляем для обратной совместимости (временно)
    dp.include_router(basic_router)
    dp.errors.register(errors_handler)
