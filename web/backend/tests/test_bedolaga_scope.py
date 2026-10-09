"""Разделы Bedolaga — только админу без ограничения видимости юзеров.

Клиенты, платежи и тикеты Bedolaga с юзерами панели связаны разве что по
Telegram ID, под скоуп их не отфильтровать: ограниченный админ видел бы всех.
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from web.backend.api.deps import require_permission

from .conftest import make_admin

PERMS = {("bedolaga_customers", "view"), ("bedolaga_support", "view"), ("users", "view")}


def _visible(value):
    return patch("web.backend.core.rbac.get_visible_user_uuids", new_callable=AsyncMock, return_value=value)


@pytest.mark.asyncio
async def test_scoped_admin_is_refused_bedolaga():
    admin = make_admin("operator", "reseller", account_id=3, permissions=PERMS)
    with _visible({"user-a"}):
        for resource in ("bedolaga_customers", "bedolaga_support"):
            with pytest.raises(HTTPException) as exc:
                await require_permission(resource, "view")(admin)
            assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_scoped_admin_keeps_other_sections():
    admin = make_admin("operator", "reseller", account_id=3, permissions=PERMS)
    with _visible({"user-a"}):
        assert await require_permission("users", "view")(admin) is admin


@pytest.mark.asyncio
async def test_unrestricted_admin_gets_bedolaga():
    admin = make_admin("operator", "operator", account_id=3, permissions=PERMS)
    with _visible(None):
        assert await require_permission("bedolaga_customers", "view")(admin) is admin


@pytest.mark.asyncio
async def test_superadmin_is_never_restricted():
    admin = make_admin("superadmin")
    with _visible({"user-a"}) as visible:
        assert await require_permission("bedolaga_customers", "view")(admin) is admin
    visible.assert_not_awaited()


@pytest.mark.asyncio
async def test_me_tells_the_frontend(app, operator_client):
    with _visible({"user-a"}), \
            patch("web.backend.core.rbac.get_admin_account_by_id", new_callable=AsyncMock, return_value=None):
        resp = await operator_client.get("/api/v2/auth/me")
    assert resp.status_code == 200, resp.text
    assert resp.json()["user_scope_restricted"] is True
