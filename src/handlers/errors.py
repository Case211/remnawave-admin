from aiogram.types.error_event import ErrorEvent
from aiogram.utils.i18n import gettext as _

from src.utils.logger import logger


async def errors_handler(event: ErrorEvent) -> None:
    update = event.update
    exc = event.exception

    user_id = None
    payload = None
    try:
        if update.message:
            user_id = update.message.from_user.id if update.message.from_user else None
            payload = update.message.text
            await update.message.answer(_("errors.generic"))
        elif update.callback_query:
            user_id = update.callback_query.from_user.id if update.callback_query.from_user else None
            payload = update.callback_query.data
            await update.callback_query.answer(_("errors.generic"), show_alert=True)
    except Exception:
        # If replying fails, just log.
        pass

    safe_update = {}
    try:
        safe_update = update.model_dump(mode="json", exclude_none=True)
    except Exception:
        safe_update = {"repr": repr(update)}

    logger.exception(
        "Unhandled error while processing update",
        extra={"user_id": user_id, "payload": payload, "update": safe_update},
        exc_info=exc,
    )
