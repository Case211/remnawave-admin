from src.config import get_settings


def is_admin(user_id: int) -> bool:
    settings = get_settings()
    return user_id in settings.allowed_admins if settings.allowed_admins else True
