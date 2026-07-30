"""
Users mixin — user baselines, CRUD, search, bulk operations.
"""
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from shared.logger import logger
from shared.db._base import _db_row_to_api_format, _parse_timestamp
from shared.db_schema import ADMIN_TABLE, USERS_TABLE, USER_BASELINES_TABLE, USER_CONNECTIONS_TABLE, USER_HWID_DEVICES_TABLE
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql


class UsersMixin:
    # ==================== User Baselines ====================

    async def get_user_baseline(self, user_uuid: str, max_age_seconds: int = 3600) -> Optional[Dict[str, Any]]:
        """Get cached baseline if fresh enough (within max_age_seconds)."""
        if not self.is_connected:
            return None
        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    select_sql(
                        USER_BASELINES_TABLE,
                        "user_uuid, typical_countries, typical_cities, typical_regions,"
                        " typical_asns, known_ips, avg_daily_unique_ips, max_daily_unique_ips,"
                        " typical_hours, avg_session_duration_min, data_points",
                        "WHERE user_uuid = $1"
                        " AND computed_at > NOW() - make_interval(secs => $2)",
                    ),
                    user_uuid, max_age_seconds,
                )
                if row:
                    return {
                        'typical_countries': list(row['typical_countries'] or []),
                        'typical_cities': list(row['typical_cities'] or []),
                        'typical_regions': list(row['typical_regions'] or []),
                        'typical_asns': list(row['typical_asns'] or []),
                        'known_ips': list(row['known_ips'] or [])[:500],
                        'avg_daily_unique_ips': row['avg_daily_unique_ips'] or 0.0,
                        'max_daily_unique_ips': row['max_daily_unique_ips'] or 0,
                        'typical_hours': list(row['typical_hours'] or []),
                        'avg_session_duration_minutes': row['avg_session_duration_min'] or 0,
                        'data_points': row['data_points'] or 0,
                    }
        except Exception as e:
            logger.warning("get_user_baseline failed: %s", e)
        return None

    async def save_user_baseline(self, user_uuid: str, baseline: Dict[str, Any]) -> None:
        """Save computed baseline to DB for persistence across restarts."""
        if not self.is_connected:
            return
        try:
            async with self.acquire() as conn:
                await conn.execute(
                    insert_sql(
                        USER_BASELINES_TABLE,
                        [
                            "user_uuid", "typical_countries", "typical_cities", "typical_regions",
                            "typical_asns", "known_ips", "avg_daily_unique_ips", "max_daily_unique_ips",
                            "typical_hours", "avg_session_duration_min", "data_points", "computed_at",
                        ],
                        values="$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW()",
                        suffix=(
                            "ON CONFLICT (user_uuid) DO UPDATE SET "
                            "typical_countries = EXCLUDED.typical_countries, "
                            "typical_cities = EXCLUDED.typical_cities, "
                            "typical_regions = EXCLUDED.typical_regions, "
                            "typical_asns = EXCLUDED.typical_asns, "
                            "known_ips = EXCLUDED.known_ips, "
                            "avg_daily_unique_ips = EXCLUDED.avg_daily_unique_ips, "
                            "max_daily_unique_ips = EXCLUDED.max_daily_unique_ips, "
                            "typical_hours = EXCLUDED.typical_hours, "
                            "avg_session_duration_min = EXCLUDED.avg_session_duration_min, "
                            "data_points = EXCLUDED.data_points, "
                            "computed_at = NOW()"
                        ),
                    ),
                    user_uuid,
                    baseline.get('typical_countries', []),
                    baseline.get('typical_cities', []),
                    baseline.get('typical_regions', []),
                    baseline.get('typical_asns', []),
                    baseline.get('known_ips', []),
                    baseline.get('avg_daily_unique_ips', 0.0),
                    baseline.get('max_daily_unique_ips', 0),
                    baseline.get('typical_hours', []),
                    baseline.get('avg_session_duration_minutes', 0),
                    baseline.get('data_points', 0),
                )
        except Exception as e:
            logger.warning("save_user_baseline failed: %s", e)

    async def get_stale_baseline_users(self, max_age_seconds: int = 3600, limit: int = 100) -> List[str]:
        """Get user UUIDs that need baseline refresh (stale or missing)."""
        if not self.is_connected:
            return []
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    (
                        SELECT u.uuid, NULL::timestamptz AS computed_at
                        FROM {USERS_TABLE} u
                        WHERE NOT EXISTS (
                            SELECT 1 FROM {USER_BASELINES_TABLE} b WHERE b.user_uuid = u.uuid
                        )
                    )
                    UNION ALL
                    (
                        SELECT b.user_uuid AS uuid, b.computed_at
                        FROM {USER_BASELINES_TABLE} b
                        WHERE b.computed_at < NOW() - make_interval(secs => $1)
                    )
                    ORDER BY computed_at ASC NULLS FIRST
                    LIMIT $2
                    """,
                    max_age_seconds, limit,
                )
                return [str(r['uuid']) for r in rows]
        except Exception as e:
            logger.warning("get_stale_baseline_users failed: %s", e)
            return []

    # ==================== Users ====================
    
    async def get_user_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(USERS_TABLE, "*", "WHERE uuid = $1"),
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_uuid_by_email(self, email: str) -> Optional[str]:
        """Находит user_uuid по email. Возвращает UUID или None."""
        if not self.is_connected or not email:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(USERS_TABLE, "uuid", "WHERE email = $1 LIMIT 1"),
                email
            )
            return str(row["uuid"]) if row else None

    async def get_email_to_uuid_map(self, emails: list) -> Dict[str, str]:
        """Resolve multiple emails to user UUIDs in one query.
        Returns: {email: uuid_string}
        """
        if not self.is_connected or not emails:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "email, uuid::text", "WHERE email = ANY($1::text[])"),
                emails,
            )
            return {r["email"]: r["uuid"] for r in rows}

    async def get_short_uuid_to_uuid_map(self, short_uuids: list) -> Dict[str, str]:
        """Resolve multiple short_uuids to user UUIDs in one query.
        Returns: {short_uuid: uuid_string}
        """
        if not self.is_connected or not short_uuids:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "short_uuid, uuid::text", "WHERE short_uuid = ANY($1::text[])"),
                short_uuids,
            )
            return {r["short_uuid"]: r["uuid"] for r in rows}

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username (case-insensitive) with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(USERS_TABLE, "*", "WHERE LOWER(username) = LOWER($1)"),
                username
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user by Telegram ID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(USERS_TABLE, "*", "WHERE telegram_id = $1"),
                telegram_id
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_by_short_uuid(self, short_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by short UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(USERS_TABLE, "*", "WHERE short_uuid = $1"),
                short_uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_by_subscription_uuid(self, subscription_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by subscription UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(USERS_TABLE, "*", "WHERE subscription_uuid = $1"),
                subscription_uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_uuid_by_id_from_raw_data(self, user_id: str) -> Optional[str]:
        """Находит user_uuid по ID из raw_data (для Xray логов).

        Uses UNION ALL instead of OR to allow PostgreSQL to use
        individual functional indexes on each raw_data field.
        Results are cached in-memory (TTL 60s) to reduce DB load
        since this is called on every connection from node agents.
        """
        if not self.is_connected or not user_id:
            return None

        # Check in-memory cache first
        now = time.monotonic()
        cached = self._raw_data_id_cache.get(user_id)
        if cached is not None:
            value, ts = cached
            if now - ts < self._RAW_DATA_ID_CACHE_TTL:
                return value
            del self._raw_data_id_cache[user_id]

        async with self.acquire() as conn:
            # UNION ALL allows each branch to use its own functional index
            # instead of a sequential scan caused by OR conditions
            row = await conn.fetchrow(
                f"""
                SELECT uuid FROM (
                    SELECT uuid FROM {USERS_TABLE} WHERE raw_data->>'id' = $1 AND raw_data IS NOT NULL
                    UNION ALL
                    SELECT uuid FROM {USERS_TABLE} WHERE raw_data->>'userId' = $1 AND raw_data IS NOT NULL
                    UNION ALL
                    SELECT uuid FROM {USERS_TABLE} WHERE raw_data->>'user_id' = $1 AND raw_data IS NOT NULL
                ) sub
                LIMIT 1
                """,
                user_id
            )
            result = str(row["uuid"]) if row else None

        # Populate cache (also cache misses to avoid repeated lookups)
        if len(self._raw_data_id_cache) >= self._RAW_DATA_ID_CACHE_MAX:
            # Evict oldest ~25% of entries
            sorted_keys = sorted(
                self._raw_data_id_cache,
                key=lambda k: self._raw_data_id_cache[k][1]
            )
            for k in sorted_keys[:len(sorted_keys) // 4 + 1]:
                del self._raw_data_id_cache[k]
        self._raw_data_id_cache[user_id] = (result, now)

        return result
    
    async def search_users(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search users by username, email, short_uuid, or UUID.
        Returns list of matching users in API format.
        """
        if not self.is_connected:
            return []
        
        search_pattern = f"%{query}%"
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT {self._USER_LIST_COLUMNS} FROM {USERS_TABLE}
                WHERE
                    LOWER(username) LIKE LOWER($1) OR
                    LOWER(email) LIKE LOWER($1) OR
                    short_uuid LIKE $1 OR
                    uuid::text LIKE $1
                ORDER BY username
                LIMIT $2 OFFSET $3
                """,
                search_pattern, limit, offset
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_users_count(self) -> int:
        """Get total number of users in database."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.fetchval(select_sql(USERS_TABLE, "COUNT(*)"))
            return result or 0
    
    # Allowlist для ORDER BY — защита от SQL-инъекции
    ALLOWED_ORDER_BY = {"username", "created_at", "updated_at", "status", "expire_at", "email", "uuid"}

    # Explicit columns for list queries — excludes raw_data (JSONB) to reduce transfer size
    _USER_LIST_COLUMNS = (
        "uuid, username, status, email, expire_at, traffic_limit_bytes, used_traffic_bytes, "
        "raw_used_traffic_bytes, hwid_device_limit, created_at, updated_at, short_uuid, "
        "subscription_uuid, telegram_id, created_by_admin_id"
    )

    async def get_all_users(
        self,
        limit: int = 100,
        offset: int = 0,
        status: Optional[str] = None,
        order_by: str = "username"
    ) -> List[Dict[str, Any]]:
        """
        Get all users with optional filtering and pagination.
        Returns list of users with raw_data converted to API format.
        """
        if not self.is_connected:
            return []

        if order_by not in self.ALLOWED_ORDER_BY:
            order_by = "username"

        async with self.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    f"SELECT {self._USER_LIST_COLUMNS} FROM {USERS_TABLE} WHERE status = $1 ORDER BY {order_by} LIMIT $2 OFFSET $3",
                    status, limit, offset
                )
            else:
                rows = await conn.fetch(
                    f"SELECT {self._USER_LIST_COLUMNS} FROM {USERS_TABLE} ORDER BY {order_by} LIMIT $1 OFFSET $2",
                    limit, offset
                )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_users_stats(self) -> Dict[str, int]:
        """
        Get users statistics by status.
        Returns dict: {total, active, expired, disabled, limited}
        """
        if not self.is_connected:
            return {"total": 0, "active": 0, "expired": 0, "disabled": 0, "limited": 0}
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "status, COUNT(*) as count", "GROUP BY status")
            )
            
            stats = {"total": 0, "active": 0, "expired": 0, "disabled": 0, "limited": 0}
            for row in rows:
                status = row["status"]
                count = row["count"]
                stats["total"] += count
                if status:
                    stats[status.lower()] = count
            
            return stats
    
    async def get_users_count_by_status(self) -> Dict[str, Any]:
        """
        Get user counts grouped by status + total traffic sum via SQL aggregation.
        Returns: {total, active, disabled, expired, limited, total_used_traffic_bytes}
        """
        if not self.is_connected:
            return {"total": 0, "active": 0, "disabled": 0, "expired": 0,
                    "limited": 0, "total_used_traffic_bytes": 0}

        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(
                    USERS_TABLE,
                    "COUNT(*) AS total,\n"
                    "                    COUNT(*) FILTER (WHERE LOWER(status) = 'active') AS active,\n"
                    "                    COUNT(*) FILTER (WHERE LOWER(status) = 'disabled') AS disabled,\n"
                    "                    COUNT(*) FILTER (WHERE LOWER(status) = 'expired') AS expired,\n"
                    "                    COUNT(*) FILTER (WHERE LOWER(status) = 'limited') AS limited,\n"
                    "                    COALESCE(SUM(used_traffic_bytes), 0) AS total_used_traffic_bytes"
                )
            )
            return dict(row) if row else {
                "total": 0, "active": 0, "disabled": 0, "expired": 0,
                "limited": 0, "total_used_traffic_bytes": 0,
            }

    # Allowed sort columns for paginated queries (column name -> SQL expression)
    _PAGINATED_SORT_MAP = {
        "created_at": "created_at",
        "username": "username",
        "status": "status",
        "expire_at": "expire_at",
        "email": "email",
        "uuid": "uuid",
        "updated_at": "updated_at",
        "used_traffic_bytes": "COALESCE(used_traffic_bytes, 0)",
        "raw_used_traffic_bytes": "COALESCE(raw_used_traffic_bytes, 0)",
        "lifetime_used_traffic_bytes": "COALESCE((raw_data->>'lifetimeUsedTrafficBytes')::bigint, 0)",
        "traffic_limit_bytes": "COALESCE(traffic_limit_bytes, 0)",
        "hwid_device_limit": "COALESCE(hwid_device_limit, 0)",
        "online_at": "immutable_tstz(raw_data->'userTraffic'->>'onlineAt')",
        "created_by_admin_username": (
            "(" + select_sql(ADMIN_TABLE, 'username', 'WHERE id = users.created_by_admin_id') + ")"
        ),
    }

    async def get_users_paginated(
        self,
        page: int = 1,
        per_page: int = 20,
        search: Optional[str] = None,
        status: Optional[str] = None,
        traffic_type: Optional[str] = None,
        expire_filter: Optional[str] = None,
        online_filter: Optional[str] = None,
        traffic_usage: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        uuid_whitelist: Optional[List[str]] = None,
        admin_id: Optional[int] = None,
        external_squad_uuid: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> tuple:
        """
        Get paginated users with server-side filtering and sorting.
        Returns (users_list, total_count).

        If `uuid_whitelist` is provided (access-policy scope), only users
        with matching UUID are returned. An empty list means no access —
        returns ([], 0).
        """
        if not self.is_connected:
            return [], 0

        conditions = []
        args = []
        param_idx = 0

        # Access-policy scope filter
        if uuid_whitelist is not None:
            if not uuid_whitelist:
                return [], 0
            param_idx += 1
            args.append(uuid_whitelist)
            conditions.append(f"uuid::text = ANY(${param_idx})")

        # Filter: search
        if search:
            param_idx += 1
            like_param = f"${param_idx}"
            args.append(f"%{search}%")
            conditions.append(
                f"(LOWER(username) LIKE LOWER({like_param})"
                f" OR LOWER(email) LIKE LOWER({like_param})"
                f" OR uuid::text LIKE {like_param}"
                f" OR short_uuid LIKE {like_param}"
                f" OR telegram_id::text LIKE {like_param}"
                f" OR LOWER(COALESCE(description, raw_data->>'description', '')) LIKE LOWER({like_param}))"
            )

        # Filter: status
        if status:
            param_idx += 1
            args.append(status.lower())
            conditions.append(f"LOWER(status) = ${param_idx}")

        # Filter: traffic type
        if traffic_type == "unlimited":
            conditions.append("(traffic_limit_bytes IS NULL OR traffic_limit_bytes = 0)")
        elif traffic_type == "limited":
            conditions.append("(traffic_limit_bytes IS NOT NULL AND traffic_limit_bytes > 0)")

        # Filter: expiration
        if expire_filter == "no_expiry":
            conditions.append("expire_at IS NULL")
        elif expire_filter == "expired":
            conditions.append("expire_at < NOW()")
        elif expire_filter == "expiring_7d":
            conditions.append("expire_at >= NOW() AND expire_at <= NOW() + INTERVAL '7 days'")
        elif expire_filter == "expiring_30d":
            conditions.append("expire_at >= NOW() AND expire_at <= NOW() + INTERVAL '30 days'")

        # Filter: online status (from JSONB userTraffic.onlineAt)
        # Uses immutable_tstz() wrapper to match the functional index
        _online_expr = "raw_data->'userTraffic'->>'onlineAt'"
        _online_ts = f"immutable_tstz({_online_expr})"
        if online_filter == "never":
            conditions.append(f"({_online_expr}) IS NULL")
        elif online_filter == "online_24h":
            conditions.append(
                f"({_online_expr}) IS NOT NULL AND {_online_ts} >= NOW() - INTERVAL '24 hours'"
            )
        elif online_filter == "online_7d":
            conditions.append(
                f"({_online_expr}) IS NOT NULL AND {_online_ts} >= NOW() - INTERVAL '7 days'"
            )
        elif online_filter == "online_30d":
            conditions.append(
                f"({_online_expr}) IS NOT NULL AND {_online_ts} >= NOW() - INTERVAL '30 days'"
            )

        # Filter: traffic usage percentage
        if traffic_usage == "zero":
            conditions.append("COALESCE(used_traffic_bytes, 0) = 0")
        elif traffic_usage in ("above_50", "above_70", "above_90"):
            threshold = {"above_50": 0.5, "above_70": 0.7, "above_90": 0.9}[traffic_usage]
            param_idx += 1
            args.append(threshold)
            conditions.append(
                f"traffic_limit_bytes > 0 AND (used_traffic_bytes::float / traffic_limit_bytes) >= ${param_idx}"
            )

        # Filter: admin
        if admin_id is not None:
            param_idx += 1
            args.append(admin_id)
            conditions.append(f"created_by_admin_id = ${param_idx}")

        # Filter: external squad (compare as text to tolerate any UUID casing / invalid input)
        if external_squad_uuid:
            param_idx += 1
            args.append(str(external_squad_uuid))
            conditions.append(f"external_squad_uuid::text = ${param_idx}")

        # Filter: tag (exact match, single tag per user)
        if tag:
            param_idx += 1
            args.append(tag)
            conditions.append(f"tag = ${param_idx}")

        where_clause = " AND ".join(conditions) if conditions else "TRUE"

        # Sort
        sort_expr = self._PAGINATED_SORT_MAP.get(sort_by, "created_at")
        direction = "DESC" if sort_order == "desc" else "ASC"
        nulls = "NULLS LAST" if direction == "DESC" else "NULLS FIRST"
        order_clause = f"{sort_expr} {direction} {nulls}"

        # Pagination
        offset = (page - 1) * per_page
        param_idx += 1
        args.append(per_page)
        limit_param = f"${param_idx}"
        param_idx += 1
        args.append(offset)
        offset_param = f"${param_idx}"

        query = f"""
            SELECT *, COUNT(*) OVER() AS _total_count
            FROM {USERS_TABLE}
            WHERE {where_clause}
            ORDER BY {order_clause}
            LIMIT {limit_param} OFFSET {offset_param}
        """

        async with self.acquire() as conn:
            rows = await conn.fetch(query, *args)

        if not rows:
            # No results — still need total count for empty filter results
            count_query = select_sql(USERS_TABLE, "COUNT(*)", f"WHERE {where_clause}")
            # Remove limit/offset args for count query
            count_args = args[:-2]
            async with self.acquire() as conn:
                total = await conn.fetchval(count_query, *count_args)
            return [], total or 0

        total = rows[0]["_total_count"]
        users = [_db_row_to_api_format(row) for row in rows]
        return users, total

    async def get_distinct_user_tags(self) -> List[str]:
        """Return sorted list of distinct non-empty user tags (for filter dropdown)."""
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT DISTINCT tag FROM {USERS_TABLE} "
                f"WHERE tag IS NOT NULL AND tag <> '' ORDER BY tag"
            )
        return [r["tag"] for r in rows]

    async def get_hwid_device_counts_for_uuids(self, user_uuids: List[str]) -> Dict[str, int]:
        """Get HWID device counts for specific users by UUID list."""
        if not self.is_connected or not user_uuids:
            return {}
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(USER_HWID_DEVICES_TABLE, "user_uuid, COUNT(*) as cnt", "WHERE user_uuid = ANY($1::uuid[]) GROUP BY user_uuid"),
                    user_uuids
                )
                return {str(row["user_uuid"]): row["cnt"] for row in rows}
        except Exception as e:
            logger.error("Error getting HWID counts for UUIDs: %s", e, exc_info=True)
            return {}

    async def get_raw_traffic_for_uuids(self, user_uuids: List[str]) -> Dict[str, int]:
        """Get raw traffic sums for specific users by UUID list."""
        if not self.is_connected or not user_uuids:
            return {}
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(USERS_TABLE, "uuid::text, raw_used_traffic_bytes", "WHERE uuid = ANY($1::uuid[]) AND raw_used_traffic_bytes > 0"),
                    user_uuids
                )
                return {r["uuid"]: int(r["raw_used_traffic_bytes"]) for r in rows}
        except Exception as e:
            logger.error("Error getting raw traffic for UUIDs: %s", e, exc_info=True)
            return {}

    async def get_users_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get users by status in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "*", "WHERE status = $1 ORDER BY username LIMIT $2 OFFSET $3"),
                status, limit, offset
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def _upsert_user_with_conn(self, conn, user_data: Dict[str, Any]) -> None:
        """Insert or update a user using provided connection (for batch operations)."""
        response = user_data.get("response", user_data)

        uuid = response.get("uuid")
        if not uuid:
            logger.warning("Cannot upsert user without UUID")
            return

        user_traffic = response.get("userTraffic") or {}
        ut_val = user_traffic.get("usedTrafficBytes")
        used_traffic = ut_val if ut_val is not None else response.get("usedTrafficBytes")

        await conn.execute(
            insert_sql(
                USERS_TABLE,
                [
                    "uuid", "short_uuid", "username", "subscription_uuid", "telegram_id",
                    "email", "status", "expire_at", "traffic_limit_bytes", "used_traffic_bytes",
                    "hwid_device_limit", "description", "created_at", "updated_at", "raw_data",
                    "created_by_admin_id", "external_squad_uuid",
                ],
                values="$1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, NOW(), $14,\n"
                "                NULL, $15::uuid",
                suffix=(
                    "ON CONFLICT (uuid) DO UPDATE SET "
                    "short_uuid = EXCLUDED.short_uuid, "
                    "username = EXCLUDED.username, "
                    "subscription_uuid = EXCLUDED.subscription_uuid, "
                    "telegram_id = EXCLUDED.telegram_id, "
                    "email = EXCLUDED.email, "
                    "status = EXCLUDED.status, "
                    "expire_at = EXCLUDED.expire_at, "
                    "traffic_limit_bytes = EXCLUDED.traffic_limit_bytes, "
                    "used_traffic_bytes = EXCLUDED.used_traffic_bytes, "
                    "hwid_device_limit = EXCLUDED.hwid_device_limit, "
                    "description = EXCLUDED.description, "
                    "updated_at = NOW(), "
                    "raw_data = EXCLUDED.raw_data, "
                    # Панель — источник истины по внешнему скваду. Без этой
                    # строки колонка навсегда оставалась NULL, и фильтр
                    # «External squad» в витрине юзеров всегда давал 0 (#263).
                    "external_squad_uuid = EXCLUDED.external_squad_uuid, "
                    "created_by_admin_id = COALESCE(EXCLUDED.created_by_admin_id, users.created_by_admin_id)"
                ),
            ),
            uuid,
            response.get("shortUuid"),
            response.get("username"),
            response.get("subscriptionUuid"),
            response.get("telegramId"),
            response.get("email"),
            response.get("status"),
            _parse_timestamp(response.get("expireAt")),
            response.get("trafficLimitBytes"),
            used_traffic,
            response.get("hwidDeviceLimit"),
            response.get("description") or response.get("note") or "",
            _parse_timestamp(response.get("createdAt")),
            json.dumps(response),
            response.get("externalSquadUuid"),
        )

    async def upsert_user(self, user_data: Dict[str, Any]) -> None:
        """Insert or update a user."""
        if not self.is_connected:
            return
        async with self.acquire() as conn:
            await self._upsert_user_with_conn(conn, user_data)
    
    async def bulk_upsert_users(self, users: List[Dict[str, Any]]) -> int:
        """Bulk insert or update users. Returns number of records processed."""
        if not self.is_connected or not users:
            return 0

        count = 0
        async with self.acquire() as conn:
            async with conn.transaction():
                for user_data in users:
                    try:
                        await self._upsert_user_with_conn(conn, user_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert user: %s", e)

        return count

    async def batch_upsert_users_unnest(self, users_data: List[Dict[str, Any]]) -> int:
        """True batch upsert users using UNNEST arrays (much faster than per-record)."""
        if not self.is_connected or not users_data:
            return 0

        uuids = []
        short_uuids = []
        usernames = []
        subscription_uuids = []
        telegram_ids = []
        emails = []
        statuses = []
        expire_ats = []
        traffic_limits = []
        used_traffics = []
        hwid_limits = []
        descriptions = []
        created_ats = []
        raw_datas = []
        external_squads = []

        for user_data in users_data:
            response = user_data.get("response", user_data)
            uuid_val = response.get("uuid")
            if not uuid_val:
                continue

            user_traffic = response.get("userTraffic") or {}
            ut_val = user_traffic.get("usedTrafficBytes")
            used_traffic = ut_val if ut_val is not None else response.get("usedTrafficBytes")

            uuids.append(uuid_val)
            short_uuids.append(response.get("shortUuid"))
            usernames.append(response.get("username"))
            subscription_uuids.append(response.get("subscriptionUuid"))
            tid = response.get("telegramId")
            telegram_ids.append(str(tid) if tid is not None else None)
            emails.append(response.get("email"))
            statuses.append(response.get("status"))
            expire_ats.append(_parse_timestamp(response.get("expireAt")))
            tl = response.get("trafficLimitBytes")
            traffic_limits.append(str(tl) if tl is not None else None)
            used_traffics.append(str(used_traffic) if used_traffic is not None else None)
            hl = response.get("hwidDeviceLimit")
            hwid_limits.append(str(hl) if hl is not None else None)
            descriptions.append(response.get("description") or response.get("note") or "")
            created_ats.append(_parse_timestamp(response.get("createdAt")))
            raw_datas.append(json.dumps(response))
            esq = response.get("externalSquadUuid")
            external_squads.append(str(esq) if esq else None)

        if not uuids:
            return 0

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    f"""
                    INSERT INTO {USERS_TABLE} (
                        uuid, short_uuid, username, subscription_uuid, telegram_id,
                        email, status, expire_at, traffic_limit_bytes, used_traffic_bytes,
                        hwid_device_limit, description, created_at, updated_at, raw_data,
                        created_by_admin_id, external_squad_uuid
                    )
                    SELECT
                        u::uuid, su, un, sub::uuid, tid::bigint,
                        em, st, ea, tl::bigint, ut::bigint,
                        hl::integer, descr, ca, NOW(), rd::jsonb,
                        NULL::integer, esq::uuid
                    FROM UNNEST(
                        $1::text[], $2::text[], $3::text[], $4::text[], $5::text[],
                        $6::text[], $7::text[], $8::timestamptz[], $9::text[], $10::text[],
                        $11::text[], $12::text[], $13::timestamptz[], $14::text[],
                        $15::text[]
                    ) AS t(u, su, un, sub, tid, em, st, ea, tl, ut, hl, descr, ca, rd, esq)
                    ON CONFLICT (uuid) DO UPDATE SET
                        short_uuid = EXCLUDED.short_uuid,
                        username = EXCLUDED.username,
                        subscription_uuid = EXCLUDED.subscription_uuid,
                        telegram_id = EXCLUDED.telegram_id,
                        email = EXCLUDED.email,
                        status = EXCLUDED.status,
                        expire_at = EXCLUDED.expire_at,
                        traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
                        used_traffic_bytes = EXCLUDED.used_traffic_bytes,
                        hwid_device_limit = EXCLUDED.hwid_device_limit,
                        description = EXCLUDED.description,
                        updated_at = NOW(),
                        raw_data = EXCLUDED.raw_data,
                        external_squad_uuid = EXCLUDED.external_squad_uuid,
                        created_by_admin_id = COALESCE(EXCLUDED.created_by_admin_id, {USERS_TABLE}.created_by_admin_id)
                    """,
                    uuids, short_uuids, usernames, subscription_uuids, telegram_ids,
                    emails, statuses, expire_ats, traffic_limits, used_traffics,
                    hwid_limits, descriptions, created_ats, raw_datas,
                    external_squads,
                )
                return int(result.split()[-1]) if result else 0
        except Exception as e:
            logger.error("batch_upsert_users_unnest failed: %s", e)
            return 0

    async def delete_user(self, uuid: str) -> bool:
        """Delete user by UUID. Also cleans up connections (no FK CASCADE on partitioned table)."""
        if not self.is_connected:
            return False

        async with self.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    delete_sql(USER_CONNECTIONS_TABLE, "user_uuid = $1"), uuid
                )
                result = await conn.execute(
                    delete_sql(USERS_TABLE, "uuid = $1"), uuid
                )
                return result == "DELETE 1"

    async def get_all_user_uuids(self) -> set[str]:
        """Get set of all user UUIDs. Lightweight alternative to get_all_users() for reconciliation."""
        if not self.is_connected:
            return set()
        async with self.acquire() as conn:
            rows = await conn.fetch(select_sql(USERS_TABLE, "uuid"))
            return {str(r["uuid"]) for r in rows}

