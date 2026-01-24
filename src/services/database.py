"""
Database service for PostgreSQL integration.
Provides async database operations for caching API data locally.
"""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import asynccontextmanager

import asyncpg
from asyncpg import Pool, Connection

from src.config import get_settings
from src.utils.logger import logger


# SQL schema for creating tables
SCHEMA_SQL = """
-- Пользователи (основные данные для быстрого поиска)
CREATE TABLE IF NOT EXISTS users (
    uuid UUID PRIMARY KEY,
    short_uuid VARCHAR(16),
    username VARCHAR(255),
    subscription_uuid UUID,
    telegram_id BIGINT,
    email VARCHAR(255),
    status VARCHAR(50),
    expire_at TIMESTAMP WITH TIME ZONE,
    traffic_limit_bytes BIGINT,
    used_traffic_bytes BIGINT,
    hwid_device_limit INTEGER,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_short_uuid ON users(short_uuid);
CREATE INDEX IF NOT EXISTS idx_users_subscription_uuid ON users(subscription_uuid);

-- Ноды
CREATE TABLE IF NOT EXISTS nodes (
    uuid UUID PRIMARY KEY,
    name VARCHAR(255),
    address VARCHAR(255),
    port INTEGER,
    is_disabled BOOLEAN DEFAULT FALSE,
    is_connected BOOLEAN DEFAULT FALSE,
    traffic_limit_bytes BIGINT,
    traffic_used_bytes BIGINT,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_is_connected ON nodes(is_connected);

-- Хосты
CREATE TABLE IF NOT EXISTS hosts (
    uuid UUID PRIMARY KEY,
    remark VARCHAR(255),
    address VARCHAR(255),
    port INTEGER,
    is_disabled BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_hosts_remark ON hosts(remark);

-- Профили конфигурации (редко меняются)
CREATE TABLE IF NOT EXISTS config_profiles (
    uuid UUID PRIMARY KEY,
    name VARCHAR(255),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data JSONB
);

-- Метаданные синхронизации
CREATE TABLE IF NOT EXISTS sync_metadata (
    key VARCHAR(100) PRIMARY KEY,
    last_sync_at TIMESTAMP WITH TIME ZONE,
    sync_status VARCHAR(50),
    error_message TEXT,
    records_synced INTEGER DEFAULT 0
);

-- История IP-адресов пользователей (для будущего анализа устройств)
CREATE TABLE IF NOT EXISTS user_connections (
    id SERIAL PRIMARY KEY,
    user_uuid UUID REFERENCES users(uuid) ON DELETE CASCADE,
    ip_address INET,
    node_uuid UUID REFERENCES nodes(uuid) ON DELETE SET NULL,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    disconnected_at TIMESTAMP WITH TIME ZONE,
    device_info JSONB
);

CREATE INDEX IF NOT EXISTS idx_user_connections_user ON user_connections(user_uuid, connected_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_connections_ip ON user_connections(ip_address);
CREATE INDEX IF NOT EXISTS idx_user_connections_node ON user_connections(node_uuid);
"""


