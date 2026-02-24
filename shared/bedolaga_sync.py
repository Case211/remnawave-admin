"""
Background sync service for Bedolaga bot data.

Periodically fetches static data (stats, users, subscriptions, transactions)
from the Bedolaga Web API and caches it in the local PostgreSQL database.
This enables fast analytics queries without hitting the Bedolaga API on every request.

Dynamic data (tickets, promos, polls) is NOT synced — those are fetched
in real-time via the bedolaga_client when needed.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BedolagaSyncService:
    """Periodic sync of Bedolaga data to local cache tables."""

    def __init__(self):
        self._running: bool = False
        self._sync_task: Optional[asyncio.Task] = None
        self._initial_sync_done: bool = False

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def initial_sync_done(self) -> bool:
        return self._initial_sync_done

    async def start(self, interval_seconds: int = 300) -> None:
        """Start the sync service with periodic loop."""
        if self._running:
            logger.warning("Bedolaga sync service already running")
            return

        from shared.bedolaga_client import bedolaga_client
        if not bedolaga_client.is_configured:
            logger.info("Bedolaga API not configured, sync service disabled")
            return

        from shared.database import db_service
        if not db_service.is_connected:
            logger.warning("Database not connected, Bedolaga sync cannot start")
            return

        self._running = True
        logger.info(
            "Bedolaga sync service started (interval: %ds)", interval_seconds,
        )

        # Initial sync
        await self._run_initial_sync()

        # Periodic loop
        self._sync_task = asyncio.create_task(
            self._periodic_sync_loop(interval_seconds)
        )

    async def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None
        logger.info("Bedolaga sync service stopped")

    async def _run_initial_sync(self) -> None:
        try:
            await self.full_sync()
            self._initial_sync_done = True
            logger.info("Bedolaga initial sync completed")
        except Exception as e:
            logger.error("Bedolaga initial sync failed: %s", e)

    async def _periodic_sync_loop(self, interval: int) -> None:
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                logger.debug("Running periodic Bedolaga sync...")
                await self.full_sync()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Bedolaga periodic sync error: %s", e)

    async def full_sync(self) -> Dict[str, int]:
        """Sync all entities. Returns dict with synced record counts."""
        results: Dict[str, int] = {}

        for entity, sync_fn in [
            ("stats", self.sync_stats),
            ("users", self.sync_users),
            ("subscriptions", self.sync_subscriptions),
            ("transactions", self.sync_transactions),
        ]:
            try:
                results[entity] = await sync_fn()
            except Exception as e:
                logger.error("Failed to sync Bedolaga %s: %s", entity, e)
                results[entity] = -1
                await self._update_sync_metadata(entity, "error", str(e))

        logger.debug("Bedolaga full sync: %s", results)
        return results

    # ── Stats ─────────────────────────────────────────────────────

    async def sync_stats(self) -> int:
        """Fetch overview stats and save a snapshot."""
        from shared.bedolaga_client import bedolaga_client
        from shared.database import db_service

        data = await bedolaga_client.get_stats_overview()

        async with db_service.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO bedolaga_stats_snapshots
                    (total_users, active_subscriptions, total_revenue,
                     total_transactions, open_tickets, raw_data)
                VALUES ($1, $2, $3, $4, $5, $6)
                """,
                data.get("total_users", 0),
                data.get("active_subscriptions", 0),
                float(data.get("total_revenue", 0)),
                data.get("total_transactions", 0),
                data.get("open_tickets", 0),
                json.dumps(data),
            )

        await self._update_sync_metadata("stats", "success", records_synced=1)
        return 1

    # ── Users ─────────────────────────────────────────────────────

    async def sync_users(self) -> int:
        """Paginate through all Bedolaga users and upsert into cache."""
        from shared.bedolaga_client import bedolaga_client
        from shared.database import db_service

        total_synced = 0
        offset = 0
        page_size = 100
        seen_ids: set[int] = set()

        while True:
            resp = await bedolaga_client.get_users(limit=page_size, offset=offset)

            # Bedolaga returns paginated: items list + total
            items = resp.get("items", resp.get("users", []))
            if not isinstance(items, list):
                items = []
            total = resp.get("total", 0)

            if not items:
                break

            async with db_service.acquire() as conn:
                for user in items:
                    uid = user.get("id")
                    if not uid:
                        continue
                    seen_ids.add(uid)
                    await conn.execute(
                        """
                        INSERT INTO bedolaga_users_cache
                            (id, telegram_id, username, first_name, last_name,
                             status, balance_kopeks, referral_code, referred_by_id,
                             has_had_paid_subscription, created_at, last_activity,
                             raw_data, synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
                        ON CONFLICT (id) DO UPDATE SET
                            telegram_id = EXCLUDED.telegram_id,
                            username = EXCLUDED.username,
                            first_name = EXCLUDED.first_name,
                            last_name = EXCLUDED.last_name,
                            status = EXCLUDED.status,
                            balance_kopeks = EXCLUDED.balance_kopeks,
                            referral_code = EXCLUDED.referral_code,
                            referred_by_id = EXCLUDED.referred_by_id,
                            has_had_paid_subscription = EXCLUDED.has_had_paid_subscription,
                            created_at = EXCLUDED.created_at,
                            last_activity = EXCLUDED.last_activity,
                            raw_data = EXCLUDED.raw_data,
                            synced_at = NOW()
                        """,
                        uid,
                        user.get("telegram_id"),
                        user.get("username"),
                        user.get("first_name"),
                        user.get("last_name"),
                        user.get("status"),
                        user.get("balance_kopeks", 0),
                        user.get("referral_code"),
                        user.get("referred_by_id"),
                        user.get("has_had_paid_subscription", False),
                        _parse_dt(user.get("created_at")),
                        _parse_dt(user.get("last_activity")),
                        json.dumps(user),
                    )
                    total_synced += 1

            offset += page_size
            if offset >= total or len(items) < page_size:
                break

        # Remove stale entries
        if seen_ids:
            async with db_service.acquire() as conn:
                deleted = await conn.execute(
                    "DELETE FROM bedolaga_users_cache WHERE id != ALL($1::int[])",
                    list(seen_ids),
                )
                if deleted and "DELETE" in deleted:
                    count = int(deleted.split()[-1])
                    if count:
                        logger.info("Removed %d stale Bedolaga users from cache", count)

        await self._update_sync_metadata("users", "success", records_synced=total_synced)
        logger.debug("Synced %d Bedolaga users", total_synced)
        return total_synced

    # ── Subscriptions ─────────────────────────────────────────────

    async def sync_subscriptions(self) -> int:
        """Paginate through subscriptions and upsert into cache."""
        from shared.bedolaga_client import bedolaga_client
        from shared.database import db_service

        total_synced = 0
        offset = 0
        page_size = 100
        seen_ids: set[int] = set()

        while True:
            resp = await bedolaga_client.get_subscriptions(limit=page_size, offset=offset)
            items = resp.get("items", resp.get("subscriptions", []))
            if not isinstance(items, list):
                items = []
            total = resp.get("total", 0)

            if not items:
                break

            async with db_service.acquire() as conn:
                for sub in items:
                    sid = sub.get("id")
                    if not sid:
                        continue
                    seen_ids.add(sid)
                    await conn.execute(
                        """
                        INSERT INTO bedolaga_subscriptions_cache
                            (id, user_id, user_telegram_id, plan_name, status,
                             is_trial, started_at, expires_at, traffic_limit_bytes,
                             traffic_used_bytes, payment_amount, payment_provider,
                             raw_data, synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
                        ON CONFLICT (id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            user_telegram_id = EXCLUDED.user_telegram_id,
                            plan_name = EXCLUDED.plan_name,
                            status = EXCLUDED.status,
                            is_trial = EXCLUDED.is_trial,
                            started_at = EXCLUDED.started_at,
                            expires_at = EXCLUDED.expires_at,
                            traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
                            traffic_used_bytes = EXCLUDED.traffic_used_bytes,
                            payment_amount = EXCLUDED.payment_amount,
                            payment_provider = EXCLUDED.payment_provider,
                            raw_data = EXCLUDED.raw_data,
                            synced_at = NOW()
                        """,
                        sid,
                        sub.get("user_id"),
                        sub.get("user_telegram_id"),
                        sub.get("plan_name"),
                        sub.get("status"),
                        sub.get("is_trial", False),
                        _parse_dt(sub.get("started_at")),
                        _parse_dt(sub.get("expires_at")),
                        sub.get("traffic_limit_bytes"),
                        sub.get("traffic_used_bytes"),
                        _to_decimal(sub.get("payment_amount")),
                        sub.get("payment_provider"),
                        json.dumps(sub),
                    )
                    total_synced += 1

            offset += page_size
            if offset >= total or len(items) < page_size:
                break

        if seen_ids:
            async with db_service.acquire() as conn:
                await conn.execute(
                    "DELETE FROM bedolaga_subscriptions_cache WHERE id != ALL($1::int[])",
                    list(seen_ids),
                )

        await self._update_sync_metadata(
            "subscriptions", "success", records_synced=total_synced,
        )
        logger.debug("Synced %d Bedolaga subscriptions", total_synced)
        return total_synced

    # ── Transactions ──────────────────────────────────────────────

    async def sync_transactions(self) -> int:
        """Paginate through transactions and upsert into cache."""
        from shared.bedolaga_client import bedolaga_client
        from shared.database import db_service

        total_synced = 0
        offset = 0
        page_size = 100

        while True:
            resp = await bedolaga_client.get_transactions(limit=page_size, offset=offset)
            items = resp.get("items", resp.get("transactions", []))
            if not isinstance(items, list):
                items = []
            total = resp.get("total", 0)

            if not items:
                break

            async with db_service.acquire() as conn:
                for tx in items:
                    tid = tx.get("id")
                    if not tid:
                        continue
                    await conn.execute(
                        """
                        INSERT INTO bedolaga_transactions_cache
                            (id, user_id, user_telegram_id, amount, currency,
                             provider, status, type, created_at, raw_data, synced_at)
                        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,NOW())
                        ON CONFLICT (id) DO UPDATE SET
                            user_id = EXCLUDED.user_id,
                            user_telegram_id = EXCLUDED.user_telegram_id,
                            amount = EXCLUDED.amount,
                            currency = EXCLUDED.currency,
                            provider = EXCLUDED.provider,
                            status = EXCLUDED.status,
                            type = EXCLUDED.type,
                            created_at = EXCLUDED.created_at,
                            raw_data = EXCLUDED.raw_data,
                            synced_at = NOW()
                        """,
                        tid,
                        tx.get("user_id"),
                        tx.get("user_telegram_id"),
                        _to_decimal(tx.get("amount")),
                        tx.get("currency", "RUB"),
                        tx.get("provider"),
                        tx.get("status"),
                        tx.get("type"),
                        _parse_dt(tx.get("created_at")),
                        json.dumps(tx),
                    )
                    total_synced += 1

            offset += page_size
            if offset >= total or len(items) < page_size:
                break

        await self._update_sync_metadata(
            "transactions", "success", records_synced=total_synced,
        )
        logger.debug("Synced %d Bedolaga transactions", total_synced)
        return total_synced

    # ── Sync metadata ─────────────────────────────────────────────

    async def _update_sync_metadata(
        self,
        entity: str,
        status: str,
        error_message: Optional[str] = None,
        records_synced: int = 0,
    ) -> None:
        """Write sync status to sync_metadata table (reusing existing table)."""
        try:
            from shared.database import db_service
            key = f"bedolaga_{entity}"
            await db_service.update_sync_metadata(
                key=key,
                status=status,
                records_synced=records_synced,
                error_message=error_message,
            )
        except Exception as e:
            logger.warning("Failed to update sync metadata for %s: %s", entity, e)

    async def get_sync_status(self) -> list[dict]:
        """Get sync status for all Bedolaga entities."""
        try:
            from shared.database import db_service
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT key, last_sync_at, sync_status, records_synced, error_message
                    FROM sync_metadata
                    WHERE key LIKE 'bedolaga_%'
                    ORDER BY key
                    """
                )
                return [dict(r) for r in rows]
        except Exception:
            return []


# ── Helpers ───────────────────────────────────────────────────────

def _parse_dt(val: Any) -> Optional[datetime]:
    """Parse a datetime string from Bedolaga API response."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(val, fmt)
            except ValueError:
                continue
        try:
            from datetime import datetime as dt
            return dt.fromisoformat(val)
        except (ValueError, TypeError):
            pass
    return None


def _to_decimal(val: Any) -> Optional[float]:
    """Safely convert to float for NUMERIC columns."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


# Global instance
bedolaga_sync_service = BedolagaSyncService()
