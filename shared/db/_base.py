"""
Database base class — connection pool, schema init, migrations.
"""
import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from contextlib import asynccontextmanager

import asyncpg
from asyncpg import Pool, Connection

from shared.config import get_shared_settings as get_settings
from shared.logger import logger
from shared.metrics import VIOLATIONS_DETECTED, SYNC_RUNS


# SQL schema for creating tables
SCHEMA_SQL = """
-- Пользователи (основные данные для быстрого поиска)
CREATE TABLE IF NOT EXISTS users (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    id BIGINT,
    short_uuid VARCHAR(16),
    username VARCHAR(255),
    subscription_uuid UUID,
    telegram_id BIGINT,
    email VARCHAR(255),
    tag VARCHAR(16),
    description TEXT,
    status VARCHAR(50),
    traffic_limit_strategy VARCHAR(20) DEFAULT 'NO_RESET',
    expire_at TIMESTAMP WITH TIME ZONE,
    traffic_limit_bytes BIGINT,
    used_traffic_bytes BIGINT,
    hwid_device_limit INTEGER,
    external_squad_uuid UUID,
    created_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data JSONB,
    raw_used_traffic_bytes BIGINT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);
CREATE INDEX IF NOT EXISTS idx_users_short_uuid ON users(short_uuid);
CREATE INDEX IF NOT EXISTS idx_users_subscription_uuid ON users(subscription_uuid);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id ON users(id);

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
    cpu_usage FLOAT,
    cpu_cores INTEGER,
    memory_usage FLOAT,
    memory_total_bytes BIGINT,
    memory_used_bytes BIGINT,
    disk_usage FLOAT,
    disk_total_bytes BIGINT,
    disk_used_bytes BIGINT,
    disk_read_speed_bps BIGINT DEFAULT 0,
    disk_write_speed_bps BIGINT DEFAULT 0,
    uptime_seconds INTEGER,
    metrics_updated_at TIMESTAMP WITH TIME ZONE,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    raw_data JSONB
);

CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE INDEX IF NOT EXISTS idx_nodes_is_connected ON nodes(is_connected);
CREATE INDEX IF NOT EXISTS idx_nodes_agent_token ON nodes(agent_token) WHERE agent_token IS NOT NULL;

-- Снимки метрик нод (для истории)
CREATE TABLE IF NOT EXISTS node_metrics_snapshots (
    id BIGSERIAL PRIMARY KEY,
    node_uuid UUID NOT NULL REFERENCES nodes(uuid) ON DELETE CASCADE,
    cpu_usage FLOAT,
    cpu_cores INTEGER,
    memory_usage FLOAT,
    memory_total_bytes BIGINT,
    memory_used_bytes BIGINT,
    disk_usage FLOAT,
    disk_total_bytes BIGINT,
    disk_used_bytes BIGINT,
    disk_read_speed_bps BIGINT DEFAULT 0,
    disk_write_speed_bps BIGINT DEFAULT 0,
    uptime_seconds INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_nms_node_created ON node_metrics_snapshots(node_uuid, created_at);

-- Торрент-события
CREATE TABLE IF NOT EXISTS torrent_events (
    id BIGSERIAL PRIMARY KEY,
    user_uuid UUID NOT NULL,
    user_id BIGINT,
    node_uuid UUID NOT NULL,
    ip_address VARCHAR(45) NOT NULL,
    destination VARCHAR(255) NOT NULL,
    inbound_tag VARCHAR(100) DEFAULT '',
    outbound_tag VARCHAR(100) DEFAULT 'TORRENT',
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    detected_by VARCHAR(32) NOT NULL DEFAULT 'xray_routing'
);
CREATE INDEX IF NOT EXISTS idx_te_user_date ON torrent_events(user_uuid, detected_at);
CREATE INDEX IF NOT EXISTS idx_te_detected ON torrent_events(detected_at);

-- Хосты
CREATE TABLE IF NOT EXISTS hosts (
    uuid UUID PRIMARY KEY,
    remark VARCHAR(255),
    address VARCHAR(255),
    port INTEGER,
    is_disabled BOOLEAN DEFAULT FALSE,
    is_hidden BOOLEAN DEFAULT FALSE,
    tag VARCHAR(32),
    security_layer VARCHAR(20) DEFAULT 'DEFAULT',
    server_description VARCHAR(30),
    view_position INTEGER DEFAULT 0,
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

-- Трафик пользователей по нодам (синхронизируется из Remnawave API)
CREATE TABLE IF NOT EXISTS user_node_traffic (
    user_uuid UUID REFERENCES users(uuid) ON DELETE CASCADE,
    user_id BIGINT,
    node_uuid UUID REFERENCES nodes(uuid) ON DELETE CASCADE,
    traffic_bytes BIGINT NOT NULL DEFAULT 0,
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    PRIMARY KEY (user_uuid, node_uuid)
);

CREATE INDEX IF NOT EXISTS idx_user_node_traffic_node ON user_node_traffic(node_uuid);
CREATE INDEX IF NOT EXISTS idx_user_node_traffic_bytes ON user_node_traffic(traffic_bytes DESC);

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
    user_id BIGINT,
    ip_address INET,
    node_uuid UUID REFERENCES nodes(uuid) ON DELETE SET NULL,
    connected_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    disconnected_at TIMESTAMP WITH TIME ZONE,
    device_info JSONB
);

CREATE INDEX IF NOT EXISTS idx_user_connections_user ON user_connections(user_uuid, connected_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_connections_ip ON user_connections(ip_address);
CREATE INDEX IF NOT EXISTS idx_user_connections_node ON user_connections(node_uuid);
CREATE INDEX IF NOT EXISTS idx_user_connections_user_active ON user_connections(user_uuid, disconnected_at, connected_at DESC);

-- HWID устройства пользователей
CREATE TABLE IF NOT EXISTS user_hwid_devices (
    id SERIAL PRIMARY KEY,
    user_uuid UUID NOT NULL,
    user_id BIGINT,
    hwid VARCHAR(255) NOT NULL,
    platform VARCHAR(50),
    os_version VARCHAR(100),
    device_model VARCHAR(255),
    app_version VARCHAR(50),
    user_agent TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- проставлено, если устройство отвязали: строка остаётся, чтобы HWID
    -- помнил всех, кого на нём видели (детект повторных триалов)
    removed_at TIMESTAMP WITH TIME ZONE
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_hwid_devices_user_hwid ON user_hwid_devices(user_uuid, hwid);
CREATE INDEX IF NOT EXISTS idx_hwid_devices_hwid_removed ON user_hwid_devices(hwid, removed_at);
CREATE INDEX IF NOT EXISTS idx_hwid_devices_user_uuid ON user_hwid_devices(user_uuid);
CREATE INDEX IF NOT EXISTS idx_hwid_devices_platform ON user_hwid_devices(platform);
CREATE INDEX IF NOT EXISTS idx_hwid_devices_hwid ON user_hwid_devices(hwid);

-- Индексы для violations (таблица создаётся через Alembic)
CREATE INDEX IF NOT EXISTS idx_violations_user_detected ON violations(user_uuid, detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_violations_reasons_gin ON violations USING GIN(reasons);

-- Индексы для violation_whitelist (таблица создаётся через Alembic)
CREATE INDEX IF NOT EXISTS idx_violation_whitelist_user ON violation_whitelist(user_uuid);

-- Partial-индексы для cleanup-запросов (ускоряют DELETE старых записей)
CREATE INDEX IF NOT EXISTS idx_uc_cleanup ON user_connections(connected_at) INCLUDE (id) WHERE disconnected_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_violations_cleanup ON violations(detected_at) INCLUDE (id) WHERE action_taken IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_nms_created_at ON node_metrics_snapshots(created_at);

-- user_baselines table is managed by Alembic migration 0041

-- admin_permissions table is managed by Alembic migration 0009
CREATE INDEX IF NOT EXISTS idx_admin_permissions_role_id ON admin_permissions(role_id);
"""


