"""
HTTP client for Bedolaga Bot Web API.

Provides async methods for communicating with the Bedolaga bot's
built-in admin API. Used by both the sync service (periodic data fetch)
and the web backend (real-time proxy endpoints).

Authentication: X-API-Key header with a token configured in Bedolaga.
"""

import asyncio
import logging
import time
from typing import Any, Optional

import httpx
from httpx import HTTPStatusError

logger = logging.getLogger(__name__)


# ── Exceptions ────────────────────────────────────────────────────

class BedolagaClientError(Exception):
    def __init__(self, message: str = "", code: str = "ERR_BEDOLAGA_000"):
        self.message = message
        self.code = code
        super().__init__(message)


class BedolagaNotFoundError(BedolagaClientError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, "ERR_BEDOLAGA_404")


class BedolagaUnauthorizedError(BedolagaClientError):
    def __init__(self, message: str = "Unauthorized"):
        super().__init__(message, "ERR_BEDOLAGA_401")


class BedolagaNetworkError(BedolagaClientError):
    def __init__(self, message: str = "Network error"):
        super().__init__(message, "ERR_BEDOLAGA_NET")


class BedolagaTimeoutError(BedolagaClientError):
    def __init__(self, message: str = "Request timeout"):
        super().__init__(message, "ERR_BEDOLAGA_TIMEOUT")


class BedolagaServerError(BedolagaClientError):
    def __init__(self, message: str = "Server error"):
        super().__init__(message, "ERR_BEDOLAGA_500")


# ── Client ────────────────────────────────────────────────────────

