import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage

from src.config import get_settings
from src.services.api_client import api_client
from src.utils.auth import AdminMiddleware
from src.utils.i18n import get_i18n_middleware
from src.utils.logger import logger
from src.handlers import register_handlers


async def check_api_connection() -> bool:
    """Проверяет подключение к API с повторными попытками."""
    from src.config import get_settings
    settings = get_settings()
    max_attempts = 5
    delay = 3  # секунды между попытками
    
    api_url = str(settings.api_base_url).rstrip("/")
    logger.info("🔍 Checking API connection to: %s", api_url)
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("Attempting connection... (attempt %d/%d)", attempt, max_attempts)
            await api_client.get_health()
            logger.info("✅ API connection successful")
            return True
        except Exception as exc:
            error_msg = str(exc)
            error_type = type(exc).__name__
            logger.warning(
                "❌ API connection failed (attempt %d/%d) [%s]: %s",
                attempt, max_attempts, error_type, error_msg
            )
            if attempt < max_attempts:
                logger.info("⏳ Retrying in %d seconds...", delay)
                await asyncio.sleep(delay)
            else:
                logger.error("❌ All connection attempts failed")
                logger.error(
                    "💡 Troubleshooting tips:\n"
                    "  1. Check that API_BASE_URL is correct (should be http://remnawave:3000 for Docker)\n"
                    "  2. Verify that both containers are in the same Docker network (remnawave-network)\n"
                    "  3. Ensure the API container (remnawave) is running and healthy\n"
                    "  4. Check API_TOKEN is set correctly in .env file"
                )
                return False
    
    return False


async def main() -> None:
    import os
    # Логируем сырое значение переменной окружения для отладки
    raw_admins_env = os.getenv("ADMINS", "NOT_SET")
    logger.info("🔍 DEBUG: Raw ADMINS env var: %s", repr(raw_admins_env))
    
    settings = get_settings()
    
    # Логируем загруженных администраторов для отладки
    logger.info(
        "🔐 Loaded admin configuration: admins=%s allowed_admins=%s",
        settings.admins,
        settings.allowed_admins,
    )
    if not settings.allowed_admins:
        logger.warning(
            "⚠️ WARNING: No administrators configured! "
            "Set ADMINS environment variable with comma-separated user IDs (e.g., ADMINS=123456789,987654321)"
        )
    
    # Логируем настройки уведомлений
    raw_chat_id = os.getenv("NOTIFICATIONS_CHAT_ID", "NOT_SET")
    raw_topic_id = os.getenv("NOTIFICATIONS_TOPIC_ID", "NOT_SET")
    logger.info(
        "📢 Notifications config: raw_chat_id=%s raw_topic_id=%s parsed_chat_id=%s parsed_topic_id=%s",
        repr(raw_chat_id),
        repr(raw_topic_id),
        settings.notifications_chat_id,
        settings.notifications_topic_id,
    )
    if settings.notifications_chat_id:
        logger.info(
            "📢 Notifications enabled: chat_id=%s topic_id=%s",
            settings.notifications_chat_id,
            settings.notifications_topic_id,
        )
    else:
        logger.warning("📢 Notifications disabled: NOTIFICATIONS_CHAT_ID not set or invalid")

    # Проверяем подключение к API перед стартом
    if not await check_api_connection():
        logger.error(
            "🚨 Cannot start bot: API is unavailable. " 
            "Please check API_BASE_URL and API_TOKEN in your .env file. "
            "Make sure the API server is running and accessible."
        )
        sys.exit(1)

    # parse_mode is left as default (None) to avoid HTML parsing issues with plain text translations
    bot = Bot(token=settings.bot_token)
    dp = Dispatcher(storage=MemoryStorage())

    # middlewares
    # Сначала проверка администратора (блокирует неавторизованных пользователей)
    dp.message.middleware(AdminMiddleware())
    dp.callback_query.middleware(AdminMiddleware())
    # Затем i18n middleware (для локализации)
    dp.message.middleware(get_i18n_middleware())
    dp.callback_query.middleware(get_i18n_middleware())

    register_handlers(dp)
    dp.shutdown.register(api_client.close)

    logger.info("Starting bot")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
