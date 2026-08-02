"""
Nodes mixin — node CRUD, metrics snapshots, user-node traffic.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.logger import logger
from shared.db._base import _db_row_to_api_format
from shared.db_schema import (
    NODES_TABLE,
    USER_NODE_TRAFFIC_TABLE,
    NODE_METRICS_SNAPSHOTS_TABLE,
    USERS_TABLE,
)
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql


class NodesMixin:
    # ==================== Nodes ====================
    
    async def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes with raw_data in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(select_sql(NODES_TABLE, "*", "ORDER BY name"))
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_node_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get node by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(NODES_TABLE, "*", "WHERE uuid = $1"),
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_nodes_by_uuids(self, uuids: list[str]) -> Dict[str, Dict[str, Any]]:
        """Get multiple nodes by UUIDs in a single query.

        Returns:
            Dict mapping node UUID -> node info dict.
        """
        if not self.is_connected or not uuids:
            return {}

        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(NODES_TABLE, "*", "WHERE uuid::text = ANY($1)"),
                [str(u) for u in uuids]
            )
            result = {}
            for row in rows:
                node = _db_row_to_api_format(row)
                if node:
                    result[str(row['uuid'])] = node
            return result

    async def get_node_agent_token(self, uuid: str) -> Optional[str]:
        """Получить токен агента для ноды (если установлен)."""
        if not self.is_connected:
            return None

        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(NODES_TABLE, "agent_token", "WHERE uuid = $1"),
                uuid
            )
            return row["agent_token"] if row and row["agent_token"] else None

    async def get_nodes_agent_state(self) -> Dict[str, Dict[str, Any]]:
        """Per-node agent flags: has_agent_token, agent_v2_connected, agent_v2_last_ping.

        Returned dict is keyed by lowercase uuid string. The token value itself
        is NOT returned — only a boolean indicating whether it is set, to keep
        the secret off API responses.
        """
        if not self.is_connected:
            return {}

        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(NODES_TABLE, """
                        uuid,
                        (agent_token IS NOT NULL AND agent_token <> '') AS has_agent_token,
                        COALESCE(agent_v2_connected, false) AS agent_v2_connected,
                        agent_v2_last_ping,
                        agent_version
                    """)
            )

        result: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            uid = str(row["uuid"]).lower()
            last_ping = row["agent_v2_last_ping"]
            # naive datetime = UTC: без tz-суффикса JS распарсит как локальное
            # время и относительное «N назад» на фронте соврёт на часовой пояс
            if last_ping is not None and last_ping.tzinfo is None:
                ping_iso = last_ping.isoformat() + "Z"
            else:
                ping_iso = last_ping.isoformat() if last_ping else None
            result[uid] = {
                "has_agent_token": bool(row["has_agent_token"]),
                "agent_v2_connected": bool(row["agent_v2_connected"]),
                "agent_v2_last_ping": ping_iso,
                "agent_version": row["agent_version"],
            }
        return result
    
    async def get_nodes_stats(self) -> Dict[str, int]:
        """
        Get nodes statistics.
        Returns dict: {total, enabled, disabled, connected}
        """
        if not self.is_connected:
            return {"total": 0, "enabled": 0, "disabled": 0, "connected": 0}
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(NODES_TABLE, """
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE NOT is_disabled) as enabled,
                        COUNT(*) FILTER (WHERE is_disabled) as disabled,
                        COUNT(*) FILTER (WHERE is_connected AND NOT is_disabled) as connected
                    """)
            )
            return dict(row) if row else {"total": 0, "enabled": 0, "disabled": 0, "connected": 0}
    
    async def upsert_node(self, node_data: Dict[str, Any]) -> None:
        """Insert or update a node."""
        if not self.is_connected:
            return

        response = node_data.get("response", node_data)

        uuid = response.get("uuid")
        if not uuid:
            logger.warning("Cannot upsert node without UUID")
            return

        # Safely convert values that may come as strings from webhook payloads
        port = response.get("port")
        if port is not None:
            try:
                port = int(port)
            except (ValueError, TypeError):
                port = None

        traffic_limit = response.get("trafficLimitBytes")
        if traffic_limit is not None:
            try:
                traffic_limit = int(traffic_limit)
            except (ValueError, TypeError):
                traffic_limit = None

        traffic_used = response.get("trafficUsedBytes")
        if traffic_used is not None:
            try:
                traffic_used = int(traffic_used)
            except (ValueError, TypeError):
                traffic_used = None

        users_online = response.get("usersOnline")
        if users_online is not None:
            try:
                users_online = int(users_online)
            except (ValueError, TypeError):
                users_online = 0
        else:
            users_online = 0

        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    NODES_TABLE,
                    [
                        "uuid", "name", "address", "port", "is_disabled", "is_connected",
                        "traffic_limit_bytes", "traffic_used_bytes", "users_online", "updated_at", "raw_data",
                    ],
                    values="$1, $2, $3, $4, $5, $6, $7, $8, $9, NOW(), $10",
                    suffix="""
                    ON CONFLICT (uuid) DO UPDATE SET
                        name = EXCLUDED.name,
                        address = EXCLUDED.address,
                        port = EXCLUDED.port,
                        is_disabled = EXCLUDED.is_disabled,
                        is_connected = EXCLUDED.is_connected,
                        traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
                        traffic_used_bytes = EXCLUDED.traffic_used_bytes,
                        users_online = EXCLUDED.users_online,
                        updated_at = NOW(),
                        raw_data = EXCLUDED.raw_data
                    """,
                ),
                uuid,
                response.get("name"),
                response.get("address"),
                port,
                bool(response.get("isDisabled", False)),
                bool(response.get("isConnected", False)),
                traffic_limit,
                traffic_used,
                users_online,
                json.dumps(response),
            )
    
    async def bulk_upsert_nodes(self, nodes: List[Dict[str, Any]]) -> int:
        """Bulk insert or update nodes. Returns number of records processed."""
        if not self.is_connected or not nodes:
            return 0
        
        count = 0
        async with self.acquire() as conn:
            async with conn.transaction():
                for node_data in nodes:
                    try:
                        await self.upsert_node(node_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert node: %s", e)
        
        return count
    
    async def delete_node(self, uuid: str) -> bool:
        """Delete node by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(NODES_TABLE, "uuid = $1"),
                uuid
            )
            return result == "DELETE 1"
    
    async def update_node_metrics(
        self,
        node_uuid: str,
        cpu_usage: float | None = None,
        cpu_cores: int | None = None,
        memory_usage: float | None = None,
        memory_total_bytes: int | None = None,
        memory_used_bytes: int | None = None,
        disk_usage: float | None = None,
        disk_total_bytes: int | None = None,
        disk_used_bytes: int | None = None,
        disk_read_speed_bps: int | None = None,
        disk_write_speed_bps: int | None = None,
        uptime_seconds: int | None = None,
    ) -> bool:
        """Update system metrics for a node (from Node Agent)."""
        if not self.is_connected:
            return False

        async with self.acquire() as conn:
            result = await conn.execute(
                update_sql(
                    NODES_TABLE,
                    """
                        cpu_usage = $2,
                        cpu_cores = $3,
                        memory_usage = $4,
                        memory_total_bytes = $5,
                        memory_used_bytes = $6,
                        disk_usage = $7,
                        disk_total_bytes = $8,
                        disk_used_bytes = $9,
                        disk_read_speed_bps = $10,
                        disk_write_speed_bps = $11,
                        uptime_seconds = $12,
                        metrics_updated_at = NOW()
                    """,
                    "uuid = $1",
                ),
                node_uuid,
                cpu_usage,
                cpu_cores,
                memory_usage,
                memory_total_bytes,
                memory_used_bytes,
                disk_usage,
                disk_total_bytes,
                disk_used_bytes,
                disk_read_speed_bps,
                disk_write_speed_bps,
                uptime_seconds,
            )
            return result == "UPDATE 1"

    async def update_node_agent_version(self, node_uuid: str, version: str) -> bool:
        """Записать версию node-agent (репортится в каждом батче).

        UPDATE срабатывает только при отличии — коллектор зовёт это на каждый
        батч, и без гарда мы бы дёргали строку ноды раз в несколько секунд.
        """
        if not self.is_connected:
            return False
        async with self.acquire() as conn:
            result = await conn.execute(
                update_sql(
                    NODES_TABLE,
                    "agent_version = $2",
                    "uuid = $1 AND agent_version IS DISTINCT FROM $2",
                ),
                node_uuid,
                version,
            )
            return result == "UPDATE 1"

    # ==================== Node Metrics Snapshots ====================

    async def insert_node_metrics_snapshot(
        self,
        node_uuid: str,
        cpu_usage: float | None = None,
        cpu_cores: int | None = None,
        memory_usage: float | None = None,
        memory_total_bytes: int | None = None,
        memory_used_bytes: int | None = None,
        disk_usage: float | None = None,
        disk_total_bytes: int | None = None,
        disk_used_bytes: int | None = None,
        disk_read_speed_bps: int | None = None,
        disk_write_speed_bps: int | None = None,
        uptime_seconds: int | None = None,
    ) -> bool:
        """Insert a snapshot of node metrics for historical tracking."""
        if not self.is_connected:
            return False
        try:
            async with self.acquire() as conn:
                await conn.execute(
                    insert_sql(
                        NODE_METRICS_SNAPSHOTS_TABLE,
                        [
                            "node_uuid", "cpu_usage", "cpu_cores", "memory_usage",
                            "memory_total_bytes", "memory_used_bytes",
                            "disk_usage", "disk_total_bytes", "disk_used_bytes",
                            "disk_read_speed_bps", "disk_write_speed_bps", "uptime_seconds",
                        ],
                    ),
                    node_uuid, cpu_usage, cpu_cores, memory_usage,
                    memory_total_bytes, memory_used_bytes,
                    disk_usage, disk_total_bytes, disk_used_bytes,
                    disk_read_speed_bps, disk_write_speed_bps, uptime_seconds,
                )
                return True
        except Exception as e:
            logger.debug("Failed to insert metrics snapshot: %s", e)
            return False

    async def get_node_metrics_history(
        self,
        period: str = "24h",
        node_uuid: str | None = None,
    ) -> list:
        """Get averaged node metrics for the given period."""
        if not self.is_connected:
            return []

        delta_map = {"24h": 1, "7d": 7, "30d": 30, "all": 3650}
        days = delta_map.get(period, 1)

        columns = """
            s.node_uuid,
            n.name as node_name,
            ROUND(AVG(s.cpu_usage)::numeric, 1) as avg_cpu,
            ROUND(AVG(s.memory_usage)::numeric, 1) as avg_memory,
            ROUND(AVG(s.disk_usage)::numeric, 1) as avg_disk,
            ROUND(MAX(s.cpu_usage)::numeric, 1) as max_cpu,
            ROUND(MAX(s.memory_usage)::numeric, 1) as max_memory,
            ROUND(MAX(s.disk_usage)::numeric, 1) as max_disk,
            COUNT(*) as samples_count
        """
        suffix = "s JOIN nodes n ON n.uuid = s.node_uuid WHERE s.created_at >= NOW() - make_interval(days => $1)"
        params: list = [days]

        if node_uuid:
            suffix += " AND s.node_uuid = $2::uuid"
            params.append(node_uuid)

        suffix += " GROUP BY s.node_uuid, n.name ORDER BY n.name"

        query = select_sql(NODE_METRICS_SNAPSHOTS_TABLE, columns, suffix)

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(query, *params)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("get_node_metrics_history failed: %s", e)
            return []

    async def get_node_metrics_timeseries(
        self,
        period: str = "24h",
        node_uuid: str | None = None,
    ) -> list:
        """Get time-bucketed average metrics for charting.

        24h -> hourly, 7d -> 6h, 30d -> daily.
        """
        if not self.is_connected:
            return []

        delta_map = {"24h": 1, "7d": 7, "30d": 30, "all": 3650}
        trunc_map = {"24h": "hour", "7d": "hour", "30d": "day", "all": "day"}
        # For 7d we truncate to hour then floor to 6h in Python for simplicity
        days = delta_map.get(period, 1)
        trunc = trunc_map.get(period, "hour")

        columns = f"""
            date_trunc('{trunc}', s.created_at) as bucket,
            s.node_uuid,
            n.name as node_name,
            ROUND(AVG(s.cpu_usage)::numeric, 1) as avg_cpu,
            ROUND(AVG(s.memory_usage)::numeric, 1) as avg_memory,
            ROUND(AVG(s.disk_usage)::numeric, 1) as avg_disk
        """
        suffix = "s JOIN nodes n ON n.uuid = s.node_uuid WHERE s.created_at >= NOW() - make_interval(days => $1)"
        params: list = [days]
        if node_uuid:
            suffix += " AND s.node_uuid = $2::uuid"
            params.append(node_uuid)
        suffix += f" GROUP BY bucket, s.node_uuid, n.name ORDER BY bucket"

        query = select_sql(NODE_METRICS_SNAPSHOTS_TABLE, columns, suffix)

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(query, *params)
                result = [dict(r) for r in rows]
                # For 7d period, floor hourly buckets to 6h
                if period == "7d":
                    for row in result:
                        b = row["bucket"]
                        if b:
                            row["bucket"] = b.replace(hour=(b.hour // 6) * 6, minute=0, second=0, microsecond=0)
                return result
        except Exception as e:
            logger.error("get_node_metrics_timeseries failed: %s", e)
            return []

    async def cleanup_old_metrics_snapshots(self, retention_days: int = 30, batch_size: int = 5000) -> int:
        """Delete metrics snapshots older than retention_days in batches."""
        if not self.is_connected:
            return 0
        total = 0
        max_batches = 1000
        try:
            for _ in range(max_batches):
                async with self.acquire() as conn:
                    result = await conn.execute(
                        delete_sql(
                            NODE_METRICS_SNAPSHOTS_TABLE,
                            f"""id IN (
                                SELECT id FROM {NODE_METRICS_SNAPSHOTS_TABLE}
                                WHERE created_at < NOW() - make_interval(days => $1)
                                ORDER BY created_at
                                LIMIT $2
                            )""",
                        ),
                        retention_days, batch_size,
                    )
                    deleted = int(result.split()[-1]) if result and result.split() else 0
                    total += deleted
                    if deleted < batch_size:
                        break
                await asyncio.sleep(0.1)
            else:
                logger.warning("cleanup_old_metrics_snapshots hit max_batches limit (%d batches, %d rows)", max_batches, total)
            return total
        except Exception as e:
            logger.error("cleanup_old_metrics_snapshots failed: %s", e)
            return total


    # ==================== User Node Traffic Methods ====================

    async def upsert_user_node_traffic(
        self, user_uuid: str, node_uuid: str, traffic_bytes: int
    ) -> None:
        """Upsert traffic record for a user on a specific node."""
        if not self.is_connected:
            return
        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(
                    USER_NODE_TRAFFIC_TABLE,
                    ["user_uuid", "node_uuid", "traffic_bytes", "synced_at"],
                    values="$1::uuid, $2::uuid, $3, NOW()",
                    suffix="""
                    ON CONFLICT (user_uuid, node_uuid)
                    DO UPDATE SET traffic_bytes = $3, synced_at = NOW()
                    """,
                ),
                user_uuid, node_uuid, traffic_bytes,
            )

    async def batch_upsert_user_node_traffic(
        self, records: List[tuple]
    ) -> int:
        """Batch upsert traffic records via UNNEST. Each record: (user_uuid, node_uuid, traffic_bytes)."""
        if not self.is_connected or not records:
            return 0
        user_uuids = [r[0] for r in records]
        node_uuids = [r[1] for r in records]
        traffic_bytes = [r[2] for r in records]
        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    f"""
                    INSERT INTO {USER_NODE_TRAFFIC_TABLE} (user_uuid, node_uuid, traffic_bytes, synced_at)
                    SELECT u::uuid, n::uuid, t, NOW()
                    FROM UNNEST($1::text[], $2::text[], $3::bigint[]) AS r(u, n, t)
                    ON CONFLICT (user_uuid, node_uuid)
                    DO UPDATE SET traffic_bytes = EXCLUDED.traffic_bytes, synced_at = NOW()
                    """,
                    user_uuids, node_uuids, traffic_bytes,
                )
                return int(result.split()[-1]) if result else 0
        except Exception as e:
            logger.warning("batch_upsert_user_node_traffic failed: %s", e)
            return 0

    async def get_username_to_uuid_map(self, usernames: List[str]) -> Dict[str, str]:
        """Get a mapping of username -> uuid for a list of usernames."""
        if not self.is_connected or not usernames:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "username, uuid::text", "WHERE LOWER(username) = ANY(SELECT LOWER(x) FROM unnest($1::text[]) AS x)"),
                usernames,
            )
            return {r["username"].lower(): r["uuid"] for r in rows}

    async def get_node_users_traffic(self, node_uuid: str) -> List[Dict[str, Any]]:
        """Get all users' traffic on a specific node, joined with username.
        Excludes expired/disabled users.
        """
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USER_NODE_TRAFFIC_TABLE,
                    """
                    unt.user_uuid, u.username, unt.traffic_bytes,
                    n.name as node_name
                    """,
                    """
                    unt
                    JOIN users u ON unt.user_uuid = u.uuid
                    JOIN nodes n ON unt.node_uuid = n.uuid
                    WHERE unt.node_uuid = $1::uuid
                      AND u.status NOT IN ('EXPIRED', 'DISABLED', 'LIMITED')
                    ORDER BY unt.traffic_bytes DESC
                    """,
                ),
                node_uuid,
            )
            return [dict(r) for r in rows]

    async def get_all_user_node_traffic_above(
        self, threshold_bytes: int
    ) -> List[Dict[str, Any]]:
        """Get all user-node pairs where traffic exceeds threshold.
        Excludes expired/disabled users.
        """
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USER_NODE_TRAFFIC_TABLE,
                    """
                    unt.user_uuid, u.username, unt.node_uuid,
                    n.name as node_name, unt.traffic_bytes
                    """,
                    """
                    unt
                    JOIN users u ON unt.user_uuid = u.uuid
                    JOIN nodes n ON unt.node_uuid = n.uuid
                    WHERE unt.traffic_bytes >= $1
                      AND u.status NOT IN ('EXPIRED', 'DISABLED', 'LIMITED')
                    ORDER BY unt.traffic_bytes DESC
                    """,
                ),
                threshold_bytes,
            )
            return [dict(r) for r in rows]

    async def get_raw_traffic_sums(self) -> Dict[str, int]:
        """Get accumulated raw traffic (without node multipliers) per user.

        Returns dict mapping user_uuid -> raw_used_traffic_bytes from users table.
        Only returns users with raw_used_traffic_bytes > 0.
        """
        if not self.is_connected:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "uuid::text, raw_used_traffic_bytes", "WHERE raw_used_traffic_bytes > 0")
            )
            return {r["uuid"]: int(r["raw_used_traffic_bytes"]) for r in rows}

    async def increment_raw_traffic(self, deltas: Dict[str, int]) -> None:
        """Increment raw_used_traffic_bytes for multiple users.

        deltas: dict mapping user_uuid -> bytes to add.
        """
        if not self.is_connected or not deltas:
            return
        async with self.acquire() as conn:
            async with conn.transaction():
                for user_uuid, delta in deltas.items():
                    if delta > 0:
                        await conn.execute(
                            update_sql(USERS_TABLE, "raw_used_traffic_bytes = raw_used_traffic_bytes + $2", "uuid = $1::uuid"),
                            user_uuid, delta,
                        )

    async def get_used_traffic_map(self, user_uuids: List[str]) -> Dict[str, int]:
        """Get current used_traffic_bytes for a list of users."""
        if not self.is_connected or not user_uuids:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "uuid::text, COALESCE(used_traffic_bytes, 0) as used", "WHERE uuid = ANY($1::uuid[])"),
                user_uuids,
            )
            return {r["uuid"]: int(r["used"]) for r in rows}

    async def get_used_traffic_map_by_id(self, panel_ids: List[int]) -> Dict[int, int]:
        """Get current used_traffic_bytes for a list of panel numeric user ids (Remnawave v3)."""
        if not self.is_connected or not panel_ids:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USERS_TABLE, "id, COALESCE(used_traffic_bytes, 0) as used", "WHERE id = ANY($1::bigint[])"),
                panel_ids,
            )
            return {int(r["id"]): int(r["used"]) for r in rows}

    async def reset_raw_traffic(self, user_uuids: List[str]) -> None:
        """Reset raw_used_traffic_bytes to 0 for specified users (traffic reset detected)."""
        if not self.is_connected or not user_uuids:
            return
        async with self.acquire() as conn:
            await conn.execute(
                update_sql(USERS_TABLE, "raw_used_traffic_bytes = 0", "uuid = ANY($1::uuid[])"),
                user_uuids,
            )

    async def reset_raw_traffic_by_id(self, panel_ids: List[int]) -> None:
        """Reset raw_used_traffic_bytes to 0 for specified panel numeric user ids (Remnawave v3)."""
        if not self.is_connected or not panel_ids:
            return
        async with self.acquire() as conn:
            await conn.execute(
                update_sql(USERS_TABLE, "raw_used_traffic_bytes = 0", "id = ANY($1::bigint[])"),
                panel_ids,
            )

    async def get_user_node_traffic_snapshot(self) -> Dict[str, Dict[str, int]]:
        """Get current snapshot of user_node_traffic.

        Returns dict: {user_uuid: {node_uuid: traffic_bytes}}.
        """
        if not self.is_connected:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USER_NODE_TRAFFIC_TABLE, "user_uuid::text, node_uuid::text, traffic_bytes")
            )
        result: Dict[str, Dict[str, int]] = {}
        for r in rows:
            uid = r["user_uuid"]
            if uid not in result:
                result[uid] = {}
            result[uid][r["node_uuid"]] = int(r["traffic_bytes"])
        return result

