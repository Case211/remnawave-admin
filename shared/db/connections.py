"""
Connections mixin — user connections, partitioning, torrent events.
"""
import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from shared.logger import logger
from shared.db_schema import USER_CONNECTIONS_TABLE, VIOLATIONS_TABLE, USERS_TABLE, NODES_TABLE
from shared.db_query import select_sql, insert_sql, update_sql


class ConnectionsMixin:
    # ==================== User Connections (for future device tracking) ====================

    async def get_user_connection_history(
        self, user_uuid: str, days: int = 30, limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """История подключений юзера (сессии) — для таймлайна."""
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""SELECT uc.id, uc.ip_address, uc.node_uuid::text AS node_uuid,
                           uc.connected_at, uc.disconnected_at, uc.device_info,
                           n.name AS node_name
                    FROM {USER_CONNECTIONS_TABLE} uc
                    LEFT JOIN {NODES_TABLE} n ON n.uuid = uc.node_uuid
                    WHERE uc.user_uuid = $1::uuid
                      AND uc.connected_at >= NOW() - INTERVAL '1 day' * $2
                    ORDER BY uc.connected_at DESC
                    LIMIT $3""",
                user_uuid, days, limit,
            )
        out: List[Dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            for k in ("connected_at", "disconnected_at"):
                if d.get(k) is not None:
                    d[k] = d[k].isoformat()
            if isinstance(d.get("device_info"), str):
                try:
                    d["device_info"] = json.loads(d["device_info"])
                except (ValueError, TypeError):
                    d["device_info"] = None
            out.append(d)
        return out

    async def add_user_connection(
        self,
        user_uuid: str,
        ip_address: str,
        node_uuid: Optional[str] = None,
        device_info: Optional[Dict[str, Any]] = None,
        connected_at: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Add or update a user connection record.
        Если есть активное подключение с этим IP, обновляет время подключения.
        Иначе создаёт новую запись.
        Returns connection ID.
        """
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            async with conn.transaction():
                # Проверяем, есть ли уже активное подключение с этим IP для этого пользователя
                # Включаем connected_at в SELECT чтобы избежать лишнего round-trip
                existing = await conn.fetchrow(
                    select_sql(
                        USER_CONNECTIONS_TABLE,
                        "id, connected_at",
                        "WHERE user_uuid = $1 AND ip_address = $2 AND disconnected_at IS NULL ORDER BY connected_at DESC LIMIT 1",
                    ),
                    user_uuid, ip_address
                )

                if existing:
                    conn_id = existing['id']
                    existing_time = existing['connected_at']

                    # Нормализуем timezone — приводим к naive UTC для корректного сравнения
                    def _to_naive_utc(dt):
                        if dt is None:
                            return None
                        if isinstance(dt, str):
                            try:
                                dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                            except ValueError:
                                return None
                        if not isinstance(dt, datetime):
                            return None
                        if dt.tzinfo:
                            from datetime import timezone as tz
                            dt = dt.astimezone(tz.utc).replace(tzinfo=None)
                        return dt

                    existing_utc = _to_naive_utc(existing_time)
                    connected_utc = _to_naive_utc(connected_at)

                    if existing_utc and connected_utc:
                        update_time = max(existing_utc, connected_utc)
                    elif connected_utc:
                        update_time = connected_utc
                    elif existing_utc:
                        update_time = existing_utc
                    else:
                        update_time = datetime.utcnow()

                    await conn.execute(
                        update_sql(
                            USER_CONNECTIONS_TABLE,
                            "connected_at = $1, node_uuid = COALESCE($2, node_uuid)",
                            "id = $3",
                        ),
                        update_time, node_uuid, conn_id
                    )
                    result_id = conn_id
                else:
                    # Создаём новую запись
                    insert_time = connected_at if connected_at else datetime.utcnow()
                    result_id = await conn.fetchval(
                        insert_sql(
                            USER_CONNECTIONS_TABLE,
                            ["user_uuid", "ip_address", "node_uuid", "device_info", "connected_at"],
                            returning="id",
                        ),
                        user_uuid, ip_address, node_uuid,
                        json.dumps(device_info) if device_info else None,
                        insert_time
                    )

                # Закрываем старые подключения с другими IP (общее для обоих веток)
                await conn.execute(
                    update_sql(
                        USER_CONNECTIONS_TABLE,
                        "disconnected_at = NOW()",
                        "user_uuid = $1 AND ip_address != $2 AND disconnected_at IS NULL AND connected_at < NOW() - INTERVAL '2 minutes'",
                    ),
                    user_uuid, ip_address
                )

                return result_id

    async def batch_upsert_connections(
        self,
        connections: list,
        stale_threshold_minutes: int = 2,
    ) -> Dict[str, int]:
        """
        Batch upsert connections and close stale ones in a single transaction.
        Replaces per-connection add_user_connection calls for collector batches.

        Args:
            connections: List of dicts with keys:
                - user_uuid: str
                - ip_address: str
                - node_uuid: str | None
                - device_info: dict | None
                - connected_at: datetime | None
            stale_threshold_minutes: Close other-IP connections older than this

        Returns:
            {"upserted": int, "closed_stale": int}
        """
        if not self.is_connected or not connections:
            return {"upserted": 0, "closed_stale": 0}

        # Deduplicate: keep latest connected_at per (user_uuid, ip_address)
        # PostgreSQL raises error if ON CONFLICT targets same row twice in one INSERT
        deduped: dict = {}
        for c in connections:
            key = (str(c["user_uuid"]), str(c["ip_address"]))
            ca = c.get("connected_at")
            existing = deduped.get(key)
            if existing is None or (ca and ca > (existing.get("connected_at") or datetime.min)):
                deduped[key] = c
        # Sort by (user_uuid, ip_address) to ensure consistent lock ordering
        # and prevent deadlocks when concurrent batches touch the same rows
        connections = [deduped[k] for k in sorted(deduped.keys())]

        user_uuids = []
        ip_addresses = []
        node_uuids = []
        device_infos = []
        connected_ats = []

        for c in connections:
            user_uuids.append(str(c["user_uuid"]))
            ip = str(c["ip_address"])
            if '/' in ip:
                ip = ip.split('/')[0]
            ip_addresses.append(ip)
            node_uuids.append(str(c["node_uuid"]) if c.get("node_uuid") else None)
            device_infos.append(json.dumps(c["device_info"]) if c.get("device_info") else None)
            ca = c.get("connected_at")
            if ca and isinstance(ca, str):
                try:
                    ca = datetime.fromisoformat(ca.replace('Z', '+00:00'))
                except ValueError:
                    ca = None
            connected_ats.append(ca or datetime.utcnow())

        async with self.acquire() as conn:
            async with conn.transaction():
                # Detect ip_address column type (INET vs VARCHAR) — cache once
                if not hasattr(self, '_ip_col_is_inet'):
                    col_type = await conn.fetchval(
                        "SELECT data_type FROM information_schema.columns "
                        "WHERE table_name = 'user_connections' AND column_name = 'ip_address'"
                    )
                    self._ip_col_is_inet = (col_type == 'inet')

                ip_cast = "::inet" if self._ip_col_is_inet else ""

                # Сравнивать ip_address НАПРЯМУЮ, без ::text с обеих сторон.
                # Совместимость INET/VARCHAR держит ip_cast на стороне значения
                # (см. 75af1947) — приведение колонки к тексту поверх него уже
                # ничего не чинит, а на INET-инстансах мешает: ip_address
                # выпадает из Index Cond частичного индекса
                # (user_uuid, ip_address) WHERE disconnected_at IS NULL
                # в Filter, и строки юзера читаются все. На VARCHAR приведение
                # безвредно — там оно no-op и планировщик его снимает сам.

                # 1a. Update existing active connections (match by user_uuid + ip_address)
                # Two-step approach: partitioned tables require partition key in
                # unique index, so ON CONFLICT (user_uuid, ip_address) alone won't
                # work. Instead: UPDATE existing rows first, then INSERT truly new.
                update_result = await conn.execute(
                    f"""
                    UPDATE {USER_CONNECTIONS_TABLE} uc
                    SET connected_at = GREATEST(uc.connected_at, batch.ca),
                        node_uuid = COALESCE(batch.n, uc.node_uuid),
                        device_info = COALESCE(batch.d, uc.device_info)
                    FROM (
                        SELECT u::uuid AS uid, u_ip{ip_cast} AS ip,
                               n::uuid AS n, d::jsonb AS d, COALESCE(t, NOW()) AS ca
                        FROM UNNEST($1::text[], $2::text[], $3::text[], $4::text[], $5::timestamptz[])
                            AS t(u, u_ip, n, d, t)
                    ) batch
                    WHERE uc.user_uuid = batch.uid
                      AND uc.ip_address = batch.ip
                      AND uc.disconnected_at IS NULL
                    """,
                    user_uuids, ip_addresses, node_uuids, device_infos, connected_ats,
                )
                updated = int(update_result.split()[-1]) if update_result else 0

                # 1b. Insert truly new connections (no existing active row for user+ip)
                insert_result = await conn.execute(
                    f"""
                    INSERT INTO {USER_CONNECTIONS_TABLE} (user_uuid, ip_address, node_uuid, device_info, connected_at)
                    SELECT u::uuid, u_ip{ip_cast}, n::uuid, d::jsonb, COALESCE(t, NOW())
                    FROM UNNEST($1::text[], $2::text[], $3::text[], $4::text[], $5::timestamptz[])
                        AS t(u, u_ip, n, d, t)
                    WHERE NOT EXISTS (
                        SELECT 1 FROM {USER_CONNECTIONS_TABLE} uc
                        WHERE uc.user_uuid = u::uuid
                          AND uc.ip_address = u_ip{ip_cast}
                          AND uc.disconnected_at IS NULL
                    )
                    """,
                    user_uuids, ip_addresses, node_uuids, device_infos, connected_ats,
                )
                inserted = int(insert_result.split()[-1]) if insert_result else 0
                upserted = updated + inserted

                # 2. Close stale connections — IPs not in this batch, older than threshold
                # Cast ip_address to text for comparison (works with both INET and VARCHAR)
                close_result = await conn.execute(
                    f"""
                    UPDATE {USER_CONNECTIONS_TABLE} uc
                    SET disconnected_at = NOW()
                    FROM (
                        SELECT DISTINCT u::uuid AS uid, i{ip_cast} AS ip
                        FROM UNNEST($1::text[], $2::text[]) AS t(u, i)
                    ) batch
                    WHERE uc.user_uuid = batch.uid
                      AND uc.ip_address != batch.ip
                      AND uc.disconnected_at IS NULL
                      AND uc.connected_at < NOW() - make_interval(mins => $3)
                    """,
                    user_uuids, ip_addresses, stale_threshold_minutes,
                )
                closed = int(close_result.split()[-1]) if close_result else 0

        return {"upserted": upserted, "closed_stale": closed}

    async def get_user_active_connections(
        self,
        user_uuid: str,
        limit: int = 100,
        max_age_minutes: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get active (not disconnected) connections for a user.
        
        Args:
            user_uuid: UUID пользователя
            limit: Максимальное количество записей
            max_age_minutes: Максимальный возраст подключения в минутах (по умолчанию 5 минут)
                           Подключения старше этого возраста считаются неактивными
        """
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USER_CONNECTIONS_TABLE,
                    "*",
                    "WHERE user_uuid = $1 AND disconnected_at IS NULL AND connected_at > NOW() - make_interval(mins => $2) ORDER BY connected_at DESC LIMIT $3",
                ),
                user_uuid, int(max_age_minutes), limit
            )
            return [dict(row) for row in rows]
    
    async def get_user_unique_ips_count(
        self,
        user_uuid: str,
        since_hours: int = 24
    ) -> int:
        """Get count of unique IP addresses for a user in the last N hours."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.fetchval(
                select_sql(
                    USER_CONNECTIONS_TABLE,
                    "COUNT(DISTINCT ip_address)",
                    "WHERE user_uuid = $1 AND connected_at > NOW() - make_interval(hours => $2)",
                ),
                user_uuid, int(since_hours)
            )
            return result or 0
    
    async def get_unique_ips_in_window(
        self,
        user_uuid: str,
        window_minutes: int = 60
    ) -> int:
        """
        Get count of unique IP addresses for a user within a time window.
        
        Args:
            user_uuid: UUID пользователя
            window_minutes: Временное окно в минутах (по умолчанию 60 минут)
        
        Returns:
            Количество уникальных IP адресов в указанном окне
        """
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.fetchval(
                select_sql(
                    USER_CONNECTIONS_TABLE,
                    "COUNT(DISTINCT ip_address)",
                    "WHERE user_uuid = $1 AND connected_at > NOW() - make_interval(mins => $2)",
                ),
                user_uuid, int(window_minutes)
            )
            return result or 0
    
    async def get_simultaneous_connections(
        self,
        user_uuid: str
    ) -> int:
        """
        Get count of simultaneous (active, not disconnected) connections for a user.
        
        Args:
            user_uuid: UUID пользователя
        
        Returns:
            Количество одновременных активных подключений
        """
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.fetchval(
                select_sql(
                    USER_CONNECTIONS_TABLE,
                    "COUNT(*)",
                    "WHERE user_uuid = $1 AND disconnected_at IS NULL AND connected_at > NOW() - INTERVAL '10 minutes'",
                ),
                user_uuid
            )
            return result or 0

    async def get_user_connection_stats_combined(
        self,
        user_uuid: str,
        window_minutes: int = 60,
        max_age_minutes: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Get all connection stats in a single query using subqueries (4 queries → 1)."""
        if not self.is_connected:
            return None

        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                SELECT
                    (SELECT COUNT(*) FROM {USER_CONNECTIONS_TABLE}
                     WHERE user_uuid = $1 AND disconnected_at IS NULL
                       AND connected_at > NOW() - make_interval(mins => $3)
                    ) AS active_count,
                    (SELECT COUNT(DISTINCT ip_address) FROM {USER_CONNECTIONS_TABLE}
                     WHERE user_uuid = $1
                       AND connected_at > NOW() - make_interval(mins => $2)
                    ) AS unique_ips,
                    (SELECT COUNT(*) FROM {USER_CONNECTIONS_TABLE}
                     WHERE user_uuid = $1 AND disconnected_at IS NULL
                       AND connected_at > NOW() - INTERVAL '10 minutes'
                    ) AS simultaneous,
                    (SELECT COUNT(*) FROM {USER_CONNECTIONS_TABLE}
                     WHERE user_uuid = $1
                       AND connected_at > NOW() - INTERVAL '1 day'
                    ) AS history_24h_count,
                    (SELECT MAX(connected_at) FROM {USER_CONNECTIONS_TABLE}
                     WHERE user_uuid = $1 AND disconnected_at IS NULL
                       AND connected_at > NOW() - make_interval(mins => $3)
                    ) AS last_connection_at
                """,
                user_uuid, window_minutes, max_age_minutes
            )
            if not row:
                return None
            return dict(row)

    async def get_connection_history(
        self,
        user_uuid: str,
        days: int = 7,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        """
        Get connection history for a user.

        Args:
            user_uuid: UUID пользователя
            days: Количество дней истории (по умолчанию 7)
            limit: Максимальное количество записей (по умолчанию 200)
        
        Returns:
            Список подключений с информацией об IP, ноде, времени подключения/отключения
        """
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USER_CONNECTIONS_TABLE,
                    """
                        id,
                        user_uuid,
                        ip_address,
                        node_uuid,
                        connected_at,
                        disconnected_at,
                        device_info
                    """,
                    "WHERE user_uuid = $1 AND connected_at > NOW() - make_interval(days => $2) ORDER BY connected_at DESC LIMIT $3",
                ),
                user_uuid,
                int(days),
                limit
            )
            return [dict(row) for row in rows]
    
    async def get_active_connections(
        self,
        user_uuid: str,
        limit: int = 100,
        max_age_minutes: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get active (not disconnected) connections for a user.
        Alias for get_user_active_connections for consistency with plan.
        
        Args:
            user_uuid: UUID пользователя
            limit: Максимальное количество записей
            max_age_minutes: Максимальный возраст подключения в минутах
        
        Returns:
            Список активных подключений
        """
        return await self.get_user_active_connections(user_uuid, limit, max_age_minutes)
    
    async def close_user_connection(self, connection_id: int) -> bool:
        """Mark a connection as disconnected."""
        if not self.is_connected:
            return False

        async with self.acquire() as conn:
            result = await conn.execute(
                update_sql(
                    USER_CONNECTIONS_TABLE,
                    "disconnected_at = NOW()",
                    "id = $1 AND disconnected_at IS NULL",
                ),
                connection_id
            )
            return result == "UPDATE 1"

    async def close_user_connections_batch(self, connection_ids: list) -> int:
        """Close multiple connections in a single batch UPDATE."""
        if not self.is_connected or not connection_ids:
            return 0

        async with self.acquire() as conn:
            result = await conn.execute(
                update_sql(
                    USER_CONNECTIONS_TABLE,
                    "disconnected_at = NOW()",
                    "id = ANY($1) AND disconnected_at IS NULL",
                ),
                connection_ids
            )
            return int(result.split()[-1]) if result else 0

    async def cleanup_old_connections(self, retention_days: int = 30, batch_size: int = 5000) -> int:
        """Drop old partitions or delete old rows from user_connections."""
        if not self.is_connected:
            return 0
        total = 0
        try:
            async with self.acquire() as conn:
                # Try partition-based cleanup: find and detach+drop old partitions
                partitions = await conn.fetch(
                    """
                    SELECT c.relname, pg_get_expr(c.relpartbound, c.oid) AS bound_expr
                    FROM pg_inherits i
                    JOIN pg_class p ON i.inhparent = p.oid
                    JOIN pg_class c ON i.inhrelid = c.oid
                    WHERE p.relname = 'user_connections'
                      AND c.relname != 'user_connections_default'
                    ORDER BY c.relname
                    """,
                )
                if partitions:
                    import re
                    from datetime import datetime, timedelta, timezone
                    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
                    for part in partitions:
                        name = part["relname"]
                        if not re.match(r'^user_connections_p\d{4}_\d{2}$', name):
                            continue
                        bound = part["bound_expr"] or ""
                        if " TO ('" in bound:
                            to_str = bound.split(" TO ('")[1].split("')")[0]
                            try:
                                upper = datetime.fromisoformat(to_str).replace(tzinfo=timezone.utc)
                                if upper <= cutoff:
                                    await conn.execute(
                                        f"ALTER TABLE {USER_CONNECTIONS_TABLE} DETACH PARTITION {name}"
                                    )
                                    await conn.execute(f"DROP TABLE {name}")
                                    logger.info("Dropped partition %s", name)
                                    total += 1
                            except (ValueError, IndexError):
                                pass
                    if total > 0:
                        return total

            # Fallback: non-partitioned table or no old partitions — batched DELETE
            max_batches = 1000
            for _ in range(max_batches):
                async with self.acquire() as conn:
                    result = await conn.execute(
                        f"""
                        DELETE FROM {USER_CONNECTIONS_TABLE}
                        WHERE id IN (
                            SELECT id FROM {USER_CONNECTIONS_TABLE}
                            WHERE disconnected_at IS NOT NULL
                              AND connected_at < NOW() - make_interval(days => $1)
                            ORDER BY connected_at
                            LIMIT $2
                        )
                        """,
                        retention_days, batch_size,
                    )
                    deleted = int(result.split()[-1]) if result and result.split() else 0
                    total += deleted
                    if deleted < batch_size:
                        break
                await asyncio.sleep(0.1)
            else:
                logger.warning("cleanup_old_connections hit max_batches limit (%d batches, %d rows)", max_batches, total)
            return total
        except Exception as e:
            logger.error("cleanup_old_connections failed: %s", e)
            return total

    async def ensure_connection_partitions(self, months_ahead: int = 3) -> int:
        """Auto-create future monthly partitions for user_connections."""
        if not self.is_connected:
            return 0
        try:
            async with self.acquire() as conn:
                is_partitioned = await conn.fetchval(
                    "SELECT COUNT(*) FROM pg_inherits i JOIN pg_class p ON i.inhparent = p.oid WHERE p.relname = 'user_connections'"
                )
                if not is_partitioned:
                    return 0

                # One-time fix: strip CIDR suffixes from ip_address after INET→VARCHAR migration
                fixed = await conn.execute(
                    update_sql(USER_CONNECTIONS_TABLE, "ip_address = split_part(ip_address, '/', 1)", "ip_address LIKE '%/%'")
                )
                fixed_count = int(fixed.split()[-1]) if fixed else 0
                if fixed_count > 0:
                    logger.info("Stripped CIDR suffix from %d ip_address values", fixed_count)

                from datetime import datetime, timezone
                now = datetime.now(timezone.utc)
                created = 0
                for offset in range(months_ahead + 1):
                    month = now.month + offset
                    year = now.year + (month - 1) // 12
                    month = (month - 1) % 12 + 1
                    next_month = month + 1
                    next_year = year + (next_month - 1) // 12
                    next_month = (next_month - 1) % 12 + 1

                    part_name = f"user_connections_p{year}_{month:02d}"
                    from_date = f"{year}-{month:02d}-01"
                    to_date = f"{next_year}-{next_month:02d}-01"

                    exists = await conn.fetchval(
                        "SELECT 1 FROM pg_class WHERE relname = $1", part_name
                    )
                    if not exists:
                        await conn.execute(f"""
                            CREATE TABLE {part_name}
                            PARTITION OF {USER_CONNECTIONS_TABLE}
                            FOR VALUES FROM ('{from_date}') TO ('{to_date}')
                        """)
                        created += 1
                        logger.info("Created partition %s (%s to %s)", part_name, from_date, to_date)

                return created
        except Exception as e:
            logger.warning("ensure_connection_partitions failed: %s", e)
            return 0

    # ==================== Torrent Events ====================

    async def save_torrent_event(
        self,
        user_uuid: str,
        node_uuid: str,
        ip_address: str,
        destination: str,
        inbound_tag: str = "",
        outbound_tag: str = "TORRENT",
        detected_at=None,
        detected_by: str = "xray_routing",
    ):
        """Save a raw torrent event to the torrent_events table."""
        if not self.is_connected:
            return None
        try:
            async with self.acquire() as conn:
                return await conn.fetchval(
                    """
                    INSERT INTO torrent_events (
                        user_uuid, node_uuid, ip_address, destination,
                        inbound_tag, outbound_tag, detected_at, detected_by
                    ) VALUES ($1, $2, $3, $4, $5, $6, COALESCE($7, NOW()), $8)
                    RETURNING id
                    """,
                    user_uuid, node_uuid, ip_address, destination,
                    inbound_tag, outbound_tag, detected_at, detected_by,
                )
        except Exception as e:
            logger.error("save_torrent_event failed: %s", e, exc_info=True)
            return None

    async def batch_save_torrent_events(self, events: list) -> int:
        """
        Batch INSERT торрент-событий через UNNEST (один round-trip вместо N).

        Args:
            events: Список словарей с ключами:
                user_uuid, node_uuid, ip_address, destination,
                inbound_tag (опц.), outbound_tag (опц.), detected_at (опц.)

        Returns:
            Количество вставленных записей.
        """
        if not self.is_connected or not events:
            return 0
        try:
            user_uuids = []
            node_uuids = []
            ip_addresses = []
            destinations = []
            inbound_tags = []
            outbound_tags = []
            detected_ats = []
            detected_bys = []

            for ev in events:
                user_uuids.append(ev["user_uuid"])
                node_uuids.append(ev["node_uuid"])
                ip_addresses.append(ev["ip_address"])
                destinations.append(ev["destination"])
                inbound_tags.append(ev.get("inbound_tag", ""))
                outbound_tags.append(ev.get("outbound_tag", "TORRENT"))
                detected_ats.append(ev.get("detected_at"))
                detected_bys.append(ev.get("detected_by") or "xray_routing")

            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    INSERT INTO torrent_events (
                        user_uuid, node_uuid, ip_address, destination,
                        inbound_tag, outbound_tag, detected_at, detected_by
                    )
                    SELECT u::uuid, n::uuid, ip, dst, itag, otag, COALESCE(da, NOW()), db
                    FROM UNNEST(
                        $1::text[], $2::text[], $3::text[], $4::text[],
                        $5::text[], $6::text[], $7::timestamptz[], $8::text[]
                    ) AS t(u, n, ip, dst, itag, otag, da, db)
                    """,
                    user_uuids, node_uuids, ip_addresses, destinations,
                    inbound_tags, outbound_tags, detected_ats, detected_bys,
                )
                return int(result.split()[-1]) if result else 0
        except Exception as e:
            logger.error("batch_save_torrent_events failed: %s", e)
            return 0

    async def count_recent_torrent_events(self, user_uuid: str, minutes: int = 30) -> int:
        """Сколько торрент-событий набралось у пользователя за окно.

        По этому числу отделяют обмен от шума: у настоящего роя счёт идёт на
        сотни за минуты, у ложного срабатывания событие ровно одно.
        """
        if not self.is_connected:
            return 0
        try:
            async with self.acquire() as conn:
                value = await conn.fetchval(
                    "SELECT count(*) FROM torrent_events "
                    "WHERE user_uuid = $1::uuid "
                    "AND detected_at > NOW() - make_interval(mins => $2)",
                    user_uuid, minutes,
                )
            return int(value or 0)
        except Exception as e:
            logger.warning("count_recent_torrent_events failed: %s", e)
            return 0

    async def shared_torrent_destinations(
        self, destinations: list, hours: int = 24,
    ) -> set:
        """Адреса из списка, за которыми в окне стоял не один пользователь.

        Вердикт nDPI живёт на адресе назначения: за адресом мессенджера или
        CDN сидит пол-ноды, и один поток сделал бы нарушителями всех, кто
        туда ходил. Обвинять по такому адресу нельзя — привязка недоказуема.
        """
        if not self.is_connected or not destinations:
            return set()
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT destination
                    FROM torrent_events
                    WHERE destination = ANY($1::text[])
                      AND detected_at > NOW() - make_interval(hours => $2)
                    GROUP BY destination
                    HAVING count(DISTINCT user_uuid) > 1
                    """,
                    list({str(d) for d in destinations if d}), hours,
                )
            return {r["destination"] for r in rows}
        except Exception as e:
            logger.warning("shared_torrent_destinations failed: %s", e)
            return set()

    async def get_recent_torrent_violation(self, user_uuid: str, minutes: int = 10):
        """Check if a torrent-type violation exists for this user within the last N minutes."""
        if not self.is_connected:
            return None
        try:
            async with self.acquire() as conn:
                return await conn.fetchval(
                    select_sql(
                        VIOLATIONS_TABLE,
                        "id",
                        "WHERE user_uuid = $1 AND detected_at > NOW() - make_interval(mins => $2) AND 'Torrent traffic detected' = ANY(reasons)",
                    ),
                    user_uuid, minutes,
                )
        except Exception as e:
            logger.error("get_recent_torrent_violation failed: %s", e)
            return None

    async def get_torrent_stats(self, days: int = 7) -> dict:
        """Get torrent event statistics for the given period."""
        if not self.is_connected:
            return {}
        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total_events,
                        COUNT(DISTINCT user_uuid) as unique_users,
                        COUNT(DISTINCT destination) as unique_destinations,
                        COUNT(DISTINCT node_uuid) as affected_nodes
                    FROM torrent_events
                    WHERE detected_at > NOW() - make_interval(days => $1)
                    """,
                    days,
                )
                top_users = await conn.fetch(
                    f"""
                    SELECT te.user_uuid::text, u.username, COUNT(*) as event_count
                    FROM torrent_events te
                    LEFT JOIN {USERS_TABLE} u ON u.uuid = te.user_uuid
                    WHERE te.detected_at > NOW() - make_interval(days => $1)
                    GROUP BY te.user_uuid, u.username
                    ORDER BY event_count DESC
                    LIMIT 10
                    """,
                    days,
                )
                return {
                    "total_events": row["total_events"] if row else 0,
                    "unique_users": row["unique_users"] if row else 0,
                    "unique_destinations": row["unique_destinations"] if row else 0,
                    "affected_nodes": row["affected_nodes"] if row else 0,
                    "top_users": [dict(r) for r in top_users],
                }
        except Exception as e:
            logger.error("get_torrent_stats failed: %s", e)
            return {}

    async def get_torrent_timeseries(self, days: int = 7) -> list:
        """Get torrent event counts grouped by day."""
        if not self.is_connected:
            return []
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT date_trunc('day', detected_at) AS day,
                           COUNT(*) AS event_count,
                           COUNT(DISTINCT user_uuid) AS unique_users
                    FROM torrent_events
                    WHERE detected_at > NOW() - make_interval(days => $1)
                    GROUP BY day
                    ORDER BY day
                    """,
                    days,
                )
                return [
                    {
                        "date": r["day"].isoformat() if r["day"] else None,
                        "events": r["event_count"],
                        "users": r["unique_users"],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("get_torrent_timeseries failed: %s", e)
            return []

    async def get_torrent_top_destinations(self, days: int = 7, limit: int = 15) -> list:
        """Get top torrent destinations by event count."""
        if not self.is_connected:
            return []
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT destination, COUNT(*) AS event_count,
                           COUNT(DISTINCT user_uuid) AS unique_users
                    FROM torrent_events
                    WHERE detected_at > NOW() - make_interval(days => $1)
                    GROUP BY destination
                    ORDER BY event_count DESC
                    LIMIT $2
                    """,
                    days, limit,
                )
                return [
                    {
                        "destination": r["destination"],
                        "events": r["event_count"],
                        "users": r["unique_users"],
                    }
                    for r in rows
                ]
        except Exception as e:
            logger.error("get_torrent_top_destinations failed: %s", e)
            return []

    async def cleanup_old_torrent_events(self, retention_days: int = 90, batch_size: int = 5000) -> int:
        """Delete torrent events older than retention_days in batches."""
        if not self.is_connected:
            return 0
        total = 0
        max_batches = 1000
        try:
            for _ in range(max_batches):
                async with self.acquire() as conn:
                    result = await conn.execute(
                        """
                        DELETE FROM torrent_events
                        WHERE id IN (
                            SELECT id FROM torrent_events
                            WHERE detected_at < NOW() - make_interval(days => $1)
                            ORDER BY detected_at
                            LIMIT $2
                        )
                        """,
                        retention_days, batch_size,
                    )
                    deleted = int(result.split()[-1]) if result and result.split() else 0
                    total += deleted
                    if deleted < batch_size:
                        break
                await asyncio.sleep(0.1)
            else:
                logger.warning("cleanup_old_torrent_events hit max_batches limit (%d batches, %d rows)", max_batches, total)
            return total
        except Exception as e:
            logger.error("cleanup_old_torrent_events failed: %s", e)
            return total

