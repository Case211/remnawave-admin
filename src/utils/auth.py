from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional, Set, Tuple

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from aiogram.utils.i18n import gettext as _

from src.config import get_settings
from src.utils.chat_context import set_current_chat_type
from src.utils.i18n import get_i18n
from shared.logger import log_button_click, log_command, log_user_input, logger
from shared.rbac import has_permission, get_scope, get_visible_user_uuids, get_admin_account_by_telegram_id


@dataclass
class BotAdmin:
    telegram_id: int
    account_id: Optional[int] = None
    username: str = ""
    role_id: Optional[int] = None
    role_name: Optional[str] = None
    has_bot_access: bool = False
    is_superadmin: bool = False
    unrestricted_user_access: bool = False
    max_users: Optional[int] = None
    max_traffic_gb: Optional[int] = None
    max_nodes: Optional[int] = None
    max_hosts: Optional[int] = None
    users_created: int = 0
    traffic_used_bytes: int = 0
    nodes_created: int = 0
    hosts_created: int = 0
    unlimited_traffic_policy: str = "allowed"
    _perms_sync: Set[Tuple[str, str]] = field(default_factory=set, repr=False, compare=False)

    def has_perm_sync(self, resource: str, action: str) -> bool:
        if self.is_superadmin:
            return True
        return (resource, action) in self._perms_sync

    async def has_permission(self, resource: str, action: str) -> bool:
        if self.is_superadmin:
            return True
        if self.role_id is None:
            return False
        return await has_permission(self.role_id, resource, action)

    async def get_scope(self, resource_type: str, action: str = "view") -> Optional[Set[str]]:
        return await get_scope(self.account_id, self.role_id, self.role_name, resource_type, action)

    async def get_visible_user_uuids(self) -> Optional[Set[str]]:
        return await get_visible_user_uuids(self.account_id, self.role_name)


async def _precompute_perms(admin: BotAdmin) -> None:
    if admin.is_superadmin or admin.role_id is None:
        return
    from shared.rbac import get_role_permission_set
    perms = await get_role_permission_set(admin.role_id)
    admin._perms_sync = perms


def _build_admin_from_account(user_id: int, account: dict, has_bot_access: Optional[bool] = None) -> BotAdmin:
    role_name = account.get("role_name")
    return BotAdmin(
        telegram_id=user_id,
        account_id=account.get("id"),
        username=account.get("username", ""),
        role_id=account.get("role_id"),
        role_name=role_name,
        has_bot_access=account.get("has_bot_access", False) if has_bot_access is None else has_bot_access,
        is_superadmin=role_name == "superadmin",
        unrestricted_user_access=account.get("unrestricted_user_access", False) or False,
        max_users=account.get("max_users"),
        max_traffic_gb=account.get("max_traffic_gb"),
        max_nodes=account.get("max_nodes"),
        max_hosts=account.get("max_hosts"),
        users_created=account.get("users_created", 0),
        traffic_used_bytes=account.get("traffic_used_bytes", 0),
        nodes_created=account.get("nodes_created", 0),
        hosts_created=account.get("hosts_created", 0),
        unlimited_traffic_policy=account.get("unlimited_traffic_policy", "allowed"),
    )


async def resolve_admin(user_id: int) -> Optional[BotAdmin]:
    settings = get_settings()
    allowed_admins = settings.allowed_admins

    if allowed_admins and user_id in allowed_admins:
        account = await get_admin_account_by_telegram_id(user_id)
        if account:
            admin = _build_admin_from_account(user_id, account, has_bot_access=True)
            if not admin.is_superadmin:
                await _precompute_perms(admin)
            return admin
        return BotAdmin(telegram_id=user_id, is_superadmin=True)

    account = await get_admin_account_by_telegram_id(user_id)
    if not account:
        return None
    if not account.get("has_bot_access", False):
        return None
    admin = _build_admin_from_account(user_id, account)
    if not admin.is_superadmin:
        await _precompute_perms(admin)
    return admin


class AdminMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user_id = None
        chat_type = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
            chat_type = event.chat.type if event.chat else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None
            if event.message is not None and getattr(event.message, "chat", None):
                chat_type = event.message.chat.type

        # Клавиатуры строятся без доступа к событию, а WebApp-кнопки
        # допустимы только в приватных чатах — см. utils/chat_context.
        set_current_chat_type(chat_type)

        if user_id is None:
            return await handler(event, data)

        admin = await resolve_admin(user_id)

        if admin is None:
            logger.warning("Unauthorized: user_id=%s event=%s", user_id, type(event).__name__)
            i18n = get_i18n()
            with i18n.use_locale(i18n.default_locale):
                error_text = _("errors.unauthorized")
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(error_text, show_alert=True)
                except Exception:
                    pass
            elif isinstance(event, Message):
                try:
                    await event.answer(error_text)
                except Exception:
                    pass
            return

        if not admin.is_superadmin and not admin.has_bot_access:
            logger.warning("No bot access: user_id=%s", user_id)
            i18n = get_i18n()
            with i18n.use_locale(i18n.default_locale):
                error_text = _("errors.no_bot_access")
            text = _("errors.no_bot_access_title") + "\n\n" + error_text
            if isinstance(event, CallbackQuery):
                try:
                    await event.answer(error_text, show_alert=True)
                except Exception:
                    pass
            elif isinstance(event, Message):
                try:
                    await event.answer(text)
                except Exception:
                    pass
            return

        data["admin"] = admin

        # Propagate admin identity to internal_api_client via ContextVar
        from shared.internal_api import _admin_ctx
        _admin_ctx.set({
            "username": admin.username,
            "account_id": admin.account_id,
        })

        if isinstance(event, CallbackQuery):
            username = event.from_user.username if event.from_user else None
            log_button_click(
                callback_data=event.data or "unknown",
                user_id=user_id,
                username=username,
            )
        elif isinstance(event, Message):
            username = event.from_user.username if event.from_user else None
            if event.text and event.text.startswith("/"):
                command_parts = event.text.split(maxsplit=1)
                command = command_parts[0]
                args = command_parts[1] if len(command_parts) > 1 else None
                log_command(
                    command=command,
                    user_id=user_id,
                    username=username,
                    args=args,
                )
            elif event.text:
                log_user_input(
                    field="text_input",
                    user_id=user_id,
                    username=username,
                    preview=event.text,
                )

        return await handler(event, data)
