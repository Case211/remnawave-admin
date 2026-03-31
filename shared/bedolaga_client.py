"""HTTP client for Bedolaga Bot API."""
import json
import logging
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class BedolagaClient:
    """Client for Bedolaga Bot REST API."""

    def __init__(self):
        self._base_url: Optional[str] = None
        self._api_token: Optional[str] = None
        self._client: Optional[httpx.AsyncClient] = None

    def configure(self, base_url: str, api_token: str):
        """Configure the client with URL and token."""
        self._base_url = base_url.rstrip("/")
        self._api_token = api_token
        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._api_token)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self._base_url,
                headers={"X-API-Key": self._api_token},
                timeout=httpx.Timeout(15.0),
            )
        return self._client

    # ── Base methods ──

    @staticmethod
    def _parse_json(response: httpx.Response) -> dict:
        """Parse JSON from response, returning {} on empty body."""
        body = response.text
        if not body or not body.strip():
            logger.warning(
                "Bedolaga API returned empty response (status=%s, url=%s)",
                response.status_code, response.url,
            )
            return {}
        try:
            return response.json()
        except json.JSONDecodeError:
            preview = body[:300]
            raise ValueError(
                f"Bedolaga API returned non-JSON response "
                f"(status={response.status_code}, url={response.url}): {preview}"
            )

    async def _get(self, path: str, params: dict = None) -> dict:
        client = self._get_client()
        response = await client.get(path, params=params)
        response.raise_for_status()
        return self._parse_json(response)

    async def _post(self, path: str, json: dict = None, params: dict = None) -> dict:
        client = self._get_client()
        response = await client.post(path, json=json, params=params)
        response.raise_for_status()
        return self._parse_json(response)

    async def _patch(self, path: str, json: dict = None) -> dict:
        client = self._get_client()
        response = await client.patch(path, json=json)
        response.raise_for_status()
        return self._parse_json(response)

    async def _delete(self, path: str, params: dict = None) -> dict:
        client = self._get_client()
        response = await client.delete(path, params=params)
        response.raise_for_status()
        return self._parse_json(response)

    # ── Stats ──

    async def get_overview(self) -> dict:
        return await self._get("/stats/overview")

    async def get_full_stats(self) -> dict:
        return await self._get("/stats/full")

    async def get_health(self) -> dict:
        return await self._get("/health")

    # ── Users ──

    async def list_users(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/users", params=params)

    async def get_user(self, user_id: int) -> dict:
        return await self._get(f"/users/{user_id}")

    async def get_user_by_telegram(self, telegram_id: int) -> dict:
        return await self._get(f"/users/by-telegram-id/{telegram_id}")

    async def update_user(self, user_id: int, data: dict) -> dict:
        return await self._patch(f"/users/{user_id}", json=data)

    async def modify_balance(self, user_id: int, data: dict) -> dict:
        return await self._post(f"/users/{user_id}/balance", json=data)

    # ── Subscriptions ──

    async def list_subscriptions(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/subscriptions", params=params)

    async def get_subscription(self, sub_id: int) -> dict:
        return await self._get(f"/subscriptions/{sub_id}")

    async def create_subscription(self, user_id: int, data: dict) -> dict:
        return await self._post(f"/users/{user_id}/subscription", json=data)

    async def deactivate_subscription(self, user_id: int) -> dict:
        return await self._delete(f"/users/{user_id}/subscription")

    async def extend_subscription(self, sub_id: int, data: dict) -> dict:
        return await self._post(f"/subscriptions/{sub_id}/extend", json=data)

    async def add_traffic(self, sub_id: int, data: dict) -> dict:
        return await self._post(f"/subscriptions/{sub_id}/traffic", json=data)

    async def add_devices(self, sub_id: int, data: dict) -> dict:
        return await self._post(f"/subscriptions/{sub_id}/devices", json=data)

    async def reset_devices(self, sub_id: int) -> dict:
        return await self._post(f"/subscriptions/{sub_id}/reset-devices")

    # ── Referrals ──

    async def get_all_users(self, limit: int = 200, offset: int = 0) -> dict:
        """Fetch all users for referral network building."""
        return await self._get("/users", params={"limit": limit, "offset": offset})

    # ── Transactions ──

    async def list_transactions(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/transactions", params=params)

    # ── Subscription Events ──

    async def list_subscription_events(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/subscription-events", params=params)

    # ── Promo codes ──

    async def list_promos(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/promo-codes", params=params)

    async def get_promo(self, promo_id: int) -> dict:
        """Get promo detail with usage stats (total_uses, today_uses, recent_uses)."""
        return await self._get(f"/promo-codes/{promo_id}")

    async def create_promo(self, data: dict) -> dict:
        return await self._post("/promo-codes", json=data)

    async def update_promo(self, promo_id: int, data: dict) -> dict:
        return await self._patch(f"/promo-codes/{promo_id}", json=data)

    async def delete_promo(self, promo_id: int) -> dict:
        return await self._delete(f"/promo-codes/{promo_id}")

    async def get_promo_stats(self, promo_id: int) -> dict:
        """Detail endpoint already includes stats (total_uses, today_uses, recent_uses)."""
        return await self._get(f"/promo-codes/{promo_id}")

    # ── Marketing campaigns ──

    async def list_campaigns(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/campaigns", params=params)

    async def get_campaign(self, campaign_id: int) -> dict:
        return await self._get(f"/campaigns/{campaign_id}")

    async def create_campaign(self, data: dict) -> dict:
        return await self._post("/campaigns", json=data)

    async def update_campaign(self, campaign_id: int, data: dict) -> dict:
        return await self._patch(f"/campaigns/{campaign_id}", json=data)

    async def delete_campaign(self, campaign_id: int) -> dict:
        return await self._delete(f"/campaigns/{campaign_id}")

    # ── Partners ──

    async def list_partners(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/partners/referrers", params=params)

    async def get_partner(self, user_id: int) -> dict:
        return await self._get(f"/partners/referrers/{user_id}")

    async def update_partner_commission(self, user_id: int, data: dict) -> dict:
        return await self._patch(f"/partners/referrers/{user_id}/commission", json=data)

    async def get_partner_global_stats(self) -> dict:
        return await self._get("/partners/stats")

    async def get_partner_top_referrers(self) -> dict:
        return await self._get("/partners/stats/top-referrers")

    # ── Broadcasts (bulk messages) ──

    async def list_broadcasts(self, limit: int = 20, offset: int = 0, **filters) -> dict:
        params = {"limit": limit, "offset": offset}
        params.update({k: v for k, v in filters.items() if v is not None})
        return await self._get("/broadcasts", params=params)

    async def create_broadcast(self, data: dict) -> dict:
        return await self._post("/broadcasts", json=data)

    async def stop_broadcast(self, broadcast_id: int) -> dict:
        return await self._post(f"/broadcasts/{broadcast_id}/stop")


bedolaga_client = BedolagaClient()
