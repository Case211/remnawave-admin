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
    agent_token VARCHAR(255),  -- Токен для аутентификации Node Agent
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_is_connected ON nodes(is_connected);
CREATE INDEX IF NOT EXISTS idx_nodes_agent_token ON nodes(agent_token) WHERE agent_token IS NOT NULL;

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

-- HWID устройства пользователей
CREATE TABLE IF NOT EXISTS user_hwid_devices (
    id SERIAL PRIMARY KEY,
    user_uuid UUID NOT NULL,
    hwid VARCHAR(255) NOT NULL,
    platform VARCHAR(50),
    os_version VARCHAR(100),
    app_version VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_hwid_devices_user_hwid ON user_hwid_devices(user_uuid, hwid);
CREATE INDEX IF NOT EXISTS idx_hwid_devices_user_uuid ON user_hwid_devices(user_uuid);
CREATE INDEX IF NOT EXISTS idx_hwid_devices_platform ON user_hwid_devices(platform);
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
        import os
        settings = get_settings()
        database_url = getattr(settings, 'database_url', None) or os.environ.get('DATABASE_URL')
        if not database_url:
            logger.warning("DATABASE_URL not configured, database features disabled")
            return False
        
        async with self._lock:
            if self._pool is not None:
                return True
            
            try:
                logger.info("Connecting to PostgreSQL database...")
                self._pool = await asyncpg.create_pool(
                    dsn=database_url,
                    min_size=getattr(settings, 'db_pool_min_size', 2),
                    max_size=getattr(settings, 'db_pool_max_size', 10),
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
        """Get user by UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE uuid = $1",
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_uuid_by_email(self, email: str) -> Optional[str]:
        """Находит user_uuid по email. Возвращает UUID или None."""
        if not self.is_connected or not email:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT uuid FROM users WHERE email = $1 LIMIT 1",
                email
            )
            return str(row["uuid"]) if row else None
    
    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """Get user by username (case-insensitive) with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE LOWER(username) = LOWER($1)",
                username
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_by_telegram_id(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """Get user by Telegram ID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE telegram_id = $1",
                telegram_id
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_by_short_uuid(self, short_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by short UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE short_uuid = $1",
                short_uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_by_subscription_uuid(self, subscription_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user by subscription UUID with raw_data in API format."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM users WHERE subscription_uuid = $1",
                subscription_uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def get_user_uuid_by_id_from_raw_data(self, user_id: str) -> Optional[str]:
        """Находит user_uuid по ID из raw_data (для Xray логов)."""
        if not self.is_connected or not user_id:
            return None
        
        async with self.acquire() as conn:
            # Ищем по разным возможным полям в raw_data
            row = await conn.fetchrow(
                """
                SELECT uuid FROM users 
                WHERE raw_data->>'id' = $1 
                   OR raw_data->>'userId' = $1
                   OR raw_data->>'user_id' = $1
                LIMIT 1
                """,
                user_id
            )
            return str(row["uuid"]) if row else None
    
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
            return [_db_row_to_api_format(row) for row in rows]
    
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
        """Get users by status in API format."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM users WHERE status = $1 ORDER BY username LIMIT $2 OFFSET $3",
                status, limit, offset
            )
            return [_db_row_to_api_format(row) for row in rows]
    
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
    
    async def get_node_agent_token(self, uuid: str) -> Optional[str]:
        """Получить токен агента для ноды (если установлен)."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT agent_token FROM nodes WHERE uuid = $1",
                uuid
            )
            return row["agent_token"] if row and row["agent_token"] else None
    
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
                    -- agent_token НЕ обновляем при синхронизации из API (сохраняем локальные настройки)
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
            # Проверяем, есть ли уже активное подключение с этим IP для этого пользователя
            existing = await conn.fetchrow(
                """
                SELECT id FROM user_connections
                WHERE user_uuid = $1 
                AND ip_address = $2
                AND disconnected_at IS NULL
                ORDER BY connected_at DESC
                LIMIT 1
                """,
                user_uuid, ip_address
            )
            
            if existing:
                # Обновляем время подключения существующей записи
                # Используем самое позднее время (из нового подключения или существующего)
                conn_id = existing['id']
                # Получаем текущее время подключения из БД
                existing_row = await conn.fetchrow(
                    "SELECT connected_at FROM user_connections WHERE id = $1",
                    conn_id
                )
                existing_time = existing_row['connected_at'] if existing_row else None
                
                # Используем самое позднее время
                if connected_at and existing_time:
                    # Преобразуем existing_time в datetime если нужно
                    if isinstance(existing_time, str):
                        try:
                            existing_time = datetime.fromisoformat(existing_time.replace('Z', '+00:00'))
                        except ValueError:
                            existing_time = None
                    if isinstance(existing_time, datetime) and isinstance(connected_at, datetime):
                        # Убираем timezone для сравнения
                        if existing_time.tzinfo:
                            existing_time = existing_time.replace(tzinfo=None)
                        if connected_at.tzinfo:
                            connected_at_naive = connected_at.replace(tzinfo=None)
                        else:
                            connected_at_naive = connected_at
                        update_time = max(existing_time, connected_at_naive)
                    else:
                        update_time = connected_at if connected_at else datetime.utcnow()
                elif connected_at:
                    update_time = connected_at
                elif existing_time:
                    update_time = existing_time
                else:
                    update_time = datetime.utcnow()
                
                await conn.execute(
                    """
                    UPDATE user_connections
                    SET connected_at = $1, node_uuid = COALESCE($2, node_uuid)
                    WHERE id = $3
                    """,
                    update_time, node_uuid, conn_id
                )
                
                # Если пользователь подключается с новым IP, закрываем старые подключения с другими IP
                # Это учитывает роутинг в приложении - пользователь может переключаться между серверами
                await conn.execute(
                    """
                    UPDATE user_connections
                    SET disconnected_at = NOW()
                    WHERE user_uuid = $1
                    AND ip_address != $2
                    AND disconnected_at IS NULL
                    AND connected_at < NOW() - INTERVAL '2 minutes'
                    """,
                    user_uuid, ip_address
                )

                return conn_id
            else:
                # Создаём новую запись
                # Используем переданное время или текущее время
                insert_time = connected_at if connected_at else datetime.utcnow()
                result = await conn.fetchval(
                    """
                    INSERT INTO user_connections (user_uuid, ip_address, node_uuid, device_info, connected_at)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id
                    """,
                    user_uuid, ip_address, node_uuid,
                    json.dumps(device_info) if device_info else None,
                    insert_time
                )
                
                # Если пользователь подключается с новым IP, закрываем старые подключения с другими IP
                # Это учитывает роутинг в приложении - пользователь может переключаться между серверами
                await conn.execute(
                    """
                    UPDATE user_connections
                    SET disconnected_at = NOW()
                    WHERE user_uuid = $1
                    AND ip_address != $2
                    AND disconnected_at IS NULL
                    AND connected_at < NOW() - INTERVAL '2 minutes'
                    """,
                    user_uuid, ip_address
                )

                return result
    
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
                """
                SELECT * FROM user_connections 
                WHERE user_uuid = $1 
                AND disconnected_at IS NULL
                AND connected_at > NOW() - INTERVAL '%s minutes'
                ORDER BY connected_at DESC
                LIMIT $2
                """.replace('%s', str(max_age_minutes)),
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
                """
                SELECT COUNT(DISTINCT ip_address) FROM user_connections
                WHERE user_uuid = $1 
                AND connected_at > NOW() - INTERVAL '%s minutes'
                """.replace('%s', str(window_minutes)),
                user_uuid
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
                """
                SELECT COUNT(*) FROM user_connections
                WHERE user_uuid = $1 
                AND disconnected_at IS NULL
                """,
                user_uuid
            )
            return result or 0
    
    async def get_connection_history(
        self,
        user_uuid: str,
        days: int = 7,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Get connection history for a user.
        
        Args:
            user_uuid: UUID пользователя
            days: Количество дней истории (по умолчанию 7)
            limit: Максимальное количество записей (по умолчанию 1000)
        
        Returns:
            Список подключений с информацией об IP, ноде, времени подключения/отключения
        """
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT 
                    id,
                    user_uuid,
                    ip_address,
                    node_uuid,
                    connected_at,
                    disconnected_at,
                    device_info
                FROM user_connections
                WHERE user_uuid = $1 
                AND connected_at > NOW() - INTERVAL '%s days'
                ORDER BY connected_at DESC
                LIMIT $2
                """.replace('%s', str(days)),
                user_uuid,
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
                """
                UPDATE user_connections SET disconnected_at = NOW()
                WHERE id = $1 AND disconnected_at IS NULL
                """,
                connection_id
            )
            return result == "UPDATE 1"

    # ==================== API Tokens Methods ====================
    
    async def upsert_token(self, data: Dict[str, Any]) -> bool:
        """Upsert an API token."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        if isinstance(response, list):
            for token in response:
                await self._upsert_single_token(token)
            return True
        
        return await self._upsert_single_token(response)
    
    async def _upsert_single_token(self, token: Dict[str, Any]) -> bool:
        """Upsert a single token."""
        uuid = token.get("uuid")
        if not uuid:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO api_tokens (uuid, name, token_hash, created_at, updated_at, raw_data)
                VALUES ($1, $2, $3, $4, NOW(), $5)
                ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    token_hash = EXCLUDED.token_hash,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                token.get("name") or token.get("tokenName"),
                token.get("token") or token.get("tokenHash"),
                _parse_timestamp(token.get("createdAt")),
                json.dumps(token)
            )
        return True
    
    async def get_all_tokens(self) -> List[Dict[str, Any]]:
        """Get all API tokens."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM api_tokens ORDER BY name"
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_token_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get token by UUID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM api_tokens WHERE uuid = $1",
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def delete_token_from_db(self, uuid: str) -> bool:
        """Delete token from DB by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM api_tokens WHERE uuid = $1",
                uuid
            )
            return result == "DELETE 1"
    
    async def delete_all_tokens(self) -> int:
        """Delete all tokens. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute("DELETE FROM api_tokens")
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0

    # ==================== Templates Methods ====================
    
    async def upsert_template(self, data: Dict[str, Any]) -> bool:
        """Upsert a subscription template."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        if isinstance(response, list):
            for tpl in response:
                await self._upsert_single_template(tpl)
            return True
        
        return await self._upsert_single_template(response)
    
    async def _upsert_single_template(self, tpl: Dict[str, Any]) -> bool:
        """Upsert a single template."""
        uuid = tpl.get("uuid")
        if not uuid:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO templates (uuid, name, template_type, sort_order, created_at, updated_at, raw_data)
                VALUES ($1, $2, $3, $4, $5, NOW(), $6)
                ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    template_type = EXCLUDED.template_type,
                    sort_order = EXCLUDED.sort_order,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                tpl.get("name"),
                tpl.get("type") or tpl.get("templateType"),
                tpl.get("sortOrder") or tpl.get("sort_order"),
                _parse_timestamp(tpl.get("createdAt")),
                json.dumps(tpl)
            )
        return True
    
    async def get_all_templates(self) -> List[Dict[str, Any]]:
        """Get all subscription templates."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM templates ORDER BY sort_order, name"
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_template_by_uuid(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get template by UUID."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM templates WHERE uuid = $1",
                uuid
            )
            return _db_row_to_api_format(row) if row else None
    
    async def delete_template_from_db(self, uuid: str) -> bool:
        """Delete template from DB by UUID."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM templates WHERE uuid = $1",
                uuid
            )
            return result == "DELETE 1"
    
    async def delete_all_templates(self) -> int:
        """Delete all templates. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute("DELETE FROM templates")
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0

    # ==================== Snippets Methods ====================
    
    async def upsert_snippet(self, data: Dict[str, Any]) -> bool:
        """Upsert a snippet."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        snippets = response.get("snippets", []) if isinstance(response, dict) else response
        
        if isinstance(snippets, list):
            for snippet in snippets:
                await self._upsert_single_snippet(snippet)
            return True
        
        return await self._upsert_single_snippet(response)
    
    async def _upsert_single_snippet(self, snippet: Dict[str, Any]) -> bool:
        """Upsert a single snippet."""
        name = snippet.get("name")
        if not name:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO snippets (name, snippet_data, created_at, updated_at, raw_data)
                VALUES ($1, $2, $3, NOW(), $4)
                ON CONFLICT (name) DO UPDATE SET
                    snippet_data = EXCLUDED.snippet_data,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                name,
                json.dumps(snippet.get("snippet", [])),
                _parse_timestamp(snippet.get("createdAt")),
                json.dumps(snippet)
            )
        return True
    
    async def get_all_snippets(self) -> List[Dict[str, Any]]:
        """Get all snippets."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM snippets ORDER BY name"
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_snippet_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get snippet by name."""
        if not self.is_connected:
            return None
        
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM snippets WHERE name = $1",
                name
            )
            return _db_row_to_api_format(row) if row else None
    
    async def delete_snippet_from_db(self, name: str) -> bool:
        """Delete snippet from DB by name."""
        if not self.is_connected:
            return False
        
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM snippets WHERE name = $1",
                name
            )
            return result == "DELETE 1"
    
    async def delete_all_snippets(self) -> int:
        """Delete all snippets. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute("DELETE FROM snippets")
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0

    # ==================== Squads Methods ====================
    
    async def upsert_internal_squads(self, data: Dict[str, Any]) -> bool:
        """Upsert internal squads."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        squads = response.get("internalSquads", []) if isinstance(response, dict) else response
        
        if isinstance(squads, list):
            for squad in squads:
                await self._upsert_single_internal_squad(squad)
            return True
        
        return await self._upsert_single_internal_squad(response)
    
    async def _upsert_single_internal_squad(self, squad: Dict[str, Any]) -> bool:
        """Upsert a single internal squad."""
        uuid = squad.get("uuid")
        if not uuid:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO internal_squads (uuid, name, description, updated_at, raw_data)
                VALUES ($1, $2, $3, NOW(), $4)
                ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                squad.get("name"),
                squad.get("description"),
                json.dumps(squad)
            )
        return True
    
    async def upsert_external_squads(self, data: Dict[str, Any]) -> bool:
        """Upsert external squads."""
        if not self.is_connected:
            return False
        
        response = data.get("response", data)
        squads = response.get("externalSquads", []) if isinstance(response, dict) else response
        
        if isinstance(squads, list):
            for squad in squads:
                await self._upsert_single_external_squad(squad)
            return True
        
        return await self._upsert_single_external_squad(response)
    
    async def _upsert_single_external_squad(self, squad: Dict[str, Any]) -> bool:
        """Upsert a single external squad."""
        uuid = squad.get("uuid")
        if not uuid:
            return False
        
        async with self.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO external_squads (uuid, name, description, updated_at, raw_data)
                VALUES ($1, $2, $3, NOW(), $4)
                ON CONFLICT (uuid) DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    updated_at = NOW(),
                    raw_data = EXCLUDED.raw_data
                """,
                uuid,
                squad.get("name"),
                squad.get("description"),
                json.dumps(squad)
            )
        return True
    
    async def get_all_internal_squads(self) -> List[Dict[str, Any]]:
        """Get all internal squads."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM internal_squads ORDER BY name"
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def get_all_external_squads(self) -> List[Dict[str, Any]]:
        """Get all external squads."""
        if not self.is_connected:
            return []
        
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM external_squads ORDER BY name"
            )
            return [_db_row_to_api_format(row) for row in rows]
    
    async def delete_all_internal_squads(self) -> int:
        """Delete all internal squads. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute("DELETE FROM internal_squads")
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0
    
    async def delete_all_external_squads(self) -> int:
        """Delete all external squads. Returns count of deleted records."""
        if not self.is_connected:
            return 0
        
        async with self.acquire() as conn:
            result = await conn.execute("DELETE FROM external_squads")
            try:
                return int(result.split()[-1])
            except (IndexError, ValueError):
                return 0
    
    # ==================== User Devices (HWID) ====================
    # Используем данные из users.raw_data вместо отдельной таблицы
    
    async def get_user_devices_count(self, user_uuid: str) -> int:
        """
        Получить количество устройств пользователя из локальной БД.
        Использует данные из users.raw_data (синхронизированные из API).
        
        Args:
            user_uuid: UUID пользователя
        
        Returns:
            Количество устройств пользователя
        """
        if not self.is_connected:
            return 1  # По умолчанию 1 устройство
        
        try:
            async with self.acquire() as conn:
                # Получаем raw_data пользователя, где могут быть данные об устройствах
                row = await conn.fetchrow(
                    "SELECT raw_data FROM users WHERE uuid = $1",
                    user_uuid
                )
                
                if row and row.get("raw_data"):
                    raw_data = row["raw_data"]
                    if isinstance(raw_data, str):
                        try:
                            raw_data = json.loads(raw_data)
                        except json.JSONDecodeError:
                            pass

                    if isinstance(raw_data, dict):
                        # Проверяем различные возможные поля с данными об устройствах
                        response = raw_data.get("response", raw_data)

                        # Основное поле - hwidDeviceLimit (лимит HWID устройств)
                        hwid_device_limit = response.get("hwidDeviceLimit")
                        if hwid_device_limit is not None:
                            # 0 означает безлимит, но для расчёта используем 1
                            limit = int(hwid_device_limit)
                            if limit == 0:
                                return 1  # Безлимит - используем 1 как базу
                            return max(1, limit)

                        # Fallback: devicesCount (старый формат)
                        devices_count = response.get("devicesCount")
                        if devices_count is not None:
                            return max(1, int(devices_count))

                        # Fallback: массив devices
                        devices = response.get("devices", [])
                        if isinstance(devices, list) and len(devices) > 0:
                            return len(devices)

                # Если данных нет, возвращаем 1 по умолчанию
                logger.debug("No device limit data found for user %s, using default 1", user_uuid)
                return 1
        except Exception as e:
            logger.error("Error getting user devices count for %s: %s", user_uuid, e, exc_info=True)
            return 1  # По умолчанию 1 устройство

    # ==================== IP Metadata ====================
    
    async def get_ip_metadata(self, ip_address: str) -> Optional[Dict[str, Any]]:
        """
        Получить метаданные IP адреса из БД.
        
        Args:
            ip_address: IP адрес
        
        Returns:
            Словарь с метаданными или None
        """
        if not self.is_connected:
            return None
        
        try:
            async with self.acquire() as conn:
                query = """
                    SELECT ip_address, country_code, country_name, region, city,
                           latitude, longitude, timezone, asn, asn_org,
                           connection_type, is_proxy, is_vpn, is_tor, is_hosting, is_mobile,
                           created_at, updated_at, last_checked_at
                    FROM ip_metadata
                    WHERE ip_address = $1
                """
                row = await conn.fetchrow(query, ip_address)
                
                if row:
                    return dict(row)
                return None
            
        except Exception as e:
            logger.error("Error getting IP metadata for %s: %s", ip_address, e, exc_info=True)
            return None
    
    async def get_ip_metadata_batch(self, ip_addresses: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Получить метаданные для нескольких IP адресов из БД.
        
        Args:
            ip_addresses: Список IP адресов
        
        Returns:
            Словарь {ip: metadata}
        """
        if not self.is_connected or not ip_addresses:
            return {}
        
        try:
            async with self.acquire() as conn:
                query = """
                    SELECT ip_address, country_code, country_name, region, city,
                           latitude, longitude, timezone, asn, asn_org,
                           connection_type, is_proxy, is_vpn, is_tor, is_hosting, is_mobile,
                           created_at, updated_at, last_checked_at
                    FROM ip_metadata
                    WHERE ip_address = ANY($1::text[])
                """
                rows = await conn.fetch(query, ip_addresses)
                
                result = {}
                for row in rows:
                    result[row['ip_address']] = dict(row)
                
                return result
            
        except Exception as e:
            logger.error("Error getting IP metadata batch: %s", e, exc_info=True)
            return {}
    
    async def save_ip_metadata(
        self,
        ip_address: str,
        country_code: Optional[str] = None,
        country_name: Optional[str] = None,
        region: Optional[str] = None,
        city: Optional[str] = None,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        timezone: Optional[str] = None,
        asn: Optional[int] = None,
        asn_org: Optional[str] = None,
        connection_type: Optional[str] = None,
        is_proxy: bool = False,
        is_vpn: bool = False,
        is_tor: bool = False,
        is_hosting: bool = False,
        is_mobile: bool = False
    ) -> bool:
        """
        Сохранить или обновить метаданные IP адреса в БД.
        
        Args:
            ip_address: IP адрес
            ... остальные параметры метаданных
        
        Returns:
            True если успешно, False при ошибке
        """
        if not self.is_connected:
            return False
        
        try:
            async with self.acquire() as conn:
                query = """
                    INSERT INTO ip_metadata (
                        ip_address, country_code, country_name, region, city,
                        latitude, longitude, timezone, asn, asn_org,
                        connection_type, is_proxy, is_vpn, is_tor, is_hosting, is_mobile,
                        last_checked_at, updated_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, NOW(), NOW()
                    )
                    ON CONFLICT (ip_address) DO UPDATE SET
                        country_code = EXCLUDED.country_code,
                        country_name = EXCLUDED.country_name,
                        region = EXCLUDED.region,
                        city = EXCLUDED.city,
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        timezone = EXCLUDED.timezone,
                        asn = EXCLUDED.asn,
                        asn_org = EXCLUDED.asn_org,
                        connection_type = EXCLUDED.connection_type,
                        is_proxy = EXCLUDED.is_proxy,
                        is_vpn = EXCLUDED.is_vpn,
                        is_tor = EXCLUDED.is_tor,
                        is_hosting = EXCLUDED.is_hosting,
                        is_mobile = EXCLUDED.is_mobile,
                        last_checked_at = NOW(),
                        updated_at = NOW()
                """
                
                await conn.execute(
                    query,
                    ip_address, country_code, country_name, region, city,
                    latitude, longitude, timezone, asn, asn_org,
                    connection_type, is_proxy, is_vpn, is_tor, is_hosting, is_mobile
                )
                
                return True
            
        except Exception as e:
            logger.error("Error saving IP metadata for %s: %s", ip_address, e, exc_info=True)
            return False
    
    async def should_refresh_ip_metadata(self, ip_address: str, max_age_days: int = 30) -> bool:
        """
        Проверить, нужно ли обновить метаданные IP (если они старые или отсутствуют).
        
        Args:
            ip_address: IP адрес
            max_age_days: Максимальный возраст данных в днях (по умолчанию 30)
        
        Returns:
            True если нужно обновить, False если данные актуальны
        """
        if not self.is_connected:
            return True
        
        try:
            async with self.acquire() as conn:
                query = """
                    SELECT last_checked_at
                    FROM ip_metadata
                    WHERE ip_address = $1
                """
                row = await conn.fetchrow(query, ip_address)
                
                if not row or not row['last_checked_at']:
                    return True  # Нет данных - нужно получить
                
                from datetime import timedelta
                age = datetime.now(timezone.utc) - row['last_checked_at']
                return age > timedelta(days=max_age_days)
            
        except Exception as e:
            logger.error("Error checking IP metadata age for %s: %s", ip_address, e, exc_info=True)
            return True  # При ошибке лучше обновить
    
    # ========== Методы для работы с ASN базой по РФ ==========
    
    async def get_asn_record(self, asn: int) -> Optional[Dict[str, Any]]:
        """
        Получить запись ASN из базы по РФ.
        
        Args:
            asn: Номер ASN
        
        Returns:
            Словарь с данными ASN или None
        """
        if not self.is_connected:
            return None
        
        try:
            async with self.acquire() as conn:
                query = """
                    SELECT asn, org_name, org_name_en, provider_type, region, city,
                           country_code, description, ip_ranges, is_active,
                           created_at, updated_at, last_synced_at
                    FROM asn_russia
                    WHERE asn = $1 AND is_active = true
                """
                row = await conn.fetchrow(query, asn)
                
                if row:
                    return dict(row)
                return None
            
        except Exception as e:
            logger.error("Error getting ASN record %d: %s", asn, e, exc_info=True)
            return None
    
    async def get_asn_by_org_name(self, org_name: str) -> List[Dict[str, Any]]:
        """
        Найти ASN по названию организации (поиск по подстроке).
        
        Args:
            org_name: Название организации (или часть)
        
        Returns:
            Список записей ASN
        """
        if not self.is_connected:
            return []
        
        try:
            async with self.acquire() as conn:
                query = """
                    SELECT asn, org_name, org_name_en, provider_type, region, city,
                           country_code, description, is_active
                    FROM asn_russia
                    WHERE (LOWER(org_name) LIKE LOWER($1) OR LOWER(org_name_en) LIKE LOWER($1))
                      AND is_active = true
                    ORDER BY org_name
                    LIMIT 100
                """
                rows = await conn.fetch(query, f"%{org_name}%")
                return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error("Error searching ASN by org name '%s': %s", org_name, e, exc_info=True)
            return []
    
    async def save_asn_record(self, asn_record) -> bool:
        """
        Сохранить или обновить запись ASN в базе по РФ.
        
        Args:
            asn_record: Объект ASNRecord из asn_parser (или dict с полями)
        
        Returns:
            True если успешно, False при ошибке
        """
        if not self.is_connected:
            return False
        
        try:
            async with self.acquire() as conn:
                query = """
                    INSERT INTO asn_russia (
                        asn, org_name, org_name_en, provider_type, region, city,
                        country_code, description, ip_ranges, is_active, updated_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, NOW()
                    )
                    ON CONFLICT (asn) DO UPDATE SET
                        org_name = EXCLUDED.org_name,
                        org_name_en = EXCLUDED.org_name_en,
                        provider_type = EXCLUDED.provider_type,
                        region = EXCLUDED.region,
                        city = EXCLUDED.city,
                        country_code = EXCLUDED.country_code,
                        description = EXCLUDED.description,
                        ip_ranges = EXCLUDED.ip_ranges,
                        is_active = EXCLUDED.is_active,
                        updated_at = NOW()
                """
                
                ip_ranges_json = None
                if asn_record.ip_ranges:
                    ip_ranges_json = json.dumps(asn_record.ip_ranges)
                
                # Поддерживаем как объект ASNRecord, так и dict
                if hasattr(asn_record, 'asn'):
                    # Это объект ASNRecord
                    asn_num = asn_record.asn
                    org_name = asn_record.org_name
                    org_name_en = getattr(asn_record, 'org_name_en', None)
                    provider_type = getattr(asn_record, 'provider_type', None)
                    region = getattr(asn_record, 'region', None)
                    city = getattr(asn_record, 'city', None)
                    country_code = getattr(asn_record, 'country_code', 'RU')
                    description = getattr(asn_record, 'description', None)
                    ip_ranges = getattr(asn_record, 'ip_ranges', None)
                else:
                    # Это dict
                    asn_num = asn_record.get('asn')
                    org_name = asn_record.get('org_name', f'AS{asn_num}')
                    org_name_en = asn_record.get('org_name_en')
                    provider_type = asn_record.get('provider_type')
                    region = asn_record.get('region')
                    city = asn_record.get('city')
                    country_code = asn_record.get('country_code', 'RU')
                    description = asn_record.get('description')
                    ip_ranges = asn_record.get('ip_ranges')
                
                if ip_ranges:
                    ip_ranges_json = json.dumps(ip_ranges) if not isinstance(ip_ranges, str) else ip_ranges
                else:
                    ip_ranges_json = None
                
                await conn.execute(
                    query,
                    asn_num,
                    org_name,
                    org_name_en,
                    provider_type,
                    region,
                    city,
                    country_code,
                    description,
                    ip_ranges_json,
                    True  # is_active
                )
                
                return True
            
        except Exception as e:
            logger.error("Error saving ASN record %d: %s", asn_record.asn if hasattr(asn_record, 'asn') else '?', e, exc_info=True)
            return False
    
    async def get_asn_by_provider_type(self, provider_type: str) -> List[Dict[str, Any]]:
        """
        Получить список ASN по типу провайдера.
        
        Args:
            provider_type: Тип провайдера (mobile/residential/datacenter/vpn/isp)
        
        Returns:
            Список записей ASN
        """
        if not self.is_connected:
            return []
        
        try:
            async with self.acquire() as conn:
                query = """
                    SELECT asn, org_name, org_name_en, provider_type, region, city
                    FROM asn_russia
                    WHERE provider_type = $1 AND is_active = true
                    ORDER BY org_name
                """
                rows = await conn.fetch(query, provider_type)
                return [dict(row) for row in rows]
            
        except Exception as e:
            logger.error("Error getting ASN by provider type '%s': %s", provider_type, e, exc_info=True)
            return []
    
    async def update_asn_sync_time(self):
        """Обновить время последней синхронизации ASN базы."""
        if not self.is_connected:
            return
        
        try:
            async with self.acquire() as conn:
                # Обновляем время синхронизации для всех активных записей
                query = """
                    UPDATE asn_russia
                    SET last_synced_at = NOW()
                    WHERE is_active = true
                """
                await conn.execute(query)
            
        except Exception as e:
            logger.error("Error updating ASN sync time: %s", e, exc_info=True)


    # ==================== Violations ====================

    async def save_violation(
        self,
        user_uuid: str,
        score: float,
        recommended_action: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        telegram_id: Optional[int] = None,
        confidence: Optional[float] = None,
        temporal_score: Optional[float] = None,
        geo_score: Optional[float] = None,
        asn_score: Optional[float] = None,
        profile_score: Optional[float] = None,
        device_score: Optional[float] = None,
        ip_addresses: Optional[List[str]] = None,
        countries: Optional[List[str]] = None,
        cities: Optional[List[str]] = None,
        asn_types: Optional[List[str]] = None,
        os_list: Optional[List[str]] = None,
        client_list: Optional[List[str]] = None,
        reasons: Optional[List[str]] = None,
        simultaneous_connections: Optional[int] = None,
        unique_ips_count: Optional[int] = None,
        device_limit: Optional[int] = None,
        impossible_travel: bool = False,
        is_mobile: bool = False,
        is_datacenter: bool = False,
        is_vpn: bool = False,
        raw_breakdown: Optional[str] = None
    ) -> Optional[int]:
        """
        Сохранить нарушение в базу данных.

        Returns:
            ID созданной записи или None при ошибке
        """
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                result = await conn.fetchval(
                    """
                    INSERT INTO violations (
                        user_uuid, username, email, telegram_id,
                        score, recommended_action, confidence,
                        temporal_score, geo_score, asn_score, profile_score, device_score,
                        ip_addresses, countries, cities, asn_types, os_list, client_list, reasons,
                        simultaneous_connections, unique_ips_count, device_limit,
                        impossible_travel, is_mobile, is_datacenter, is_vpn,
                        raw_breakdown, detected_at
                    )
                    VALUES (
                        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12,
                        $13, $14, $15, $16, $17, $18, $19, $20, $21, $22,
                        $23, $24, $25, $26, $27, NOW()
                    )
                    RETURNING id
                    """,
                    user_uuid, username, email, telegram_id,
                    score, recommended_action, confidence,
                    temporal_score, geo_score, asn_score, profile_score, device_score,
                    ip_addresses, countries, cities, asn_types, os_list, client_list, reasons,
                    simultaneous_connections, unique_ips_count, device_limit,
                    impossible_travel, is_mobile, is_datacenter, is_vpn,
                    raw_breakdown
                )
                return result

        except Exception as e:
            logger.error("Error saving violation for user %s: %s", user_uuid, e, exc_info=True)
            return None

    async def get_violations_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 0.0,
        limit: int = 1000
    ) -> List[Dict[str, Any]]:
        """
        Получить нарушения за указанный период.

        Args:
            start_date: Начало периода
            end_date: Конец периода
            min_score: Минимальный скор (по умолчанию 0)
            limit: Максимальное количество записей

        Returns:
            Список нарушений
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    ORDER BY detected_at DESC
                    LIMIT $4
                    """,
                    start_date, end_date, min_score, limit
                )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting violations for period: %s", e, exc_info=True)
            return []

    async def get_violations_stats_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 0.0
    ) -> Dict[str, Any]:
        """
        Получить статистику нарушений за период.

        Returns:
            Словарь со статистикой
        """
        if not self.is_connected:
            return {
                'total': 0,
                'critical': 0,
                'warning': 0,
                'monitor': 0,
                'unique_users': 0,
                'avg_score': 0.0,
                'max_score': 0.0
            }

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE score >= 80) as critical,
                        COUNT(*) FILTER (WHERE score >= 50 AND score < 80) as warning,
                        COUNT(*) FILTER (WHERE score >= 30 AND score < 50) as monitor,
                        COUNT(DISTINCT user_uuid) as unique_users,
                        COALESCE(AVG(score), 0) as avg_score,
                        COALESCE(MAX(score), 0) as max_score
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    """,
                    start_date, end_date, min_score
                )
                return dict(row) if row else {
                    'total': 0,
                    'critical': 0,
                    'warning': 0,
                    'monitor': 0,
                    'unique_users': 0,
                    'avg_score': 0.0,
                    'max_score': 0.0
                }

        except Exception as e:
            logger.error("Error getting violations stats: %s", e, exc_info=True)
            return {
                'total': 0,
                'critical': 0,
                'warning': 0,
                'monitor': 0,
                'unique_users': 0,
                'avg_score': 0.0,
                'max_score': 0.0
            }

    async def get_top_violators_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Получить топ нарушителей за период.

        Returns:
            Список пользователей с количеством и максимальным скором нарушений
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        user_uuid,
                        MAX(username) as username,
                        MAX(email) as email,
                        MAX(telegram_id) as telegram_id,
                        COUNT(*) as violations_count,
                        MAX(score) as max_score,
                        AVG(score) as avg_score,
                        MAX(detected_at) as last_violation_at,
                        ARRAY_AGG(DISTINCT recommended_action) as actions
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    GROUP BY user_uuid
                    ORDER BY violations_count DESC, max_score DESC
                    LIMIT $4
                    """,
                    start_date, end_date, min_score, limit
                )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting top violators: %s", e, exc_info=True)
            return []

    async def get_violations_by_country(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0
    ) -> Dict[str, int]:
        """
        Получить распределение нарушений по странам.

        Returns:
            Словарь {страна: количество}
        """
        if not self.is_connected:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        UNNEST(countries) as country,
                        COUNT(*) as count
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    AND countries IS NOT NULL
                    GROUP BY country
                    ORDER BY count DESC
                    """,
                    start_date, end_date, min_score
                )
                return {row['country']: row['count'] for row in rows}

        except Exception as e:
            logger.error("Error getting violations by country: %s", e, exc_info=True)
            return {}

    async def get_violations_by_action(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 0.0
    ) -> Dict[str, int]:
        """
        Получить распределение нарушений по рекомендуемым действиям.

        Returns:
            Словарь {действие: количество}
        """
        if not self.is_connected:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        recommended_action,
                        COUNT(*) as count
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    GROUP BY recommended_action
                    ORDER BY count DESC
                    """,
                    start_date, end_date, min_score
                )
                return {row['recommended_action']: row['count'] for row in rows}

        except Exception as e:
            logger.error("Error getting violations by action: %s", e, exc_info=True)
            return {}

    async def get_violations_by_asn_type(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0
    ) -> Dict[str, int]:
        """
        Получить распределение нарушений по типам провайдеров.

        Returns:
            Словарь {тип: количество}
        """
        if not self.is_connected:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        UNNEST(asn_types) as asn_type,
                        COUNT(*) as count
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    AND asn_types IS NOT NULL
                    GROUP BY asn_type
                    ORDER BY count DESC
                    """,
                    start_date, end_date, min_score
                )
                return {row['asn_type']: row['count'] for row in rows}

        except Exception as e:
            logger.error("Error getting violations by ASN type: %s", e, exc_info=True)
            return {}

    async def get_user_violations(
        self,
        user_uuid: str,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Получить историю нарушений пользователя.

        Args:
            user_uuid: UUID пользователя
            days: Количество дней истории
            limit: Максимальное количество записей

        Returns:
            Список нарушений
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM violations
                    WHERE user_uuid = $1
                    AND detected_at > NOW() - INTERVAL '%s days'
                    ORDER BY detected_at DESC
                    LIMIT $2
                    """.replace('%s', str(days)),
                    user_uuid, limit
                )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting user violations: %s", e, exc_info=True)
            return []

    async def update_violation_action(
        self,
        violation_id: int,
        action_taken: str,
        admin_telegram_id: int
    ) -> bool:
        """
        Обновить принятое действие по нарушению.

        Args:
            violation_id: ID нарушения
            action_taken: Принятое действие
            admin_telegram_id: Telegram ID администратора

        Returns:
            True если успешно
        """
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violations
                    SET action_taken = $1,
                        action_taken_at = NOW(),
                        action_taken_by = $2
                    WHERE id = $3
                    """,
                    action_taken, admin_telegram_id, violation_id
                )
                return result == "UPDATE 1"

        except Exception as e:
            logger.error("Error updating violation action: %s", e, exc_info=True)
            return False

    async def mark_violation_notified(self, violation_id: int) -> bool:
        """Отметить нарушение как отправленное в уведомлении."""
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violations
                    SET notified_at = NOW()
                    WHERE id = $1
                    """,
                    violation_id
                )
                return result == "UPDATE 1"

        except Exception as e:
            logger.error("Error marking violation as notified: %s", e, exc_info=True)
            return False

    # ==================== Violation Reports ====================

    async def save_violation_report(
        self,
        report_type: str,
        period_start: datetime,
        period_end: datetime,
        total_violations: int,
        critical_count: int,
        warning_count: int,
        monitor_count: int,
        unique_users: int,
        prev_total_violations: Optional[int] = None,
        trend_percent: Optional[float] = None,
        top_violators: Optional[str] = None,
        by_country: Optional[str] = None,
        by_action: Optional[str] = None,
        by_asn_type: Optional[str] = None,
        message_text: Optional[str] = None
    ) -> Optional[int]:
        """
        Сохранить отчёт в базу данных.

        Returns:
            ID созданного отчёта или None при ошибке
        """
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                result = await conn.fetchval(
                    """
                    INSERT INTO violation_reports (
                        report_type, period_start, period_end,
                        total_violations, critical_count, warning_count, monitor_count, unique_users,
                        prev_total_violations, trend_percent,
                        top_violators, by_country, by_action, by_asn_type,
                        message_text, generated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW())
                    RETURNING id
                    """,
                    report_type, period_start, period_end,
                    total_violations, critical_count, warning_count, monitor_count, unique_users,
                    prev_total_violations, trend_percent,
                    top_violators, by_country, by_action, by_asn_type,
                    message_text
                )
                return result

        except Exception as e:
            logger.error("Error saving violation report: %s", e, exc_info=True)
            return None

    async def mark_report_sent(self, report_id: int) -> bool:
        """Отметить отчёт как отправленный."""
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violation_reports
                    SET sent_at = NOW()
                    WHERE id = $1
                    """,
                    report_id
                )
                return result == "UPDATE 1"

        except Exception as e:
            logger.error("Error marking report as sent: %s", e, exc_info=True)
            return False

    async def get_last_report(self, report_type: str) -> Optional[Dict[str, Any]]:
        """
        Получить последний отчёт указанного типа.

        Args:
            report_type: Тип отчёта (daily/weekly/monthly)

        Returns:
            Данные отчёта или None
        """
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM violation_reports
                    WHERE report_type = $1
                    ORDER BY period_end DESC
                    LIMIT 1
                    """,
                    report_type
                )
                return dict(row) if row else None

        except Exception as e:
            logger.error("Error getting last report: %s", e, exc_info=True)
            return None

    async def get_reports_history(
        self,
        report_type: Optional[str] = None,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Получить историю отчётов.

        Args:
            report_type: Тип отчёта (опционально)
            limit: Максимальное количество записей

        Returns:
            Список отчётов
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                if report_type:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM violation_reports
                        WHERE report_type = $1
                        ORDER BY period_end DESC
                        LIMIT $2
                        """,
                        report_type, limit
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM violation_reports
                        ORDER BY period_end DESC
                        LIMIT $1
                        """,
                        limit
                    )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting reports history: %s", e, exc_info=True)
            return []


    # ==================== HWID Devices ====================

    async def upsert_hwid_device(
        self,
        user_uuid: str,
        hwid: str,
        platform: Optional[str] = None,
        os_version: Optional[str] = None,
        app_version: Optional[str] = None,
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None
    ) -> bool:
        """
        Добавить или обновить HWID устройство.

        Returns:
            True если успешно
        """
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO user_hwid_devices (
                        user_uuid, hwid, platform, os_version, app_version,
                        created_at, updated_at, synced_at
                    )
                    VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()), COALESCE($7, NOW()), NOW())
                    ON CONFLICT (user_uuid, hwid) DO UPDATE SET
                        platform = COALESCE(EXCLUDED.platform, user_hwid_devices.platform),
                        os_version = COALESCE(EXCLUDED.os_version, user_hwid_devices.os_version),
                        app_version = COALESCE(EXCLUDED.app_version, user_hwid_devices.app_version),
                        updated_at = COALESCE(EXCLUDED.updated_at, NOW()),
                        synced_at = NOW()
                    """,
                    user_uuid, hwid, platform, os_version, app_version, created_at, updated_at
                )
                return True

        except Exception as e:
            logger.error("Error upserting HWID device for user %s: %s", user_uuid, e, exc_info=True)
            return False

    async def delete_hwid_device(self, user_uuid: str, hwid: str) -> bool:
        """
        Удалить HWID устройство.

        Returns:
            True если успешно
        """
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM user_hwid_devices WHERE user_uuid = $1 AND hwid = $2",
                    user_uuid, hwid
                )
                return "DELETE" in result

        except Exception as e:
            logger.error("Error deleting HWID device for user %s: %s", user_uuid, e, exc_info=True)
            return False

    async def delete_all_user_hwid_devices(self, user_uuid: str) -> int:
        """
        Удалить все HWID устройства пользователя.

        Returns:
            Количество удалённых записей
        """
        if not self.is_connected:
            return 0

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM user_hwid_devices WHERE user_uuid = $1",
                    user_uuid
                )
                # Parse "DELETE X" to get count
                if result and "DELETE" in result:
                    try:
                        return int(result.split()[1])
                    except (IndexError, ValueError):
                        return 0
                return 0

        except Exception as e:
            logger.error("Error deleting all HWID devices for user %s: %s", user_uuid, e, exc_info=True)
            return 0

    async def get_user_hwid_devices(self, user_uuid: str) -> List[Dict[str, Any]]:
        """
        Получить список HWID устройств пользователя.

        Returns:
            Список устройств с полями: hwid, platform, os_version, app_version, created_at, updated_at
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT hwid, platform, os_version, app_version, created_at, updated_at
                    FROM user_hwid_devices
                    WHERE user_uuid = $1
                    ORDER BY created_at DESC
                    """,
                    user_uuid
                )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting HWID devices for user %s: %s", user_uuid, e, exc_info=True)
            return []

    async def get_user_hwid_devices_count(self, user_uuid: str) -> int:
        """
        Получить количество HWID устройств пользователя.

        Returns:
            Количество устройств
        """
        if not self.is_connected:
            return 0

        try:
            async with self.acquire() as conn:
                result = await conn.fetchval(
                    "SELECT COUNT(*) FROM user_hwid_devices WHERE user_uuid = $1",
                    user_uuid
                )
                return result or 0

        except Exception as e:
            logger.error("Error getting HWID devices count for user %s: %s", user_uuid, e, exc_info=True)
            return 0

    async def sync_user_hwid_devices(
        self,
        user_uuid: str,
        devices: List[Dict[str, Any]]
    ) -> int:
        """
        Синхронизировать HWID устройства пользователя.
        Удаляет старые устройства и добавляет новые.

        Args:
            user_uuid: UUID пользователя
            devices: Список устройств из API

        Returns:
            Количество синхронизированных устройств
        """
        if not self.is_connected:
            return 0

        try:
            async with self.acquire() as conn:
                async with conn.transaction():
                    # Получаем текущие HWID
                    current_hwids = set()
                    rows = await conn.fetch(
                        "SELECT hwid FROM user_hwid_devices WHERE user_uuid = $1",
                        user_uuid
                    )
                    current_hwids = {row['hwid'] for row in rows}

                    # Собираем новые HWID
                    new_hwids = set()
                    for device in devices:
                        hwid = device.get('hwid')
                        if hwid:
                            new_hwids.add(hwid)

                    # Удаляем устройства, которых больше нет
                    to_delete = current_hwids - new_hwids
                    if to_delete:
                        await conn.execute(
                            "DELETE FROM user_hwid_devices WHERE user_uuid = $1 AND hwid = ANY($2)",
                            user_uuid, list(to_delete)
                        )
                        logger.debug("Deleted %d old HWID devices for user %s", len(to_delete), user_uuid)

                    # Добавляем/обновляем устройства
                    synced = 0
                    for device in devices:
                        hwid = device.get('hwid')
                        if not hwid:
                            continue

                        platform = device.get('platform')
                        os_version = device.get('osVersion')
                        app_version = device.get('appVersion')
                        created_at = _parse_timestamp(device.get('createdAt'))
                        updated_at = _parse_timestamp(device.get('updatedAt'))

                        await conn.execute(
                            """
                            INSERT INTO user_hwid_devices (
                                user_uuid, hwid, platform, os_version, app_version,
                                created_at, updated_at, synced_at
                            )
                            VALUES ($1, $2, $3, $4, $5, COALESCE($6, NOW()), COALESCE($7, NOW()), NOW())
                            ON CONFLICT (user_uuid, hwid) DO UPDATE SET
                                platform = COALESCE(EXCLUDED.platform, user_hwid_devices.platform),
                                os_version = COALESCE(EXCLUDED.os_version, user_hwid_devices.os_version),
                                app_version = COALESCE(EXCLUDED.app_version, user_hwid_devices.app_version),
                                updated_at = COALESCE(EXCLUDED.updated_at, NOW()),
                                synced_at = NOW()
                            """,
                            user_uuid, hwid, platform, os_version, app_version, created_at, updated_at
                        )
                        synced += 1

                    return synced

        except Exception as e:
            logger.error("Error syncing HWID devices for user %s: %s", user_uuid, e, exc_info=True)
            return 0

    async def get_all_hwid_devices_stats(self) -> Dict[str, Any]:
        """
        Получить статистику по всем HWID устройствам.

        Returns:
            Словарь со статистикой: total_devices, unique_users, by_platform
        """
        if not self.is_connected:
            return {'total_devices': 0, 'unique_users': 0, 'by_platform': {}}

        try:
            async with self.acquire() as conn:
                # Общая статистика
                stats = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total_devices,
                        COUNT(DISTINCT user_uuid) as unique_users
                    FROM user_hwid_devices
                    """
                )

                # Статистика по платформам
                platform_rows = await conn.fetch(
                    """
                    SELECT
                        COALESCE(platform, 'unknown') as platform,
                        COUNT(*) as count
                    FROM user_hwid_devices
                    GROUP BY platform
                    ORDER BY count DESC
                    """
                )

                by_platform = {row['platform']: row['count'] for row in platform_rows}

                return {
                    'total_devices': stats['total_devices'] if stats else 0,
                    'unique_users': stats['unique_users'] if stats else 0,
                    'by_platform': by_platform
                }

        except Exception as e:
            logger.error("Error getting HWID devices stats: %s", e, exc_info=True)
            return {'total_devices': 0, 'unique_users': 0, 'by_platform': {}}


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