class DatabaseService:
    """
    Async database service for PostgreSQL operations.
    Provides CRUD operations for users, nodes, hosts, and config profiles.
    """
    
    def __init__(self):
        self._pool: Optional[Pool] = None
        self._initialized: bool = False
        self._lock = asyncio.Lock()
    
    @property
    def is_connected(self) -> bool:
        """Check if database connection is established."""
        return self._pool is not None and not self._pool._closed
    
    async def connect(self) -> bool:
        """
        Initialize database connection pool.
        Returns True if connection successful, False otherwise.
        """
        settings = get_settings()
        
        if not settings.database_url:
            logger.warning("DATABASE_URL not configured, database features disabled")
            return False
        
        async with self._lock:
            if self._pool is not None:
                return True
            
            try:
                logger.info("Connecting to PostgreSQL database...")
                self._pool = await asyncpg.create_pool(
                    dsn=settings.database_url,
                    min_size=settings.db_pool_min_size,
                    max_size=settings.db_pool_max_size,
                    command_timeout=30,
                )
                
                # Initialize schema
                await self._init_schema()
                self._initialized = True
                
                logger.info("✅ Database connection established successfully")
                return True
                
            except Exception as e:
                logger.error("❌ Failed to connect to database: %s", e)
                self._pool = None
                return False
    
    async def disconnect(self) -> None:
        """Close database connection pool."""
        async with self._lock:
            if self._pool is not None:
                logger.info("Closing database connection pool...")
                await self._pool.close()
                self._pool = None
                self._initialized = False
                logger.info("Database connection closed")
    
    async def _init_schema(self) -> None:
        """Initialize database schema (create tables if not exist)."""
        if self._pool is None:
            return
        
        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            logger.info("Database schema initialized")
    
    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        if self._pool is None:
            raise RuntimeError("Database not connected")
        
        async with self._pool.acquire() as conn:
            yield conn
    
    # ==================== Users ====================
    
    async def get_user_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by UUID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE uuid = $1",
                uuid
            )
            return dict(row) if row else None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username (case-insensitive)."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE LOWER(username) = LOWER($1)",
                username
            )
            return dict(row) if row else None
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user by Telegram ID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1",
                telegram_id
            )
            return dict(row) if row else None
    
    async def get_user_by_short_uuid(self, short_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by short UUID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE short_uuid = $1",
                short_uuid
            )
            return dict(row) if row else None
    
    async def get_user_by_subscription_uuid(self, subscription_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by subscription UUID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE subscription_uuid = $1",
                subscription_uuid
            )
            return dict(row) if row else None
    
    async def search_users(
        self,
        query: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Search users by username, email, short_uuid, or UUID.
        Returns list of matching users.
        """
        if not self.is_connected:
            return []
        
        search_pattern = f"%{query}%"
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM users 
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
            return [dict(row) for row in rows]
    
    async def get_users_count(self) -> int:
        """Get total number of users in database."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.fetchval("SELECT COUNT(*) FROM users")
            return result or 0
    
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
        
        async with self.acquire() as conn:
            if status:
                rows = await conn.fetch(
                    f"SELECT * FROM users WHERE status = $1 ORDER BY {order_by} LIMIT $2 OFFSET $3",
                    status, limit, offset
                )
            else:
                rows = await conn.fetch(
                    f"SELECT * FROM users ORDER BY {order_by} LIMIT $1 OFFSET $2",
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
                """
                SELECT status, COUNT(*) as count FROM users 
                GROUP BY status
                """
            )
            
            stats = {"total": 0, "active": 0, "expired": 0, "disabled": 0, "limited": 0}
            for row in rows:
                status = row["status"]
                count = row["count"]
                stats["total"] += count
                if status:
                    stats[status.lower()] = count
            
            return stats
    
    async def get_users_by_status(self, status: str, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """Get users by status."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM users WHERE status = $1 ORDER BY username LIMIT $2 OFFSET $3",
                status, limit, offset
            )
            return [dict(row) for row in rows]
    
    async def upsert_user(self, user_data: Dict[str, Any]) -> None:
        """Insert or update a user."""
        if not self.is_connected:
            return
        
        # Extract data from API response
        response = user_data.get("response", user_data)
        
        uuid = response.get("uuid")
        if not uuid:
            logger.warning("Cannot upsert user without UUID")
            return
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO users (
                    uuid, short_uuid, username, subscription_uuid, telegram_id,
                    email, status, expire_at, traffic_limit_bytes, used_traffic_bytes,
                    hwid_device_limit, created_at, updated_at, raw_data
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW(), $13)
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
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                response.get("shortUuid"),
                response.get("username"),
                response.get("subscriptionUuid"),
                response.get("telegramId"),
                response.get("email"),
                response.get("status"),
                _parse_timestamp(response.get("expireAt")),
                response.get("trafficLimitBytes"),
                response.get("usedTrafficBytes"),
                response.get("hwidDeviceLimit"),
                _parse_timestamp(response.get("createdAt")),
                json.dumps(response),
            )
    
    async def bulk_upsert_users(self, users: List[Dict[str, Any]]) -> int:
        """Bulk insert or update users. Returns number of records processed."""
        if not self.is_connected or not users:
            return 0
        
        count = 0
        async with self.acquire() as conn:
            async with conn.transaction():
                for user_data in users:
                    try:
                        await self.upsert_user(user_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert user: %s", e)
        
        return count
    
    async def delete_user(self, uuid: str) -> bool:
        """Delete user by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM users WHERE uuid = $1",
                uuid
            )
            return result == "DELETE 1"
    
    # ==================== Nodes ====================
    
    async def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes with raw_data in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM nodes ORDER BY name")
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_node_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get node by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM nodes WHERE uuid = $1",
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_nodes_stats(self) -> Dict[str, int]:
        """
        Get nodes statistics.
        Returns dict: {total, enabled, disabled, connected}
        """
        if not self.is_connected:
            return {"total": 0, "enabled": 0, "disabled": 0, "connected": 0}
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE NOT is_disabled) as enabled,
                    COUNT(*) FILTER (WHERE is_disabled) as disabled,
                    COUNT(*) FILTER (WHERE is_connected AND NOT is_disabled) as connected
                FROM nodes
                """
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
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO nodes (
                    uuid, name, address, port, is_disabled, is_connected,
                    traffic_limit_bytes, traffic_used_bytes, updated_at, raw_data
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW(), $9)
                ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    address = EXCLUDED.address,
                    port = EXCLUDED.port,
                    is_disabled = EXCLUDED.is_disabled,
                    is_connected = EXCLUDED.is_connected,
                    traffic_limit_bytes = EXCLUDED.traffic_limit_bytes,
                    traffic_used_bytes = EXCLUDED.traffic_used_bytes,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                response.get("name"),
                response.get("address"),
                response.get("port"),
                response.get("isDisabled", False),
                response.get("isConnected", False),
                response.get("trafficLimitBytes"),
                response.get("trafficUsedBytes"),
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
                "DELETE FROM nodes WHERE uuid = $1",
                uuid
            )
            return result == "DELETE 1"
    
    # ==================== Hosts ====================
    
    async def get_all_hosts(self) -> List[Dict[str, Any]]:
        """Get all hosts with raw_data in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM hosts ORDER BY remark")
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_host_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get host by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM hosts WHERE uuid = $1",
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_hosts_stats(self) -> Dict[str, int]:
        """
        Get hosts statistics.
        Returns dict: {total, enabled, disabled}
        """
        if not self.is_connected:
            return {"total": 0, "enabled": 0, "disabled": 0}
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(*) FILTER (WHERE NOT is_disabled) as enabled,
                    COUNT(*) FILTER (WHERE is_disabled) as disabled
                FROM hosts
                """
            )
            return dict(row) if row else {"total": 0, "enabled": 0, "disabled": 0}
    
    async def upsert_host(self, host_data: Dict[str, Any]) -> None:
        """Insert or update a host."""
        if not self.is_connected:
            return
        
        response = host_data.get("response", host_data)
        
        uuid = response.get("uuid")
        if not uuid:
            logger.warning("Cannot upsert host without UUID")
            return
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO hosts (
                    uuid, remark, address, port, is_disabled, updated_at, raw_data
                ) VALUES ($1, $2, $3, $4, $5, NOW(), $6)
                ON CONFLICT (uuid) DO UPDATE SET
                    remark = EXCLUDED.remark,
                    address = EXCLUDED.address,
                    port = EXCLUDED.port,
                    is_disabled = EXCLUDED.is_disabled,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                response.get("remark"),
                response.get("address"),
                response.get("port"),
                response.get("isDisabled", False),
                json.dumps(response),
            )
    
    async def bulk_upsert_hosts(self, hosts: List[Dict[str, Any]]) -> int:
        """Bulk insert or update hosts. Returns number of records processed."""
        if not self.is_connected or not hosts:
            return 0
        
        count = 0
        async with self.acquire() as conn:
            async with conn.transaction():
                for host_data in hosts:
                    try:
                        await self.upsert_host(host_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert host: %s", e)
        
        return count
    
    async def delete_host(self, uuid: str) -> bool:
        """Delete host by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM hosts WHERE uuid = $1",
                uuid
            )
            return result == "DELETE 1"
    
    # ==================== Config Profiles ====================
    
    async def get_all_config_profiles(self) -> List[Dict[str, Any]]:
        """Get all config profiles with raw_data in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM config_profiles ORDER BY name")
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_config_profile_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get config profile by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM config_profiles WHERE uuid = $1",
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def upsert_config_profile(self, profile_data: Dict[str, Any]) -> None:
        """Insert or update a config profile."""
        if not self.is_connected:
            return
        
        response = profile_data.get("response", profile_data)
        
        uuid = response.get("uuid")
        if not uuid:
            logger.warning("Cannot upsert config profile without UUID")
            return
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO config_profiles (uuid, name, updated_at, raw_data)
                VALUES ($1, $2, NOW(), $3)
                ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                response.get("name"),
                json.dumps(response),
            )
    
    async def bulk_upsert_config_profiles(self, profiles: List[Dict[str, Any]]) -> int:
        """Bulk insert or update config profiles. Returns number of records processed."""
        if not self.is_connected or not profiles:
            return 0
        
        count = 0
        async with self.acquire() as conn:
            async with conn.transaction():
                for profile_data in profiles:
                    try:
                        await self.upsert_config_profile(profile_data)
                        count += 1
                    except Exception as e:
                        logger.warning("Failed to upsert config profile: %s", e)
        
        return count
    
    # ==================== Sync Metadata ====================
    
    async def get_sync_metadata(self, key: str) -> Optional[Dict[str, Any]]:
        """Get sync metadata by key."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM sync_metadata WHERE key = $1",
                key
            )
            return dict(row) if row else None
    
    async def update_sync_metadata(
        self,
        key: str,
        status: str,
        records_synced: int = 0,
        error_message: Optional[str] = None
    ) -> None:
        """Update sync metadata."""
        if not self.is_connected:
            return
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO sync_metadata (key, last_sync_at, sync_status, records_synced, error_message)
                VALUES ($1, NOW(), $2, $3, $4)
                ON CONFLICT (key) DO UPDATE SET
                    last_sync_at = NOW(),
                    sync_status = EXCLUDED.sync_status,
                    records_synced = EXCLUDED.records_synced,
                    error_message = EXCLUDED.error_message
                """,
                key, status, records_synced, error_message
            )
    
    # ==================== User Connections (for future device tracking) ====================
    
    async def add_user_connection(
        self,
        user_uuid: str,
        ip_address: str,
        node_uuid: Optional[str] = None,
        device_info: Optional[Dict[str, Any]] = None
    ) -> Optional[int]:
        """Add a user connection record. Returns connection ID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            result = await conn.fetchval(
                """
                INSERT INTO user_connections (user_uuid, ip_address, node_uuid, device_info)
                VALUES ($1, $2::inet, $3, $4)
                RETURNING id
                """,
                user_uuid, ip_address, node_uuid,
                json.dumps(device_info) if device_info else None
            )
            return result
    
    async def get_user_active_connections(
        self,
        user_uuid: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get active (not disconnected) connections for a user."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT * FROM user_connections 
                WHERE user_uuid = $1 AND disconnected_at IS NULL
                ORDER BY connected_at DESC
                LIMIT $2
                """,
                user_uuid, limit
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
                """
                SELECT COUNT(DISTINCT ip_address) FROM user_connections
                WHERE user_uuid = $1 
                AND connected_at > NOW() - INTERVAL '%s hours'
                """.replace('%s', str(since_hours)),
                user_uuid
            )
            return result or 0
    
    async def close_user_connection(self, connection_id: int) -> bool:
        """Mark a connection as disconnected."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                """
                UPDATE user_connections SET disconnected_at = NOW()
                WHERE id = $1 AND disconnected_at IS NULL
                """,
                connection_id
            )
            return result == "UPDATE 1"


def _db_row_to_api_format(row) -> Dict[str, Any]:
    """
    Convert database row to API format.
    If raw_data exists, use it; otherwise build from row fields.
    """
    if row is None:
        return {}
    
    row_dict = dict(row)
    raw_data = row_dict.get("raw_data")
    
    if raw_data:
        # Use raw_data if available (contains full API response)
        if isinstance(raw_data, str):
            try:
                return json.loads(raw_data)
            except json.JSONDecodeError:
                pass
        elif isinstance(raw_data, dict):
            return raw_data
    
    # Fallback: build from row fields (convert snake_case to camelCase)
    result = {}
    field_mapping = {
        "uuid": "uuid",
        "short_uuid": "shortUuid",
        "username": "username",
        "subscription_uuid": "subscriptionUuid",
        "telegram_id": "telegramId",
        "email": "email",
        "status": "status",
        "expire_at": "expireAt",
        "traffic_limit_bytes": "trafficLimitBytes",
        "used_traffic_bytes": "usedTrafficBytes",
        "hwid_device_limit": "hwidDeviceLimit",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
        "name": "name",
        "address": "address",
        "port": "port",
        "is_disabled": "isDisabled",
        "is_connected": "isConnected",
        "remark": "remark",
    }
    
    for db_field, api_field in field_mapping.items():
        if db_field in row_dict and row_dict[db_field] is not None:
            value = row_dict[db_field]
            # Convert datetime to ISO string
            if isinstance(value, datetime):
                value = value.isoformat()
            # Convert UUID to string
            elif hasattr(value, 'hex'):
                value = str(value)
            result[api_field] = value
    
    return result


def _parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse timestamp from various formats."""
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value
    
    if isinstance(value, str):
        try:
            # Try ISO format
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except ValueError:
            pass
        
        try:
            # Try common format
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    
    return None


# Global database service instance
db_service = DatabaseService()