class BedolagaApiClient:
    """Async HTTP client for Bedolaga Bot Web API."""

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None
        self._base_url: Optional[str] = None
        self._api_key: Optional[str] = None
        self._configured = False

    def configure(self, base_url: str, api_key: str) -> None:
        """Configure the client with Bedolaga API credentials."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._configured = True
        # Close existing client so it gets recreated with new config
        if self._client and not self._client.is_closed:
            asyncio.get_event_loop().create_task(self._client.aclose())
            self._client = None
        logger.info("Bedolaga API client configured: %s", self._base_url)

    @property
    def is_configured(self) -> bool:
        return self._configured and bool(self._base_url) and bool(self._api_key)

    def _create_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers={"X-API-Key": self._api_key},
            timeout=timeout,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            follow_redirects=True,
        )

    async def _ensure_client(self) -> httpx.AsyncClient:
        if not self._configured:
            raise BedolagaClientError("Bedolaga API client not configured", "ERR_BEDOLAGA_NOCONF")
        if self._client is None or self._client.is_closed:
            self._client = self._create_client()
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    # ── HTTP primitives ───────────────────────────────────────────

    async def _request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json: Optional[Any] = None,
        max_retries: int = 3,
    ) -> dict:
        last_exc = None
        start = time.time()

        for attempt in range(max_retries):
            try:
                client = await self._ensure_client()
                response = await client.request(method, url, params=params, json=json)
                duration_ms = (time.time() - start) * 1000
                response.raise_for_status()
                logger.debug(
                    "Bedolaga %s %s -> %d (%.0fms)",
                    method, url, response.status_code, duration_ms,
                )
                return response.json()

            except HTTPStatusError as exc:
                status = exc.response.status_code
                if status in (401, 403):
                    raise BedolagaUnauthorizedError(f"Access denied: {status}") from exc
                if status == 404:
                    raise BedolagaNotFoundError(f"Not found: {url}") from exc
                if status >= 500:
                    last_exc = exc
                    if attempt < max_retries - 1:
                        delay = 0.5 * (2 ** attempt)
                        logger.warning(
                            "Bedolaga %s %s -> %d, retry %d/%d in %.1fs",
                            method, url, status, attempt + 1, max_retries, delay,
                        )
                        await asyncio.sleep(delay)
                        continue
                    raise BedolagaServerError(f"Server error {status} on {url}") from exc
                raise BedolagaClientError(f"HTTP {status} on {url}") from exc

            except httpx.TimeoutException as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    delay = 0.5 * (2 ** attempt)
                    logger.warning(
                        "Bedolaga %s %s timeout, retry %d/%d in %.1fs",
                        method, url, attempt + 1, max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise BedolagaTimeoutError(f"Timeout on {url}") from exc

            except (httpx.ConnectError, httpx.NetworkError, OSError) as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    delay = 1.0 * (2 ** attempt)
                    logger.warning(
                        "Bedolaga %s %s network error, retry %d/%d in %.1fs",
                        method, url, attempt + 1, max_retries, delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise BedolagaNetworkError(f"Network error on {url}") from exc

        raise BedolagaNetworkError(f"Failed after {max_retries} attempts: {url}") from last_exc

    async def _get(self, url: str, params: Optional[dict] = None, **kw) -> dict:
        return await self._request("GET", url, params=params, **kw)

    async def _post(self, url: str, json: Optional[Any] = None, **kw) -> dict:
        return await self._request("POST", url, json=json, **kw)

    async def _patch(self, url: str, json: Optional[Any] = None, **kw) -> dict:
        return await self._request("PATCH", url, json=json, **kw)

    async def _put(self, url: str, json: Optional[Any] = None, **kw) -> dict:
        return await self._request("PUT", url, json=json, **kw)

    async def _delete(self, url: str, **kw) -> dict:
        return await self._request("DELETE", url, **kw)

    # ── Health & Stats (sync targets) ─────────────────────────────

    async def get_health(self) -> dict:
        return await self._get("/health")

    async def get_stats_overview(self) -> dict:
        return await self._get("/stats/overview")

    async def get_stats_full(self) -> dict:
        return await self._get("/stats/full")

    # ── Users (sync target) ───────────────────────────────────────

    async def get_users(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        search: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if search:
            params["search"] = search
        return await self._get("/users", params=params)

    async def get_user(self, user_id: int) -> dict:
        return await self._get(f"/users/{user_id}")

    async def get_user_by_telegram_id(self, telegram_id: int) -> dict:
        return await self._get(f"/users/by-telegram-id/{telegram_id}")

    # ── Subscriptions (sync target) ───────────────────────────────

    async def get_subscriptions(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        user_id: Optional[int] = None,
        is_trial: Optional[bool] = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if user_id is not None:
            params["user_id"] = user_id
        if is_trial is not None:
            params["is_trial"] = is_trial
        return await self._get("/subscriptions", params=params)

    async def get_subscription(self, subscription_id: int) -> dict:
        return await self._get(f"/subscriptions/{subscription_id}")

    async def extend_subscription(self, subscription_id: int, days: int) -> dict:
        return await self._post(f"/subscriptions/{subscription_id}/extend", json={"days": days})

    async def add_subscription_traffic(self, subscription_id: int, traffic_gb: float) -> dict:
        return await self._post(
            f"/subscriptions/{subscription_id}/traffic",
            json={"traffic_gb": traffic_gb},
        )

    async def add_subscription_devices(self, subscription_id: int, devices: int) -> dict:
        return await self._post(
            f"/subscriptions/{subscription_id}/devices",
            json={"devices": devices},
        )

    # ── Transactions (sync target) ────────────────────────────────

    async def get_transactions(
        self,
        limit: int = 100,
        offset: int = 0,
        user_id: Optional[int] = None,
        type: Optional[str] = None,
        payment_method: Optional[str] = None,
        is_completed: Optional[bool] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id is not None:
            params["user_id"] = user_id
        if type:
            params["type"] = type
        if payment_method:
            params["payment_method"] = payment_method
        if is_completed is not None:
            params["is_completed"] = is_completed
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to
        return await self._get("/transactions", params=params)

    # ── Tickets (real-time proxy) ─────────────────────────────────

    async def get_tickets(
        self,
        limit: int = 50,
        offset: int = 0,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        user_id: Optional[int] = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        if priority:
            params["priority"] = priority
        if user_id is not None:
            params["user_id"] = user_id
        return await self._get("/tickets", params=params)

    async def get_ticket(self, ticket_id: int) -> dict:
        return await self._get(f"/tickets/{ticket_id}")

    async def update_ticket_status(self, ticket_id: int, status: str) -> dict:
        return await self._post(f"/tickets/{ticket_id}/status", json={"status": status})

    async def update_ticket_priority(self, ticket_id: int, priority: str) -> dict:
        return await self._post(f"/tickets/{ticket_id}/priority", json={"priority": priority})

    async def reply_to_ticket(self, ticket_id: int, text: str) -> dict:
        return await self._post(f"/tickets/{ticket_id}/reply", json={"text": text})

    async def block_ticket_replies(self, ticket_id: int, reason: Optional[str] = None) -> dict:
        body = {"reason": reason} if reason else {}
        return await self._post(f"/tickets/{ticket_id}/reply-block", json=body)

    async def unblock_ticket_replies(self, ticket_id: int) -> dict:
        return await self._delete(f"/tickets/{ticket_id}/reply-block")

    # ── Promo Groups (real-time proxy) ────────────────────────────

    async def get_promo_groups(self, limit: int = 100, offset: int = 0) -> dict:
        return await self._get("/promo-groups", params={"limit": limit, "offset": offset})

    async def get_promo_group(self, group_id: int) -> dict:
        return await self._get(f"/promo-groups/{group_id}")

    async def create_promo_group(self, data: dict) -> dict:
        return await self._post("/promo-groups", json=data)

    async def update_promo_group(self, group_id: int, data: dict) -> dict:
        return await self._patch(f"/promo-groups/{group_id}", json=data)

    async def delete_promo_group(self, group_id: int) -> dict:
        return await self._delete(f"/promo-groups/{group_id}")

    # ── Promo Offers (real-time proxy) ────────────────────────────

    async def get_promo_offers(
        self,
        limit: int = 100,
        offset: int = 0,
        user_id: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if user_id is not None:
            params["user_id"] = user_id
        if is_active is not None:
            params["is_active"] = is_active
        return await self._get("/promo-offers", params=params)

    async def get_promo_offer(self, offer_id: int) -> dict:
        return await self._get(f"/promo-offers/{offer_id}")

    async def create_promo_offer(self, data: dict) -> dict:
        return await self._post("/promo-offers", json=data)

    async def get_promo_offer_templates(self) -> dict:
        return await self._get("/promo-offers/templates")

    async def get_promo_offer_logs(
        self, limit: int = 100, offset: int = 0, **filters
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset, **filters}
        return await self._get("/promo-offers/logs", params=params)

    # ── Promo Codes (real-time proxy) ─────────────────────────────

    async def get_promo_codes(
        self, limit: int = 100, offset: int = 0, is_active: Optional[bool] = None
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if is_active is not None:
            params["is_active"] = is_active
        return await self._get("/promo-codes", params=params)

    async def get_promo_code(self, promocode_id: int) -> dict:
        return await self._get(f"/promo-codes/{promocode_id}")

    async def create_promo_code(self, data: dict) -> dict:
        return await self._post("/promo-codes", json=data)

    async def update_promo_code(self, promocode_id: int, data: dict) -> dict:
        return await self._patch(f"/promo-codes/{promocode_id}", json=data)

    async def delete_promo_code(self, promocode_id: int) -> dict:
        return await self._delete(f"/promo-codes/{promocode_id}")

    # ── Polls (real-time proxy) ───────────────────────────────────

    async def get_polls(self, limit: int = 100, offset: int = 0) -> dict:
        return await self._get("/polls", params={"limit": limit, "offset": offset})

    async def get_poll(self, poll_id: int) -> dict:
        return await self._get(f"/polls/{poll_id}")

    async def create_poll(self, data: dict) -> dict:
        return await self._post("/polls", json=data)

    async def delete_poll(self, poll_id: int) -> dict:
        return await self._delete(f"/polls/{poll_id}")

    async def get_poll_stats(self, poll_id: int) -> dict:
        return await self._get(f"/polls/{poll_id}/stats")

    async def get_poll_responses(
        self, poll_id: int, limit: int = 100, offset: int = 0
    ) -> dict:
        return await self._get(
            f"/polls/{poll_id}/responses",
            params={"limit": limit, "offset": offset},
        )

    # ── Partners / Referrals (real-time proxy) ────────────────────

    async def get_partners(
        self, limit: int = 100, offset: int = 0, search: Optional[str] = None
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if search:
            params["search"] = search
        return await self._get("/partners/referrers", params=params)

    async def get_partner(self, user_id: int, limit: int = 50, offset: int = 0) -> dict:
        return await self._get(
            f"/partners/referrers/{user_id}",
            params={"limit": limit, "offset": offset},
        )

    async def get_partner_stats(self, days: int = 30) -> dict:
        return await self._get("/partners/stats", params={"days": days})

    # ── Broadcasts (real-time proxy) ──────────────────────────────

    async def get_broadcasts(self, limit: int = 50, offset: int = 0) -> dict:
        return await self._get("/broadcasts", params={"limit": limit, "offset": offset})

    async def create_broadcast(self, data: dict) -> dict:
        return await self._post("/broadcasts", json=data)

    async def stop_broadcast(self, broadcast_id: int) -> dict:
        return await self._post(f"/broadcasts/{broadcast_id}/stop")

    # ── Settings (real-time proxy) ────────────────────────────────

    async def get_settings(self) -> dict:
        return await self._get("/settings")

    async def get_setting_categories(self) -> dict:
        return await self._get("/settings/categories")

    async def update_setting(self, key: str, value: Any) -> dict:
        return await self._put(f"/settings/{key}", json={"value": value})

    # ── Logs (real-time proxy) ────────────────────────────────────

    async def get_monitoring_logs(
        self, limit: int = 100, offset: int = 0, event_type: Optional[str] = None
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if event_type:
            params["event_type"] = event_type
        return await self._get("/logs/monitoring", params=params)

    async def get_support_logs(
        self, limit: int = 100, offset: int = 0, action: Optional[str] = None
    ) -> dict:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if action:
            params["action"] = action
        return await self._get("/logs/support", params=params)


# Global instance
bedolaga_client = BedolagaApiClient()
