"""Regression test for PR #255: an admin with a NULL role_name must not crash.

``AdminInfo.role`` is a required ``str``; a roleless admin's LEFT JOIN returns
``role_name=NULL``. The previous ``account.get("role_name", "admin")`` only fell
back when the key was *absent*, so a present-but-``None`` value slipped through
and later raised ``ValidationError`` on ``/api/v2/auth/me``. The resolvers now use
``account.get("role_name") or "admin"``.
"""
from unittest.mock import AsyncMock, patch

from web.backend.api.deps import _resolve_password_admin, _resolve_telegram_admin


def _account(**over):
    base = {
        "id": 7,
        "username": "noroles",
        "telegram_id": None,
        "role_id": None,  # no role assigned → role_name is NULL via LEFT JOIN
        "role_name": None,
        "is_active": True,
        "unrestricted_user_access": False,
    }
    base.update(over)
    return base


class _Settings:
    admin_login = None


async def test_password_admin_null_role_falls_back_to_admin():
    with patch(
        "web.backend.core.rbac.get_admin_account_by_username",
        new=AsyncMock(return_value=_account()),
    ):
        user = await _resolve_password_admin("noroles", _Settings())
    assert user.role == "admin"
    assert user.role_id is None
    assert user.username == "noroles"


async def test_telegram_admin_null_role_falls_back_to_admin():
    with patch(
        "web.backend.core.rbac.get_admin_account_by_telegram_id",
        new=AsyncMock(return_value=_account(telegram_id=555)),
    ):
        user = await _resolve_telegram_admin("555", {}, _Settings())
    assert user.role == "admin"


async def test_explicit_role_name_is_preserved():
    with patch(
        "web.backend.core.rbac.get_admin_account_by_username",
        new=AsyncMock(return_value=_account(role_id=2, role_name="viewer")),
    ), patch(
        "web.backend.core.rbac.get_all_permissions_for_role_id",
        new=AsyncMock(return_value=set()),
    ):
        user = await _resolve_password_admin("viewer_user", _Settings())
    assert user.role == "viewer"
    assert user.role_id == 2
