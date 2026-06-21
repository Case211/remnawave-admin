"""HttpOnly cookie-based JWT delivery.

Веб-фронт получает токены в HttpOnly cookies (XSS не может их украсть),
мобильное приложение и API-клиенты продолжают использовать Bearer-токены
из тела ответа — оба механизма работают параллельно.

CSRF-защита: double-submit cookie. Вместе с auth-cookies ставится
читаемая JS cookie rw_csrf; фронт обязан слать её значение в заголовке
X-CSRF-Token на каждом мутирующем запросе, аутентифицированном cookie.
Bearer-аутентификация CSRF-проверки не требует (заголовок нельзя
подделать кросс-сайтово).
"""
import hmac
import secrets

from fastapi import Request, Response

from web.backend.core.security import get_access_ttl_minutes, get_refresh_ttl_hours

ACCESS_COOKIE = "rw_access"
REFRESH_COOKIE = "rw_refresh"
CSRF_COOKIE = "rw_csrf"
CSRF_HEADER = "x-csrf-token"

# Refresh-cookie отдаётся браузером только на auth-эндпоинты
# (refresh/logout) — сужает поверхность утечки.
AUTH_COOKIE_PATH = "/api/v2/auth"


def _is_secure(request: Request) -> bool:
    """Secure-флаг: https напрямую или за reverse-proxy (X-Forwarded-Proto)."""
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto", "").lower() == "https"


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_auth_cookies(
    response: Response,
    request: Request,
    access_token: str,
    refresh_token: str,
) -> None:
    """Set HttpOnly auth cookies + readable CSRF cookie."""
    secure = _is_secure(request)
    access_max_age = get_access_ttl_minutes() * 60
    refresh_max_age = get_refresh_ttl_hours() * 3600

    response.set_cookie(
        ACCESS_COOKIE,
        access_token,
        max_age=access_max_age,
        httponly=True,
        secure=secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        refresh_token,
        max_age=refresh_max_age,
        httponly=True,
        secure=secure,
        samesite="strict",
        path=AUTH_COOKIE_PATH,
    )
    # CSRF-cookie живёт столько же, сколько refresh — переживает ротацию access
    response.set_cookie(
        CSRF_COOKIE,
        generate_csrf_token(),
        max_age=refresh_max_age,
        httponly=False,  # фронт читает её и шлёт в X-CSRF-Token
        secure=secure,
        samesite="lax",
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    """Delete auth cookies (logout)."""
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=AUTH_COOKIE_PATH)
    response.delete_cookie(CSRF_COOKIE, path="/")


def csrf_check_passed(request: Request) -> bool:
    """Double-submit проверка для cookie-аутентифицированных мутаций.

    Безопасные методы (GET/HEAD/OPTIONS) не проверяются.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return True
    cookie_value = request.cookies.get(CSRF_COOKIE, "")
    header_value = request.headers.get(CSRF_HEADER, "")
    if not cookie_value or not header_value:
        return False
    return hmac.compare_digest(cookie_value, header_value)
