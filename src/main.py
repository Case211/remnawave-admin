import asyncio

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeDefault
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import get_settings
from src.services.api_client import api_client
from src.utils.i18n import get_i18n_middleware
from src.utils.logger import logger
from src.handlers import register_handlers


async def main() -> None:
    settings = get_settings()

    # parse_mode is left as default (None) to avoid HTML parsing issues with plain text translations
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # middlewares
    dp.message.middleware(get_i18n_middleware())
    dp.callback_query.middleware(get_i18n_middleware())

    register_handlers(dp)
    dp.shutdown.register(api_client.close)

    # Set bot commands to enable the menu button (/start hint)
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Start working with the bot"),
            BotCommand(command="help", description="Help and commands"),
        ],
        scope=BotCommandScopeDefault(),
    )
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Начать работу с ботом"),
            BotCommand(command="help", description="Справка и команды"),
        ],
        scope=BotCommandScopeDefault(),
        language_code="ru",
    )
    await bot.set_chat_menu_button()

    logger.info("Starting bot")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
