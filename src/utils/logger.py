import logging
from src.config import get_settings


def setup_logger() -> logging.Logger:
    settings = get_settings()
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    # Align aiogram logger level with our settings.
    logging.getLogger("aiogram").setLevel(level)
    return logging.getLogger("remnawave-admin-bot")


logger = setup_logger()