class DatabaseBase:
    """
    Async database service for PostgreSQL operations.
    Provides CRUD operations for users, nodes, hosts, and config profiles.
    """
    
    _RAW_DATA_ID_CACHE_TTL = 60  # seconds
    _RAW_DATA_ID_CACHE_MAX = 10_000  # max entries before eviction

    def __init__(self):
        self._pool: Optional[Pool] = None
        self._initialized: bool = False
        self._lock = asyncio.Lock()
        self._whitelist_cache: Dict[str, tuple] = {}  # {user_uuid: ((bool, Optional[List[str]]), timestamp)}
        self._whitelist_table_available: Optional[bool] = None  # None = not checked yet
        self._whitelist_column_available: Optional[bool] = None  # excluded_analyzers column
        self._raw_data_id_cache: Dict[str, tuple] = {}  # {user_id: (uuid_or_None, monotonic_ts)}
    
    @property
    def is_connected(self) -> bool:
        """Check if database connection is established."""
        return self._pool is not None and not self._pool._closed
    
    async def connect(self, database_url: str = None, max_retries: int = 5, retry_delay: float = 2.0) -> bool:
        """
        Initialize database connection pool with retry logic.
        Returns True if connection successful, False otherwise.

        Args:
            database_url: Optional database URL. If not provided, reads from
                          DATABASE_URL env var or Settings.
            max_retries: Maximum number of connection attempts (default 5).
            retry_delay: Initial delay between retries in seconds, doubles each attempt.
        """
        import os

        # Get database URL: parameter > env var > settings (fallback)
        if not database_url:
            database_url = os.environ.get('DATABASE_URL')
        if not database_url:
            try:
                settings = get_settings()
                database_url = getattr(settings, 'database_url', None)
            except Exception as e:
                logger.debug("Could not load Settings for database_url: %s", e)

        if not database_url:
            logger.warning("DATABASE_URL not configured, database features disabled")
            return False

        # Get pool size settings
        min_size = int(os.environ.get('DB_POOL_MIN_SIZE', 5))
        max_size = int(os.environ.get('DB_POOL_MAX_SIZE', 50))
        try:
            settings = get_settings()
            min_size = getattr(settings, 'db_pool_min_size', min_size)
            max_size = getattr(settings, 'db_pool_max_size', max_size)
        except Exception as e:
            logger.debug("Pool settings from config unavailable: %s", e)

        async with self._lock:
            if self._pool is not None:
                return True

            delay = retry_delay
            for attempt in range(1, max_retries + 1):
                try:
                    logger.debug("Connecting to PostgreSQL (attempt %d/%d)...", attempt, max_retries)
                    self._pool = await asyncpg.create_pool(
                        dsn=database_url,
                        min_size=min_size,
                        max_size=max_size,
                        command_timeout=30,
                        # Закрывать idle-соединения старше 5 минут — предотвращает
                        # "connection lost" и последующие authentication-спайки в PostgreSQL
                        max_inactive_connection_lifetime=300,
                        # Увеличиваем кэш prepared statements (по умолчанию 100)
                        # чтобы снизить PARSE-запросы при большом количестве разных SQL
                        statement_cache_size=200,
                        server_settings={
                            # Автоматически убивать транзакции зависшие в "idle in transaction"
                            # дольше 30 секунд — главная причина накопления соединений и CPU-спайков
                            'idle_in_transaction_session_timeout': '30000',
                            # Убивать запросы выполняющиеся дольше 60 секунд
                            'statement_timeout': '60000',
                        },
                    )

                    # Initialize schema
                    await self._init_schema()
                    self._initialized = True

                    logger.info("✅ Database connection established")
                    return True

                except Exception as e:
                    self._pool = None
                    if attempt < max_retries:
                        logger.warning(
                            "⚠️ Database connection attempt %d/%d failed: %s. Retrying in %.0fs...",
                            attempt, max_retries, e, delay,
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * 2, 30)
                    else:
                        logger.error("❌ Failed to connect to database after %d attempts: %s", max_retries, e)
                        return False

        return False
    
    async def disconnect(self) -> None:
        """Close database connection pool."""
        async with self._lock:
            if self._pool is not None:
                await self._pool.close()
                self._pool = None
                self._initialized = False
                logger.info("🗄️ Database disconnected")
    
    async def _init_schema(self) -> None:
        """Initialize database schema (create tables if not exist)."""
        if self._pool is None:
            return

        async with self._pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)
            # Migrations for existing tables
            await self._run_migrations(conn)
            logger.debug("Database schema initialized")

    # Whitelist of valid column names for ALTER TABLE migrations
    _SAFE_HWID_COLUMNS = frozenset({"device_model", "user_agent", "removed_at"})
    _SAFE_USER_COLUMNS = frozenset({"tag", "description", "traffic_limit_strategy", "external_squad_uuid"})
    _SAFE_HOST_COLUMNS = frozenset({"is_hidden", "tag", "security_layer", "server_description", "view_position"})

    async def _run_migrations(self, conn) -> None:
        """Apply incremental migrations for existing tables."""
        # Add device_model and user_agent columns to user_hwid_devices if missing
        # removed_at дублирует alembic 0101 намеренно: обращения к колонке идут из
        # синка, который может стартовать раньше, чем доедут миграции
        for col, col_type in [("device_model", "VARCHAR(255)"), ("user_agent", "TEXT"),
                              ("removed_at", "TIMESTAMP WITH TIME ZONE")]:
            if col not in self._SAFE_HWID_COLUMNS:
                logger.warning("Skipping unknown column: %s", col)
                continue
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'user_hwid_devices' AND column_name = $1",
                col,
            )
            if not exists:
                await conn.execute(f"ALTER TABLE user_hwid_devices ADD COLUMN {col} {col_type}")
                logger.info("Migration: added column %s to user_hwid_devices", col)

        # v2.6.0: Add new user columns
        user_new_cols = [
            ("tag", "VARCHAR(16)"),
            ("description", "TEXT"),
            ("traffic_limit_strategy", "VARCHAR(20) DEFAULT 'NO_RESET'"),
            ("external_squad_uuid", "UUID"),
        ]
        for col, col_type in user_new_cols:
            if col not in self._SAFE_USER_COLUMNS:
                logger.warning("Skipping unknown column: %s", col)
                continue
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'users' AND column_name = $1",
                col,
            )
            if not exists:
                await conn.execute(f"ALTER TABLE users ADD COLUMN {col} {col_type}")
                logger.info("Migration: added column %s to users", col)

        # v2.6.0: Add new host columns
        host_new_cols = [
            ("is_hidden", "BOOLEAN DEFAULT FALSE"),
            ("tag", "VARCHAR(32)"),
            ("security_layer", "VARCHAR(20) DEFAULT 'DEFAULT'"),
            ("server_description", "VARCHAR(30)"),
            ("view_position", "INTEGER DEFAULT 0"),
        ]
        for col, col_type in host_new_cols:
            if col not in self._SAFE_HOST_COLUMNS:
                logger.warning("Skipping unknown column: %s", col)
                continue
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'hosts' AND column_name = $1",
                col,
            )
            if not exists:
                await conn.execute(f"ALTER TABLE hosts ADD COLUMN {col} {col_type}")
                logger.info("Migration: added column %s to hosts", col)

        # v3.0.0: Panel numeric user id (users.id + user_id on children).
        # Аналог alembic-миграции 0092 для инсталляций без alembic.
        user_id_tables = (
            "user_connections", "user_hwid_devices", "violations",
            "violation_whitelist", "torrent_events", "subscription_request_history",
            "user_baselines", "user_node_traffic_history", "user_node_traffic",
        )
        for table in user_id_tables:
            try:
                exists = await conn.fetchval(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = $1 AND column_name = 'user_id'",
                    table,
                )
                if not exists:
                    await conn.execute(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_id BIGINT")
                    logger.info("Migration: added column user_id to %s", table)
            except Exception as e:
                logger.warning("Migration: skip user_id column on %s: %s", table, e)
        await conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_id ON users(id)")

        # v3.1.0: правило SRR, обработавшее запрос подписки.
        # Аналог alembic-миграции 0093 для инсталляций без alembic.
        try:
            await conn.execute(
                "ALTER TABLE subscription_request_history "
                "ADD COLUMN IF NOT EXISTS srr_response_type VARCHAR(64)"
            )
            await conn.execute(
                "ALTER TABLE subscription_request_history "
                "ADD COLUMN IF NOT EXISTS srr_rule_name VARCHAR(255)"
            )
        except Exception as e:
            logger.warning("Migration: skip SRR columns on subscription_request_history: %s", e)

        # v2.6.0: Add new indexes (safe with IF NOT EXISTS)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email) WHERE email IS NOT NULL")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_users_tag ON users(tag) WHERE tag IS NOT NULL")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_hosts_tag ON hosts(tag) WHERE tag IS NOT NULL")

        # Remove stale tokens sync metadata (tokens sync removed)
        await conn.execute("DELETE FROM sync_metadata WHERE key = 'tokens'")

    async def run_table_maintenance(self) -> None:
        """Run VACUUM ANALYZE on heavy tables to prevent bloat.

        Should be called periodically (e.g., every 6 hours) for tables with
        high write throughput that may outpace autovacuum.
        """
        if not self.is_connected:
            return

        ALLOWED_TABLES = frozenset({
            "user_connections", "violations",
            "node_metrics_snapshots", "torrent_events",
        })

        for table in ALLOWED_TABLES:
            try:
                async with self._pool.acquire(timeout=60) as conn:
                    await conn.execute(f"VACUUM ANALYZE {table}", timeout=300)
                logger.debug("VACUUM ANALYZE %s completed", table)
            except Exception as e:
                logger.warning("VACUUM ANALYZE %s failed: %s", table, e)

    async def get_table_stats(self) -> List[Dict[str, Any]]:
        """Get size and dead tuple stats for monitoring."""
        if not self.is_connected:
            return []
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        relname AS table_name,
                        n_live_tup AS live_rows,
                        n_dead_tup AS dead_rows,
                        last_autovacuum,
                        last_autoanalyze,
                        pg_size_pretty(pg_total_relation_size(relid)) AS total_size
                    FROM pg_stat_user_tables
                    WHERE relname IN ('user_connections', 'violations',
                                      'node_metrics_snapshots', 'torrent_events', 'users')
                    ORDER BY n_live_tup DESC
                """)
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("get_table_stats failed: %s", e)
            return []


    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        if self._pool is None:
            raise RuntimeError("Database not connected")
        
        async with self._pool.acquire() as conn:
            yield conn
    



def _db_row_to_api_format(row) -> Dict[str, Any]:
    """
    Convert database row to API format.
    If raw_data exists, use it; otherwise build from row fields.
    """
    if row is None:
        return {}
    
    row_dict = dict(row)
    raw_data = row_dict.get("raw_data")
    
    # Metric columns stored separately by node-agent (not in raw_data)
    _METRIC_FIELDS = (
        'cpu_usage', 'cpu_cores', 'memory_usage', 'memory_total_bytes', 'memory_used_bytes',
        'disk_usage', 'disk_total_bytes', 'disk_used_bytes',
        'disk_read_speed_bps', 'disk_write_speed_bps',
        'uptime_seconds', 'metrics_updated_at',
        'agent_v2_connected', 'agent_v2_last_ping', 'agent_ip',
    )
    _INTERNAL_FIELDS = ("created_by_admin_id",)

    if raw_data:
        # Use raw_data if available (contains full API response)
        result = None
        if isinstance(raw_data, str):
            try:
                result = json.loads(raw_data)
            except json.JSONDecodeError:
                pass
        elif isinstance(raw_data, dict):
            result = dict(raw_data)

        if result is not None:
            # Overlay metric columns from DB row onto raw_data
            for field in _METRIC_FIELDS:
                val = row_dict.get(field)
                if val is not None:
                    if isinstance(val, datetime):
                        result[field] = val.isoformat()
                    else:
                        result[field] = val
            for field in _INTERNAL_FIELDS:
                val = row_dict.get(field)
                if val is not None:
                    result["createdByAdminId"] = val
            # Panel v3 identifies users by numeric id and sends no uuid —
            # overlay the local uuid column so the API contract (and the
            # frontend's user-scoped routes) keeps working.
            if "uuid" not in result and row_dict.get("uuid") is not None:
                result["uuid"] = str(row_dict["uuid"])
            return result

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
        "raw_used_traffic_bytes": "rawUsedTrafficBytes",
        "hwid_device_limit": "hwidDeviceLimit",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
        "name": "name",
        "address": "address",
        "port": "port",
        "is_disabled": "isDisabled",
        "is_connected": "isConnected",
        "remark": "remark",
        "created_by_admin_id": "createdByAdminId",
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

    # Also include metric columns in fallback path
    for field in _METRIC_FIELDS:
        val = row_dict.get(field)
        if val is not None:
            if isinstance(val, datetime):
                result[field] = val.isoformat()
            else:
                result[field] = val

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

