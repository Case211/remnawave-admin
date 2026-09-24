"""API-ключи: не дают больше прав, чем у создателя; гаснут вместе с ним."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from web.backend.api.v2 import api_keys


def _admin(role="operator", perms=(), account_id=7):
    admin = MagicMock()
    admin.account_id = account_id
    admin.role = role
    admin.has_permission = lambda r, a: (r, a) in perms
    return admin


@pytest.mark.asyncio
async def test_scope_beyond_own_rights_is_refused():
    admin = _admin(perms={("users", "view")})
    with patch("web.backend.core.rbac.get_visible_user_uuids", AsyncMock(return_value=None)):
        await api_keys._check_scopes_allowed(admin, ["users:read"])
        with pytest.raises(HTTPException) as e:
            await api_keys._check_scopes_allowed(admin, ["users:delete"])
    assert e.value.status_code == 403


@pytest.mark.asyncio
async def test_user_scopes_need_unrestricted_visibility():
    admin = _admin(perms={("users", "view")})
    with patch("web.backend.core.rbac.get_visible_user_uuids", AsyncMock(return_value={"u1"})):
        with pytest.raises(HTTPException):
            await api_keys._check_scopes_allowed(admin, ["users:read"])


@pytest.mark.asyncio
async def test_superadmin_may_grant_everything():
    with patch("web.backend.core.rbac.get_visible_user_uuids", AsyncMock(return_value=None)):
        await api_keys._check_scopes_allowed(_admin(role="superadmin"), list(api_keys.AVAILABLE_SCOPES))


def test_expiry_in_the_past_is_refused():
    with pytest.raises(HTTPException):
        api_keys._parse_expiry((datetime.now(timezone.utc) - timedelta(days=1)).isoformat())
    assert api_keys._parse_expiry((datetime.now(timezone.utc) + timedelta(days=1)).isoformat())


@pytest.mark.asyncio
async def test_key_of_disabled_owner_does_not_work():
    from web.backend.core import api_key_auth
    row = {"id": 1, "name": "k", "scopes": ["users:read"], "is_active": True, "expires_at": None,
           "created_by_admin_id": 7, "owner_id": 7, "owner_active": False}
    conn = MagicMock()
    conn.fetchrow = AsyncMock(return_value=row)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock(is_connected=True)
    db.acquire.return_value = cm
    with patch("shared.database.db_service", db):
        assert await api_key_auth.validate_api_key("rwa_x") is None
        row["owner_active"] = True
        assert (await api_key_auth.validate_api_key("rwa_x"))["id"] == 1
