"""Extended tests for web.backend.core.admin_credentials.

Covers: admin_exists, ensure_table, create_admin (async registration helpers).
"""
from unittest.mock import AsyncMock, patch

import pytest

from web.backend.core.admin_credentials import (
    admin_exists,
    ensure_table,
    create_admin,
)


# ── admin_exists ──────────────────────────────────────────────


class TestAdminExists:

    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, return_value=True)
    async def test_returns_true(self, mock_exists):
        result = await admin_exists()
        assert result is True
        mock_exists.assert_awaited_once()

    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, return_value=False)
    async def test_returns_false(self, mock_exists):
        result = await admin_exists()
        assert result is False

    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, side_effect=Exception("err"))
    async def test_returns_false_on_error(self, mock_exists):
        result = await admin_exists()
        assert result is False


# ── ensure_table ──────────────────────────────────────────────


class TestEnsureTable:

    @patch("web.backend.core.rbac.ensure_rbac_tables", new_callable=AsyncMock)
    async def test_delegates_to_rbac(self, mock_ensure):
        await ensure_table()
        mock_ensure.assert_awaited_once()

    @patch("web.backend.core.rbac.ensure_rbac_tables", new_callable=AsyncMock, side_effect=Exception("err"))
    async def test_handles_error(self, mock_ensure):
        await ensure_table()  # should not raise


# ── create_admin ──────────────────────────────────────────────


class TestCreateAdmin:

    @patch("web.backend.core.rbac.create_admin_account", new_callable=AsyncMock)
    @patch("web.backend.core.rbac.get_role_by_name", new_callable=AsyncMock)
    async def test_creates_admin_with_superadmin_role(self, mock_role, mock_create):
        mock_role.return_value = {"id": 1, "name": "superadmin"}
        mock_create.return_value = {"id": 1, "username": "admin"}

        result = await create_admin("admin", "SecureP@ss1")
        assert result is True
        mock_create.assert_awaited_once()
        # Verify role_id
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["role_id"] == 1

    @patch("web.backend.core.rbac.get_role_by_name", new_callable=AsyncMock, return_value=None)
    async def test_fails_when_superadmin_role_missing(self, mock_role):
        result = await create_admin("admin", "SecureP@ss1")
        assert result is False

    @patch("web.backend.core.rbac.create_admin_account", new_callable=AsyncMock, return_value=None)
    @patch("web.backend.core.rbac.get_role_by_name", new_callable=AsyncMock)
    async def test_fails_when_create_returns_none(self, mock_role, mock_create):
        mock_role.return_value = {"id": 1, "name": "superadmin"}
        result = await create_admin("admin", "P@ss1word")
        assert result is False

    @patch("web.backend.core.rbac.get_role_by_name", new_callable=AsyncMock, side_effect=Exception("err"))
    async def test_handles_exception(self, mock_role):
        result = await create_admin("admin", "P@ss1word")
        assert result is False

    @patch("web.backend.core.rbac.create_admin_account", new_callable=AsyncMock)
    @patch("web.backend.core.rbac.get_role_by_name", new_callable=AsyncMock)
    async def test_passes_is_generated_flag(self, mock_role, mock_create):
        mock_role.return_value = {"id": 1, "name": "superadmin"}
        mock_create.return_value = {"id": 1, "username": "admin"}

        await create_admin("admin", "P@ssw0rd!", is_generated=True)
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["is_generated_password"] is True

    @patch("web.backend.core.rbac.create_admin_account", new_callable=AsyncMock)
    @patch("web.backend.core.rbac.get_role_by_name", new_callable=AsyncMock)
    async def test_hashes_password(self, mock_role, mock_create):
        mock_role.return_value = {"id": 1, "name": "superadmin"}
        mock_create.return_value = {"id": 1}

        await create_admin("admin", "PlainText1!")
        call_kwargs = mock_create.call_args.kwargs
        # Password should be hashed (bcrypt format)
        assert call_kwargs["password_hash"].startswith("$2b$")
