"""Tests for HttpOnly cookie authentication (core/auth_cookies.py + deps)."""
import pytest
from unittest.mock import patch, AsyncMock

from web.backend.api.deps import AdminUser
from web.backend.core.security import create_access_token, create_refresh_token
from web.backend.core.auth_cookies import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    CSRF_COOKIE,
    csrf_check_passed,
)


def _make_admin(username: str = "cookieadmin") -> AdminUser:
    return AdminUser(
        telegram_id=None,
        username=username,
        role="superadmin",
        role_id=1,
        auth_method="password",
        account_id=1,
        permissions=set(),
    )


def _set_cookie_headers(resp) -> str:
    return "\n".join(resp.headers.get_list("set-cookie"))


class FakeRequest:
    """Minimal request stub for csrf_check_passed."""

    def __init__(self, method="POST", cookies=None, headers=None):
        self.method = method
        self.cookies = cookies or {}
        self.headers = headers or {}


class TestCsrfCheck:
    def test_safe_methods_skip_check(self):
        for method in ("GET", "HEAD", "OPTIONS"):
            assert csrf_check_passed(FakeRequest(method=method))

    def test_post_without_header_fails(self):
        req = FakeRequest(cookies={CSRF_COOKIE: "abc"})
        assert not csrf_check_passed(req)

    def test_post_without_cookie_fails(self):
        req = FakeRequest(headers={"x-csrf-token": "abc"})
        assert not csrf_check_passed(req)

    def test_post_mismatch_fails(self):
        req = FakeRequest(
            cookies={CSRF_COOKIE: "abc"},
            headers={"x-csrf-token": "xyz"},
        )
        assert not csrf_check_passed(req)

    def test_post_match_passes(self):
        req = FakeRequest(
            cookies={CSRF_COOKIE: "abc"},
            headers={"x-csrf-token": "abc"},
        )
        assert csrf_check_passed(req)


