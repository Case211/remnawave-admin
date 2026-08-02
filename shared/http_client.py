"""Shared HTTP transport layer with retry, timeout and error handling.

Provides BaseHttpClient that both RemnawaveApiClient (shared/api_client.py)
and BaseInternalApiClient (shared/internal_api.py) inherit from.
Eliminates transport-layer code duplication while keeping each client's
routing, auth, and API-method surface separate.
"""
import asyncio
import time

import httpx
from httpx import HTTPStatusError

from shared.exceptions import (
    ApiClientError,
    NetworkError,
    NotFoundError,
    RateLimitError,
    ServerError,
    TimeoutError,
    UnauthorizedError,
    ValidationError,
)
from shared.logger import logger, log_api_call, log_api_error


class BaseHttpClient:
    """Base HTTP client with retry, exponential backoff, and error mapping.

    Subclasses provide their own __init__ that calls super() with the
    appropriate base_url, prefix, and headers.  They may also override
    _extra_headers() to inject per-request context headers.
    """

    def __init__(self, base_url: str, prefix: str, headers: dict[str, str]) -> None:
        self._base_url = base_url.rstrip("/")
        self._prefix = prefix
        self._headers = headers
        self._client = self._create_client()

    # ── Transport plumbing ──────────────────────────────────────

    def _create_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(connect=15.0, read=60.0, write=15.0, pool=10.0)
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=self._headers,
            timeout=timeout,
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
            follow_redirects=True,
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            logger.warning("HTTP client was closed, recreating")
            self._client = self._create_client()
        return self._client

    def _extra_headers(self) -> dict[str, str]:
        """Override in subclasses to inject per-request headers."""
        return {}

    # ── Core request with retry ─────────────────────────────────

    async def _request(
        self,
        method: str,
        path: str,
        json: dict | None = None,
        params: dict | None = None,
        max_retries: int = 3,
        timeout: httpx.Timeout | None = None,
    ) -> dict:
        """Execute an HTTP request with retry and error mapping."""
        last_exc = None
        start_time = time.time()
        full_path = f"{self._prefix}{path}"
        extra_headers = self._extra_headers()

        for attempt in range(max_retries):
            try:
                client = await self._ensure_client()
                response = await client.request(
                    method, full_path,
                    json=json, params=params,
                    headers=extra_headers or None,
                    timeout=timeout,
                )
                duration_ms = (time.time() - start_time) * 1000
                response.raise_for_status()
                log_api_call(method, path, status_code=response.status_code, duration_ms=duration_ms)
                if not response.content:
                    return {}
                return response.json()

            except HTTPStatusError as exc:
                log_api_error(method, path, exc, status_code=exc.response.status_code)
                status = exc.response.status_code
                if status in (401, 403):
                    raise UnauthorizedError(f"Access denied: {status}") from exc
                if status == 404:
                    raise NotFoundError(f"Resource not found: {path}") from exc
                if status == 429:
                    raise RateLimitError(f"Rate limit exceeded on {path}") from exc
                if status in (400, 422):
                    try:
                        error_data = exc.response.json()
                        msg = error_data.get("detail") or error_data.get("message", str(exc))
                        field = error_data.get("field", "")
                        raise ValidationError(str(msg), field=field) from exc
                    except (ValueError, KeyError):
                        raise ValidationError(f"Validation error on {path}") from exc
                if status >= 500:
                    # Remnawave шлёт бизнес-ошибки (напр. невалидный конфиг) с 500
                    # и телом {message, errorCode} — доносим текст, не глотаем
                    msg = f"Server error {status} on {path}"
                    try:
                        error_data = exc.response.json()
                        panel_msg = error_data.get("message") or error_data.get("detail")
                        if panel_msg:
                            code = error_data.get("errorCode")
                            msg = str(panel_msg) + (f" [{code}]" if code else "")
                    except ValueError:
                        pass
                    raise ServerError(msg, status_code=status) from exc
                raise ApiClientError(f"API error {status}", code=f"ERR_API_{status}") from exc

            except httpx.ReadTimeout as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    delay = 0.5 * (2 ** attempt)
                    logger.debug("⏳ Timeout %s %s (%d/%d), retry in %.1fs", method, path, attempt + 1, max_retries, delay)
                    await asyncio.sleep(delay)
                else:
                    log_api_error(method, path, exc)
                    raise TimeoutError(f"Request timeout on {path}") from exc

            except (httpx.RemoteProtocolError, httpx.ConnectError) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    delay = 0.5 * (2 ** attempt)
                    logger.debug("⏳ Network error %s %s (%d/%d), retry in %.1fs", method, path, attempt + 1, max_retries, delay)
                    await asyncio.sleep(delay)
                else:
                    log_api_error(method, path, exc)
                    raise NetworkError(f"Connection failed to {path}") from exc

            except RuntimeError as exc:
                last_exc = exc
                try:
                    if self._client is not None and not self._client.is_closed:
                        await self._client.aclose()
                except Exception as close_exc:
                    logger.debug("Error closing HTTP client on RuntimeError: %s", close_exc)
                self._client = self._create_client()
                if attempt < max_retries - 1:
                    delay = 0.5 * (2 ** attempt)
                    logger.debug("⏳ Client closed %s %s (%d/%d), recreated, retry in %.1fs", method, path, attempt + 1, max_retries, delay)
                    await asyncio.sleep(delay)
                else:
                    log_api_error(method, path, exc)
                    raise NetworkError(f"Client was closed for {path}") from exc

            except httpx.HTTPError as exc:
                raise ApiClientError(f"HTTP error: {type(exc).__name__}", code="ERR_HTTP_001") from exc

        raise NetworkError(f"Failed to connect to {path} after {max_retries} attempts") from last_exc

    # ── Public request ──────────────────────────────────────────

    async def request(self, method: str, path: str, **kwargs) -> dict:
        """Public wrapper around _request."""
        return await self._request(method, path, **kwargs)

    # ── HTTP verb helpers ───────────────────────────────────────

    async def _get(self, path: str, **kwargs) -> dict:
        return await self._request("GET", path, **kwargs)

    async def _post(self, path: str, **kwargs) -> dict:
        return await self._request("POST", path, **kwargs)

    async def _patch(self, path: str, **kwargs) -> dict:
        return await self._request("PATCH", path, **kwargs)

    async def _delete(self, path: str, **kwargs) -> dict:
        return await self._request("DELETE", path, **kwargs)

    # ── Lifecycle ────────────────────────────────────────────────

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