class TestLoginSetsCookies:
    """POST /api/v2/auth/login выдаёт HttpOnly cookies."""

    @pytest.mark.asyncio
    @patch("web.backend.api.v2.auth.verify_admin_password_async", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.core.rbac.admin_account_exists", new_callable=AsyncMock, return_value=True)
    @patch("web.backend.api.v2.auth.login_guard")
    @patch("web.backend.api.v2.auth.notify_login_success", new_callable=AsyncMock)
    async def test_login_sets_auth_cookies(
        self, mock_notify, mock_guard, mock_exists, mock_verify, anon_client
    ):
        mock_guard.is_locked.return_value = False
        resp = await anon_client.post(
            "/api/v2/auth/login",
            json={"username": "admin", "password": "TestP@ss1"},
        )
        assert resp.status_code == 200

        headers = resp.headers.get_list("set-cookie")
        access = next((h for h in headers if h.startswith(f"{ACCESS_COOKIE}=")), None)
        refresh = next((h for h in headers if h.startswith(f"{REFRESH_COOKIE}=")), None)
        csrf = next((h for h in headers if h.startswith(f"{CSRF_COOKIE}=")), None)

        assert access and "HttpOnly" in access
        assert refresh and "HttpOnly" in refresh
        # refresh-cookie уходит только на auth-эндпоинты
        assert "Path=/api/v2/auth" in refresh
        # CSRF-cookie должна читаться из JS — без HttpOnly
        assert csrf and "HttpOnly" not in csrf
        # Тело по-прежнему содержит токены (мобильное приложение)
        data = resp.json()
        assert data["access_token"]
        assert data["refresh_token"]


class TestCookieAuthentication:
    """Аутентификация по cookie rw_access (dual auth в get_current_admin)."""

    @pytest.mark.asyncio
    async def test_get_with_cookie(self, anon_client):
        token = create_access_token("pwd:cookie_get", "cookie_get", auth_method="password")
        anon_client.cookies.set(ACCESS_COOKIE, token)
        with patch(
            "web.backend.api.deps._validate_token_payload",
            new_callable=AsyncMock,
            return_value=_make_admin("cookie_get"),
        ):
            resp = await anon_client.get("/api/v2/auth/me")
        assert resp.status_code == 200
        assert resp.json()["username"] == "cookie_get"

    @pytest.mark.asyncio
    async def test_mutating_without_csrf_rejected(self, anon_client):
        token = create_access_token("pwd:cookie_nocsrf", "cookie_nocsrf", auth_method="password")
        anon_client.cookies.set(ACCESS_COOKIE, token)
        with patch(
            "web.backend.api.deps._validate_token_payload",
            new_callable=AsyncMock,
            return_value=_make_admin("cookie_nocsrf"),
        ):
            resp = await anon_client.post("/api/v2/auth/logout")
        assert resp.status_code == 403
        assert "CSRF" in resp.text

    @pytest.mark.asyncio
    async def test_mutating_with_csrf_passes(self, anon_client):
        token = create_access_token("pwd:cookie_csrf", "cookie_csrf", auth_method="password")
        anon_client.cookies.set(ACCESS_COOKIE, token)
        anon_client.cookies.set(CSRF_COOKIE, "csrf-test-value")
        with patch(
            "web.backend.api.deps._validate_token_payload",
            new_callable=AsyncMock,
            return_value=_make_admin("cookie_csrf"),
        ):
            resp = await anon_client.post(
                "/api/v2/auth/logout",
                headers={"X-CSRF-Token": "csrf-test-value"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_bearer_does_not_require_csrf(self, anon_client):
        token = create_access_token("pwd:bearer_user", "bearer_user", auth_method="password")
        with patch(
            "web.backend.api.deps._validate_token_payload",
            new_callable=AsyncMock,
            return_value=_make_admin("bearer_user"),
        ):
            resp = await anon_client.post(
                "/api/v2/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            )
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_no_auth_at_all_is_401(self, anon_client):
        resp = await anon_client.get("/api/v2/auth/me")
        assert resp.status_code == 401


class TestRefreshFromCookie:
    """POST /api/v2/auth/refresh без тела — refresh из cookie."""

    @pytest.mark.asyncio
    @patch(
        "web.backend.core.rbac.get_admin_account_by_username",
        new_callable=AsyncMock,
        return_value={"id": 1, "username": "cookie_refresh", "is_active": True, "role_id": 1},
    )
    async def test_refresh_via_cookie(self, mock_account, anon_client):
        refresh = create_refresh_token("pwd:cookie_refresh")
        anon_client.cookies.set(REFRESH_COOKIE, refresh)
        resp = await anon_client.post("/api/v2/auth/refresh")
        assert resp.status_code == 200
        data = resp.json()
        assert data["access_token"]
        assert data["refresh_token"]
        # Новые cookies выставлены при ротации
        headers = _set_cookie_headers(resp)
        assert f"{ACCESS_COOKIE}=" in headers
        assert f"{REFRESH_COOKIE}=" in headers

    @pytest.mark.asyncio
    async def test_refresh_without_anything_is_401(self, anon_client):
        resp = await anon_client.post("/api/v2/auth/refresh")
        assert resp.status_code == 401


class TestLogoutClearsCookies:
    @pytest.mark.asyncio
    async def test_logout_clears_cookies(self, anon_client):
        token = create_access_token("pwd:cookie_logout", "cookie_logout", auth_method="password")
        anon_client.cookies.set(ACCESS_COOKIE, token)
        anon_client.cookies.set(CSRF_COOKIE, "csrf-logout")
        with patch(
            "web.backend.api.deps._validate_token_payload",
            new_callable=AsyncMock,
            return_value=_make_admin("cookie_logout"),
        ):
            resp = await anon_client.post(
                "/api/v2/auth/logout",
                headers={"X-CSRF-Token": "csrf-logout"},
            )
        assert resp.status_code == 200
        headers = _set_cookie_headers(resp)
        # Cookie сброшены (Max-Age=0 / expires в прошлом)
        assert f'{ACCESS_COOKIE}=""' in headers
        assert f'{REFRESH_COOKIE}=""' in headers
