"""
Network mixin — user devices (HWID), IP metadata, ASN, HWID devices, blocked IPs.
"""
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from shared.logger import logger
from shared.db._base import _parse_timestamp
from shared.db_schema import (
    ADMIN_TABLE, USERS_TABLE, NODES_TABLE, USER_CONNECTIONS_TABLE, USER_BASELINES_TABLE,
    USER_HWID_DEVICES_TABLE, VIOLATIONS_TABLE, IP_METADATA_TABLE, USER_NODE_TRAFFIC_TABLE,
    USER_NODE_TRAFFIC_HISTORY_TABLE, HOSTS_TABLE, ACCESS_POLICIES_TABLE,
    ACCESS_POLICY_RULES_TABLE, ROLE_ACCESS_POLICIES_TABLE, SUBSCRIPTION_REQUEST_HISTORY_TABLE,
    BLOCKED_IPS_TABLE, HWID_BLACKLIST_TABLE, USER_BLACKLIST_TABLE, ASN_RUSSIA_TABLE,
    NODE_TRAFFIC_SNAPSHOTS_TABLE, ONLINE_USERS_SNAPSHOTS_TABLE, ADMIN_ACCESS_POLICIES_TABLE,
)
from shared.db_query import select_sql, insert_sql, update_sql, delete_sql


class NetworkMixin:
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
                    select_sql(USERS_TABLE, "raw_data", "WHERE uuid = $1"),
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
                row = await conn.fetchrow(
                    select_sql(
                        IP_METADATA_TABLE,
                        """ip_address, country_code, country_name, region, city,
                           latitude, longitude, timezone, asn, asn_org,
                           connection_type, is_proxy, is_vpn, is_tor, is_hosting, is_mobile,
                           created_at, updated_at, last_checked_at""",
                        "WHERE ip_address = $1",
                    ),
                    ip_address,
                )
                
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
                rows = await conn.fetch(
                    select_sql(
                        IP_METADATA_TABLE,
                        """ip_address, country_code, country_name, region, city,
                           latitude, longitude, timezone, asn, asn_org,
                           connection_type, is_proxy, is_vpn, is_tor, is_hosting, is_mobile,
                           created_at, updated_at, last_checked_at""",
                        "WHERE ip_address = ANY($1::text[])",
                    ),
                    ip_addresses,
                )
                
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
                await conn.execute(
                    f"""
                    INSERT INTO {IP_METADATA_TABLE} (
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
                    """,
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
                row = await conn.fetchrow(
                    select_sql(IP_METADATA_TABLE, "last_checked_at", "WHERE ip_address = $1"),
                    ip_address,
                )
                
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
                row = await conn.fetchrow(
                    select_sql(
                        ASN_RUSSIA_TABLE,
                        """asn, org_name, org_name_en, provider_type, region, city,
                           country_code, description, ip_ranges, is_active,
                           created_at, updated_at, last_synced_at""",
                        "WHERE asn = $1 AND is_active = true",
                    ),
                    asn,
                )
                
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
                rows = await conn.fetch(
                    select_sql(
                        ASN_RUSSIA_TABLE,
                        """asn, org_name, org_name_en, provider_type, region, city,
                           country_code, description, is_active""",
                        """WHERE (LOWER(org_name) LIKE LOWER($1) OR LOWER(org_name_en) LIKE LOWER($1))
                          AND is_active = true
                        ORDER BY org_name
                        LIMIT 100""",
                    ),
                    f"%{org_name}%",
                )
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
                    f"""
                    INSERT INTO {ASN_RUSSIA_TABLE} (
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
                    """,
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
                rows = await conn.fetch(
                    select_sql(
                        ASN_RUSSIA_TABLE,
                        "asn, org_name, org_name_en, provider_type, region, city",
                        "WHERE provider_type = $1 AND is_active = true ORDER BY org_name",
                    ),
                    provider_type,
                )
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
                # Обновляем время синхронизации для активных записей, которые давно не обновлялись
                await conn.execute(
                    update_sql(
                        ASN_RUSSIA_TABLE,
                        "last_synced_at = NOW()",
                        "is_active = true AND (last_synced_at IS NULL OR last_synced_at < NOW() - INTERVAL '1 hour')",
                    ),
                )
            
        except Exception as e:
            logger.error("Error updating ASN sync time: %s", e, exc_info=True)



    # ==================== HWID Devices ====================

    async def upsert_hwid_device(
        self,
        user_uuid: str,
        hwid: str,
        platform: Optional[str] = None,
        os_version: Optional[str] = None,
        device_model: Optional[str] = None,
        app_version: Optional[str] = None,
        user_agent: Optional[str] = None,
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

        # Normalize empty strings to None so COALESCE preserves existing DB values
        platform = (platform.strip() if isinstance(platform, str) else platform) or None
        os_version = (os_version.strip() if isinstance(os_version, str) else os_version) or None
        device_model = (device_model.strip() if isinstance(device_model, str) else device_model) or None
        app_version = (app_version.strip() if isinstance(app_version, str) else app_version) or None
        user_agent = (user_agent.strip() if isinstance(user_agent, str) else user_agent) or None

        try:
            async with self.acquire() as conn:
                await conn.execute(
                    f"""
                    INSERT INTO {USER_HWID_DEVICES_TABLE} (
                        user_uuid, hwid, platform, os_version, device_model, app_version,
                        user_agent, created_at, updated_at, synced_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($8, NOW()), COALESCE($9, NOW()), NOW())
                    ON CONFLICT (user_uuid, hwid) DO UPDATE SET
                        platform = COALESCE(EXCLUDED.platform, {USER_HWID_DEVICES_TABLE}.platform),
                        os_version = COALESCE(EXCLUDED.os_version, {USER_HWID_DEVICES_TABLE}.os_version),
                        device_model = COALESCE(EXCLUDED.device_model, {USER_HWID_DEVICES_TABLE}.device_model),
                        app_version = COALESCE(EXCLUDED.app_version, {USER_HWID_DEVICES_TABLE}.app_version),
                        user_agent = COALESCE(EXCLUDED.user_agent, {USER_HWID_DEVICES_TABLE}.user_agent),
                        updated_at = COALESCE(EXCLUDED.updated_at, NOW()),
                        synced_at = NOW()
                    """,
                    user_uuid, hwid, platform, os_version, device_model, app_version,
                    user_agent, created_at, updated_at
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
                    delete_sql(USER_HWID_DEVICES_TABLE, "user_uuid = $1 AND hwid = $2"),
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
                    delete_sql(USER_HWID_DEVICES_TABLE, "user_uuid = $1"),
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
                    select_sql(
                        USER_HWID_DEVICES_TABLE,
                        """hwid, platform, os_version, device_model, app_version,
                           user_agent, created_at, updated_at""",
                        "WHERE user_uuid = $1 ORDER BY created_at DESC",
                    ),
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
                    select_sql(USER_HWID_DEVICES_TABLE, "COUNT(*)", "WHERE user_uuid = $1"),
                    user_uuid
                )
                return result or 0

        except Exception as e:
            logger.error("Error getting HWID devices count for user %s: %s", user_uuid, e, exc_info=True)
            return 0

    async def upsert_srh_records(self, records: List[Dict[str, Any]]) -> int:
        """Сохранить записи Subscription Request History. Возвращает число новых/обновлённых."""
        if not self.is_connected or not records:
            return 0
        rows = []
        for r in records:
            rid = r.get("id") or r.get("request_id")
            uuid_val = r.get("userUuid") or r.get("user_uuid")
            request_at = r.get("requestAt") or r.get("request_at")
            if rid is None or not uuid_val or request_at is None:
                continue
            if isinstance(request_at, str):
                try:
                    request_at = datetime.fromisoformat(request_at.replace("Z", "+00:00"))
                except ValueError:
                    continue
            rows.append((
                int(rid),
                str(uuid_val),
                r.get("requestIp") or r.get("request_ip"),
                r.get("userAgent") or r.get("user_agent"),
                request_at,
            ))
        if not rows:
            return 0
        try:
            async with self.acquire() as conn:
                await conn.executemany(
                    f"""
                    INSERT INTO {SUBSCRIPTION_REQUEST_HISTORY_TABLE} (id, user_uuid, request_ip, user_agent, request_at)
                    VALUES ($1, $2, $3, $4, $5)
                    ON CONFLICT (id) DO UPDATE SET
                        user_uuid = EXCLUDED.user_uuid,
                        request_ip = EXCLUDED.request_ip,
                        user_agent = EXCLUDED.user_agent,
                        request_at = EXCLUDED.request_at,
                        synced_at = NOW()
                    """,
                    rows,
                )
            return len(rows)
        except Exception as e:
            logger.warning("Failed to upsert SRH records: %s", e)
            return 0

    async def get_user_srh_records(
        self,
        user_uuid: str,
        limit: int = 100,
        max_age_days: int = 0,
    ) -> List[Dict[str, Any]]:
        """Получить историю запросов подписки юзера из локальной БД."""
        if not self.is_connected:
            return []
        try:
            async with self.acquire() as conn:
                if max_age_days > 0:
                    rows = await conn.fetch(
                        select_sql(
                            SUBSCRIPTION_REQUEST_HISTORY_TABLE,
                            "id, user_uuid, request_ip, user_agent, request_at",
                            "WHERE user_uuid = $1 AND request_at >= NOW() - $2::interval ORDER BY request_at DESC LIMIT $3",
                        ),
                        user_uuid, f"{max_age_days} days", limit,
                    )
                else:
                    rows = await conn.fetch(
                        select_sql(
                            SUBSCRIPTION_REQUEST_HISTORY_TABLE,
                            "id, user_uuid, request_ip, user_agent, request_at",
                            "WHERE user_uuid = $1 ORDER BY request_at DESC LIMIT $2",
                        ),
                        user_uuid, limit,
                    )
            return [dict(r) for r in rows]
        except Exception as e:
            logger.debug("Failed to get SRH records for %s: %s", user_uuid, e)
            return []

    async def get_srh_max_id(self) -> int:
        """Максимальный id в локальном SRH — точка остановки инкрементального sync."""
        if not self.is_connected:
            return 0
        try:
            async with self.acquire() as conn:
                val = await conn.fetchval(select_sql(SUBSCRIPTION_REQUEST_HISTORY_TABLE, "COALESCE(MAX(id), 0)"))
                return int(val or 0)
        except Exception:
            return 0

    async def cleanup_old_srh(self, keep_days: int = 90) -> int:
        """Удалить SRH записи старше keep_days. Возвращает число удалённых."""
        if not self.is_connected or keep_days <= 0:
            return 0
        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    delete_sql(SUBSCRIPTION_REQUEST_HISTORY_TABLE, "request_at < NOW() - $1::interval"),
                    f"{keep_days} days",
                )
                deleted = int(result.split()[-1]) if result and result.split() else 0
                return deleted
        except Exception as e:
            logger.debug("Failed to cleanup old SRH: %s", e)
            return 0

    async def get_hwid_device_counts_bulk(self) -> Dict[str, int]:
        """
        Получить количество HWID устройств для всех пользователей одним запросом.

        Returns:
            Словарь {user_uuid: count}
        """
        if not self.is_connected:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(USER_HWID_DEVICES_TABLE, "user_uuid, COUNT(*) as cnt", "GROUP BY user_uuid")
                )
                return {str(row["user_uuid"]): row["cnt"] for row in rows}

        except Exception as e:
            logger.error("Error getting bulk HWID device counts: %s", e, exc_info=True)
            return {}

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
                        select_sql(USER_HWID_DEVICES_TABLE, "hwid", "WHERE user_uuid = $1"),
                        user_uuid
                    )
                    current_hwids = {row['hwid'] for row in rows}

                    # Собираем новые HWID (devices может быть списком строк или словарей)
                    new_hwids = set()
                    for device in devices:
                        hwid = device.get('hwid') if isinstance(device, dict) else device
                        if hwid:
                            new_hwids.add(hwid)

                    # Удаляем устройства, которых больше нет
                    to_delete = current_hwids - new_hwids
                    if to_delete:
                        await conn.execute(
                            delete_sql(USER_HWID_DEVICES_TABLE, "user_uuid = $1 AND hwid = ANY($2)"),
                            user_uuid, list(to_delete)
                        )
                        logger.debug("Deleted %d old HWID devices for user %s", len(to_delete), user_uuid)

                    # Добавляем/обновляем устройства
                    synced = 0
                    for device in devices:
                        if isinstance(device, str):
                            hwid = device
                            platform = os_version = device_model = app_version = user_agent = None
                            created_at = updated_at = None
                        else:
                            hwid = device.get('hwid')
                            if not hwid:
                                continue
                            # Normalize empty strings to None so COALESCE preserves existing data
                            platform = device.get('platform') or None
                            os_version = device.get('osVersion') or None
                            device_model = device.get('deviceModel') or None
                            app_version = device.get('appVersion') or None
                            user_agent = device.get('userAgent') or None
                            created_at = _parse_timestamp(device.get('createdAt'))
                            updated_at = _parse_timestamp(device.get('updatedAt'))

                        await conn.execute(
                            f"""
                            INSERT INTO {USER_HWID_DEVICES_TABLE} (
                                user_uuid, hwid, platform, os_version, device_model,
                                app_version, user_agent, created_at, updated_at, synced_at
                            )
                            VALUES ($1, $2, $3, $4, $5, $6, $7, COALESCE($8, NOW()), COALESCE($9, NOW()), NOW())
                            ON CONFLICT (user_uuid, hwid) DO UPDATE SET
                                platform = COALESCE(EXCLUDED.platform, {USER_HWID_DEVICES_TABLE}.platform),
                                os_version = COALESCE(EXCLUDED.os_version, {USER_HWID_DEVICES_TABLE}.os_version),
                                device_model = COALESCE(EXCLUDED.device_model, {USER_HWID_DEVICES_TABLE}.device_model),
                                app_version = COALESCE(EXCLUDED.app_version, {USER_HWID_DEVICES_TABLE}.app_version),
                                user_agent = COALESCE(EXCLUDED.user_agent, {USER_HWID_DEVICES_TABLE}.user_agent),
                                updated_at = COALESCE(EXCLUDED.updated_at, NOW()),
                                synced_at = NOW()
                            """,
                            user_uuid, hwid, platform, os_version, device_model,
                            app_version, user_agent, created_at, updated_at
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
                    select_sql(
                        USER_HWID_DEVICES_TABLE,
                        "COUNT(*) as total_devices, COUNT(DISTINCT user_uuid) as unique_users",
                    ),
                )

                # Статистика по платформам
                platform_rows = await conn.fetch(
                    select_sql(
                        USER_HWID_DEVICES_TABLE,
                        "COALESCE(platform, 'unknown') as platform, COUNT(*) as count",
                        "GROUP BY platform ORDER BY count DESC",
                    ),
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

    async def get_shared_hwids(self, min_users: int = 2, limit: int = 50) -> List[Dict[str, Any]]:
        """Find HWIDs shared across multiple user accounts (for analytics)."""
        if not self.is_connected:
            return []

        # Load trial detection settings
        from shared.config_service import config_service
        trial_tags_raw = config_service.get("violations_trial_tags", "trial")
        trial_tags = [t.strip().lower() for t in trial_tags_raw.split(",") if t.strip()]

        trial_squads_raw = config_service.get("violations_trial_squad_uuids", "[]")
        trial_squads: list = []
        try:
            import json as _json
            parsed = _json.loads(trial_squads_raw)
            if isinstance(parsed, list):
                trial_squads = [s.strip().lower() for s in parsed if isinstance(s, str) and s.strip()]
        except (ValueError, TypeError):
            pass

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    WITH shared AS (
                        SELECT hwid
                        FROM {USER_HWID_DEVICES_TABLE}
                        GROUP BY hwid
                        HAVING COUNT(DISTINCT user_uuid) >= $1
                        ORDER BY COUNT(DISTINCT user_uuid) DESC
                        LIMIT $2
                    )
                    SELECT h.hwid, h.platform, h.device_model, h.app_version,
                           h.created_at as hwid_first_seen,
                           u.uuid::text as user_uuid, u.username, u.status,
                           u.created_at as user_created_at,
                           u.expire_at,
                           u.tag,
                           u.raw_data
                    FROM shared s
                    JOIN {USER_HWID_DEVICES_TABLE} h ON h.hwid = s.hwid
                    JOIN {USERS_TABLE} u ON h.user_uuid = u.uuid
                    ORDER BY h.hwid, h.created_at ASC
                    """,
                    min_users, limit,
                )

                # Group by hwid
                from datetime import timezone as _tz
                now = datetime.now(_tz.utc)
                groups: Dict[str, Dict[str, Any]] = {}
                for r in rows:
                    hwid = r["hwid"]
                    if hwid not in groups:
                        groups[hwid] = {
                            "hwid": hwid,
                            "platform": r["platform"],
                            "device_model": r["device_model"],
                            "user_count": 0,
                            "users": [],
                        }
                    groups[hwid]["user_count"] += 1

                    # Determine is_active from expire_at
                    expire_at = r.get("expire_at")
                    is_active = False
                    if expire_at:
                        if hasattr(expire_at, 'tzinfo') and expire_at.tzinfo is None:
                            expire_at = expire_at.replace(tzinfo=_tz.utc)
                        is_active = expire_at > now

                    # Determine is_trial from tag and internal squads
                    is_trial = False
                    user_tag = (r.get("tag") or "").strip().lower()
                    if user_tag and user_tag in trial_tags:
                        is_trial = True

                    if not is_trial and trial_squads:
                        raw_data = r.get("raw_data")
                        if raw_data:
                            if isinstance(raw_data, str):
                                try:
                                    import json as _json2
                                    raw_data = _json2.loads(raw_data)
                                except (ValueError, TypeError):
                                    raw_data = {}
                            user_squads = raw_data.get("activeInternalSquads") or []
                            if isinstance(user_squads, list):
                                for sq in user_squads:
                                    if isinstance(sq, str) and sq.strip().lower() in trial_squads:
                                        is_trial = True
                                        break

                    groups[hwid]["users"].append({
                        "uuid": r["user_uuid"],
                        "username": r["username"],
                        "status": r["status"],
                        "created_at": r["user_created_at"].isoformat() if r["user_created_at"] else None,
                        "hwid_first_seen": r["hwid_first_seen"].isoformat() if r["hwid_first_seen"] else None,
                        "expire_date": expire_at.isoformat() if expire_at else None,
                        "is_active": is_active,
                        "is_trial": is_trial,
                    })

                # Sort by user_count desc
                result = sorted(groups.values(), key=lambda g: g["user_count"], reverse=True)
                return result

        except Exception as e:
            logger.error("Error getting shared HWIDs: %s", e, exc_info=True)
            return []

    async def get_shared_hwids_for_user(self, user_uuid: str) -> List[Dict[str, Any]]:
        """For a given user, find other users sharing the same HWID(s).

        Each returned group also carries ``self_telegram_id`` (telegram_id of
        the requested user) and ``telegram_id`` on every other user, so the
        violation detector can group sibling accounts: Bedolaga multi-tariff
        mode binds several panel UUIDs to one telegram_id.
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT h2.hwid,
                           u.uuid::text  AS user_uuid,
                           u.username,
                           u.status,
                           u.telegram_id,
                           me.telegram_id AS self_telegram_id
                    FROM {USER_HWID_DEVICES_TABLE} h1
                    JOIN {USERS_TABLE} me ON me.uuid = h1.user_uuid
                    JOIN {USER_HWID_DEVICES_TABLE} h2 ON h1.hwid = h2.hwid AND h2.user_uuid != h1.user_uuid
                    JOIN {USERS_TABLE} u ON h2.user_uuid = u.uuid
                    WHERE h1.user_uuid = $1
                    ORDER BY h2.hwid, u.username
                    """,
                    user_uuid,
                )

                if not rows:
                    return []

                groups: Dict[str, Dict[str, Any]] = {}
                for r in rows:
                    hwid = r["hwid"]
                    if hwid not in groups:
                        groups[hwid] = {
                            "hwid": hwid,
                            "self_telegram_id": r["self_telegram_id"],
                            "other_users": [],
                        }
                    groups[hwid]["other_users"].append({
                        "uuid": r["user_uuid"],
                        "username": r["username"],
                        "status": r["status"],
                        "telegram_id": r["telegram_id"],
                    })

                return list(groups.values())

        except Exception as e:
            logger.error("Error getting shared HWIDs for user %s: %s", user_uuid, e, exc_info=True)
            return []

    # ==================== Blocked IPs ====================

    async def get_blocked_ips(
        self, limit: int = 50, offset: int = 0, include_expired: bool = False,
    ) -> List[Dict[str, Any]]:
        """Get blocked IPs with pagination."""
        if not self.is_connected:
            return []
        try:
            where = "" if include_expired else "WHERE expires_at IS NULL OR expires_at > NOW()"
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(BLOCKED_IPS_TABLE, "*", f"{where} ORDER BY created_at DESC LIMIT $1 OFFSET $2"),
                    limit, offset,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            logger.error("Error getting blocked IPs: %s", e)
            return []

    async def get_blocked_ips_count(self, include_expired: bool = False) -> int:
        """Get count of blocked IPs."""
        if not self.is_connected:
            return 0
        try:
            where = "" if include_expired else "WHERE expires_at IS NULL OR expires_at > NOW()"
            async with self.acquire() as conn:
                return await conn.fetchval(select_sql(BLOCKED_IPS_TABLE, "COUNT(*)", where)) or 0
        except Exception as e:
            logger.error("Error getting blocked IPs count: %s", e)
            return 0

    async def add_blocked_ip(
        self,
        ip_cidr: str,
        reason: Optional[str] = None,
        admin_id: Optional[int] = None,
        admin_username: Optional[str] = None,
        country_code: Optional[str] = None,
        asn_org: Optional[str] = None,
        expires_at=None,
    ) -> Optional[Dict[str, Any]]:
        """Add IP to blocklist. Returns created entry or None on duplicate."""
        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO {BLOCKED_IPS_TABLE} (ip_cidr, reason, added_by_admin_id, added_by_username,
                                                     country_code, asn_org, expires_at)
                    VALUES ($1::cidr, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (ip_cidr) DO NOTHING
                    RETURNING *
                    """,
                    ip_cidr, reason, admin_id, admin_username,
                    country_code, asn_org, expires_at,
                )
                return dict(row) if row else None
        except Exception as e:
            logger.error("Error adding blocked IP %s: %s", ip_cidr, e)
            return None

    async def remove_blocked_ip(self, ip_id: int) -> bool:
        """Remove blocked IP by id."""
        try:
            async with self.acquire() as conn:
                result = await conn.execute(delete_sql(BLOCKED_IPS_TABLE, "id = $1"), ip_id)
                return "DELETE 1" in result
        except Exception as e:
            logger.error("Error removing blocked IP %d: %s", ip_id, e)
            return False

    async def remove_blocked_ip_by_cidr(self, ip_cidr: str) -> bool:
        """Remove blocked IP by CIDR string."""
        try:
            async with self.acquire() as conn:
                result = await conn.execute(delete_sql(BLOCKED_IPS_TABLE, "ip_cidr = $1::cidr"), ip_cidr)
                return "DELETE 1" in result
        except Exception as e:
            logger.error("Error removing blocked IP %s: %s", ip_cidr, e)
            return False

    async def get_all_active_blocked_ips(self) -> List[str]:
        """Get all active blocked IPs as CIDR strings (for agent sync)."""
        if not self.is_connected:
            return []
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(BLOCKED_IPS_TABLE, "ip_cidr::text", "WHERE expires_at IS NULL OR expires_at > NOW()")
                )
                return [r["ip_cidr"] for r in rows]
        except Exception as e:
            logger.error("Error getting active blocked IPs: %s", e)
            return []

    async def cleanup_expired_blocked_ips(self) -> int:
        """Delete expired blocked IPs. Returns count deleted."""
        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    delete_sql(BLOCKED_IPS_TABLE, "expires_at IS NOT NULL AND expires_at < NOW()")
                )
                count = int(result.split()[-1]) if result else 0
                if count > 0:
                    logger.info("Cleaned up %d expired blocked IPs", count)
                return count
        except Exception as e:
            logger.error("Error cleaning up expired blocked IPs: %s", e)
            return 0

    # ── HWID Blacklist ──────────────────────────────────────────

    async def get_hwid_blacklist(self) -> List[Dict[str, Any]]:
        """Get all blacklisted HWIDs."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(HWID_BLACKLIST_TABLE, "*", "ORDER BY created_at DESC")
            )
            return [dict(r) for r in rows]

    async def get_blacklisted_hwid(self, hwid: str) -> Optional[Dict[str, Any]]:
        """Check if a specific HWID is blacklisted. Returns the entry or None."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(HWID_BLACKLIST_TABLE, "*", "WHERE hwid = $1"), hwid
            )
            return dict(row) if row else None

    async def check_hwids_against_blacklist(self, hwids: List[str]) -> List[Dict[str, Any]]:
        """Check multiple HWIDs against blacklist. Returns matching entries."""
        if not hwids:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(HWID_BLACKLIST_TABLE, "*", "WHERE hwid = ANY($1::text[])"), hwids
            )
            return [dict(r) for r in rows]

    async def add_hwid_to_blacklist(
        self,
        hwid: str,
        action: str = "alert",
        reason: Optional[str] = None,
        admin_id: Optional[int] = None,
        admin_username: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Add HWID to blacklist. Returns created entry or None if already exists."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO {HWID_BLACKLIST_TABLE} (hwid, action, reason, added_by_admin_id, added_by_username)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (hwid) DO UPDATE SET
                    action = EXCLUDED.action,
                    reason = EXCLUDED.reason,
                    added_by_admin_id = EXCLUDED.added_by_admin_id,
                    added_by_username = EXCLUDED.added_by_username
                RETURNING *
                """,
                hwid, action, reason, admin_id, admin_username,
            )
            return dict(row) if row else None

    async def remove_hwid_from_blacklist(self, hwid: str) -> bool:
        """Remove HWID from blacklist. Returns True if deleted."""
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(HWID_BLACKLIST_TABLE, "hwid = $1"), hwid
            )
            return "DELETE 1" in result

    async def find_users_by_hwid(self, hwid: str) -> List[Dict[str, Any]]:
        """Find all users that have a specific HWID."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT h.user_uuid, u.username, u.status, h.platform, h.device_model,
                       h.created_at as hwid_first_seen, h.updated_at as hwid_last_seen
                FROM {USER_HWID_DEVICES_TABLE} h
                LEFT JOIN {USERS_TABLE} u ON u.uuid = h.user_uuid
                WHERE h.hwid = $1
                ORDER BY h.updated_at DESC
                """,
                hwid,
            )
            return [dict(r) for r in rows]

    # ── User Blacklist ─────────────────────────────────────────────

    async def get_user_blacklist(self, limit: int = 50, offset: int = 0, source: str = None):
        """Get blacklisted Telegram user IDs with pagination."""
        async with self.acquire() as conn:
            if source:
                rows = await conn.fetch(
                    select_sql(USER_BLACKLIST_TABLE, "*", "WHERE source = $1 ORDER BY created_at DESC LIMIT $2 OFFSET $3"),
                    source, limit, offset,
                )
            else:
                rows = await conn.fetch(
                    select_sql(USER_BLACKLIST_TABLE, "*", "ORDER BY created_at DESC LIMIT $1 OFFSET $2"),
                    limit, offset,
                )
            return [dict(r) for r in rows]

    async def get_user_blacklist_count(self, source: str = None) -> int:
        """Count blacklisted entries."""
        async with self.acquire() as conn:
            if source:
                return await conn.fetchval(
                    select_sql(USER_BLACKLIST_TABLE, "COUNT(*)", "WHERE source = $1"), source
                ) or 0
            return await conn.fetchval(select_sql(USER_BLACKLIST_TABLE, "COUNT(*)")) or 0

    async def is_telegram_id_blacklisted(self, telegram_id: int) -> dict | None:
        """Check if a Telegram ID is in the blacklist. Returns entry or None."""
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                select_sql(USER_BLACKLIST_TABLE, "*", "WHERE telegram_id = $1"), telegram_id
            )
            return dict(row) if row else None

    async def check_telegram_ids_blacklist(self, telegram_ids: list[int]) -> list[dict]:
        """Batch check multiple Telegram IDs against blacklist."""
        if not telegram_ids:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(USER_BLACKLIST_TABLE, "*", "WHERE telegram_id = ANY($1::bigint[])"),
                telegram_ids,
            )
            return [dict(r) for r in rows]

    async def add_to_user_blacklist(self, telegram_id: int, reason: str = None,
                                     source: str = "manual", added_by: str = None) -> bool:
        """Add a Telegram ID to the blacklist. Returns True if added, False if already exists."""
        async with self.acquire() as conn:
            try:
                await conn.execute(
                    f"""INSERT INTO {USER_BLACKLIST_TABLE} (telegram_id, reason, source, added_by_username)
                       VALUES ($1, $2, $3, $4)
                       ON CONFLICT (telegram_id) DO UPDATE SET reason = $2, source = $3""",
                    telegram_id, reason, source, added_by,
                )
                return True
            except Exception as e:
                logger.error("Failed to add telegram_id %d to blacklist: %s", telegram_id, e)
                return False

    async def bulk_add_to_user_blacklist(self, entries: list[tuple[int, str, str]]) -> int:
        """Bulk upsert entries: [(telegram_id, reason, source), ...]. Returns count."""
        if not entries:
            return 0
        async with self.acquire() as conn:
            result = await conn.executemany(
                f"""INSERT INTO {USER_BLACKLIST_TABLE} (telegram_id, reason, source)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (telegram_id) DO UPDATE SET reason = $2, source = $3""",
                entries,
            )
            return len(entries)

    async def remove_from_user_blacklist(self, telegram_id: int) -> bool:
        """Remove a Telegram ID from the blacklist."""
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(USER_BLACKLIST_TABLE, "telegram_id = $1"), telegram_id
            )
            return "DELETE 1" in result

    async def clear_user_blacklist_by_source(self, source: str) -> int:
        """Remove all entries from a specific source. Returns count deleted."""
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(USER_BLACKLIST_TABLE, "source = $1"), source
            )
            # Extract count from "DELETE N"
            try:
                return int(result.split()[-1])
            except (ValueError, IndexError):
                return 0

    async def get_user_blacklist_sources(self) -> list[dict]:
        """Get distinct sources with entry counts."""
        async with self.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USER_BLACKLIST_TABLE,
                    "source, COUNT(*) as count, MAX(created_at) as last_updated",
                    "GROUP BY source ORDER BY count DESC",
                ),
            )
            return [dict(r) for r in rows]

    # ── Node traffic snapshots ──────────────────────────────

    async def insert_node_traffic_snapshots(
        self, snapshots: List[Tuple[str, int]]
    ) -> None:
        """Bulk-insert traffic snapshots for nodes.

        Args:
            snapshots: list of (node_uuid, traffic_bytes) tuples.
        """
        if not self.is_connected or not snapshots:
            return
        async with self.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {NODE_TRAFFIC_SNAPSHOTS_TABLE} (node_uuid, traffic_bytes, created_at)
                VALUES ($1::uuid, $2, NOW())
                """,
                snapshots,
            )

    async def get_node_traffic_timeseries(
        self, since: datetime, until: datetime | None = None,
        bucket_minutes: int = 60,
    ) -> List[Dict[str, Any]]:
        """Get per-node traffic timeseries aggregated into time buckets.

        Returns list of dicts:
            {bucket: datetime, node_uuid: str, traffic_bytes: int}
        Aggregation: MAX(traffic_bytes) per bucket (snapshot values are totals,
        not deltas — so max gives the latest reading in each bucket).
        """
        if not self.is_connected:
            return []
        until = until or datetime.now(timezone.utc)
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    date_trunc('hour', created_at)
                        + INTERVAL '1 minute' * ($3 * FLOOR(
                            EXTRACT(MINUTE FROM created_at) / $3
                          )) AS bucket,
                    node_uuid::text,
                    MAX(traffic_bytes) AS traffic_bytes
                FROM {NODE_TRAFFIC_SNAPSHOTS_TABLE}
                WHERE created_at >= $1 AND created_at < $2
                GROUP BY bucket, node_uuid
                ORDER BY bucket
                """,
                since, until, bucket_minutes,
            )
            return [dict(r) for r in rows]

    async def cleanup_old_traffic_snapshots(self, keep_days: int = 31) -> int:
        """Delete traffic snapshots older than keep_days. Returns deleted count."""
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(NODE_TRAFFIC_SNAPSHOTS_TABLE, "created_at < NOW() - INTERVAL '1 day' * $1"),
                keep_days,
            )
            return int(result.split()[-1]) if result else 0

    # ── Online users snapshots (trend chart) ────────────────

    async def insert_online_users_snapshot(self, total: int) -> None:
        """Append a single cluster-wide users-online sample."""
        if not self.is_connected:
            return
        async with self.acquire() as conn:
            await conn.execute(
                insert_sql(ONLINE_USERS_SNAPSHOTS_TABLE, ["total"]),
                int(total),
            )

    async def get_online_users_trend(
        self,
        since: datetime,
        until: datetime,
        bucket_minutes: int = 60,
        aggregation: str = "avg",
    ) -> List[Dict[str, Any]]:
        """Return bucketed online-users trend points.

        Each row: {bucket: datetime, value: int}.
        ``aggregation`` is 'avg' or 'max'. Buckets without samples are omitted.
        """
        if not self.is_connected:
            return []
        agg_sql = "MAX(total)" if aggregation == "max" else "ROUND(AVG(total))::int"
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT
                    date_trunc('hour', ts)
                        + INTERVAL '1 minute' * ($3 * FLOOR(
                            EXTRACT(MINUTE FROM ts) / $3
                          )) AS bucket,
                    {agg_sql} AS value
                FROM {ONLINE_USERS_SNAPSHOTS_TABLE}
                WHERE ts >= $1 AND ts < $2
                GROUP BY bucket
                ORDER BY bucket
                """,
                since, until, bucket_minutes,
            )
            return [{"bucket": r["bucket"], "value": int(r["value"] or 0)} for r in rows]

    async def cleanup_old_online_snapshots(self, keep_days: int = 31) -> int:
        """Delete online-users snapshots older than keep_days. Returns deleted count."""
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(ONLINE_USERS_SNAPSHOTS_TABLE, "ts < NOW() - INTERVAL '1 day' * $1"),
                keep_days,
            )
            return int(result.split()[-1]) if result else 0

    async def get_nodes_traffic_for_period(
        self, start: datetime, end: datetime,
    ) -> Dict[str, int]:
        """Per-node traffic for a time period, from snapshots.

        Snapshots are cumulative per-day totals written by sync_node_traffic,
        so MAX(traffic_bytes) in the window gives the node's traffic for the day.
        Returns {node_uuid: bytes}.
        """
        if not self.is_connected:
            return {}
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT node_uuid::text AS node_uuid,
                       MAX(traffic_bytes) AS traffic_bytes
                FROM {NODE_TRAFFIC_SNAPSHOTS_TABLE}
                WHERE created_at >= $1 AND created_at < $2
                GROUP BY node_uuid
                """,
                start, end,
            )
            return {r["node_uuid"]: int(r["traffic_bytes"] or 0) for r in rows}

    async def get_top_nodes_traffic_for_period(
        self, start: datetime, end: datetime, limit: int = 3,
    ) -> List[Tuple[str, int]]:
        """Top-N nodes by traffic in a period. Returns [(node_name, bytes)]."""
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT COALESCE(n.name, s.node_uuid::text) AS name,
                       MAX(s.traffic_bytes) AS traffic_bytes
                FROM {NODE_TRAFFIC_SNAPSHOTS_TABLE} s
                LEFT JOIN {NODES_TABLE} n ON n.uuid = s.node_uuid
                WHERE s.created_at >= $1 AND s.created_at < $2
                GROUP BY s.node_uuid, n.name
                ORDER BY traffic_bytes DESC
                LIMIT $3
                """,
                start, end, limit,
            )
            return [(r["name"], int(r["traffic_bytes"] or 0)) for r in rows]

    async def count_users_created_for_period(
        self, start: datetime, end: datetime,
    ) -> int:
        """Count users created within [start, end)."""
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            val = await conn.fetchval(
                select_sql(USERS_TABLE, "COUNT(*)", "WHERE created_at >= $1 AND created_at < $2"),
                start, end,
            )
            return int(val or 0)

    async def count_users_expired_for_period(
        self, start: datetime, end: datetime,
    ) -> int:
        """Count users whose subscription expired within [start, end)."""
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            val = await conn.fetchval(
                select_sql(USERS_TABLE, "COUNT(*)", "WHERE expire_at >= $1 AND expire_at < $2"),
                start, end,
            )
            return int(val or 0)

    # ── Access policies (scoping admin rights to specific resources) ──────

    async def list_access_policies(self) -> List[Dict[str, Any]]:
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT p.id, p.name, p.description, p.created_by, p.created_at, p.updated_at,
                       COALESCE(rc.cnt, 0) AS rules_count,
                       COALESCE(rl.cnt, 0) AS roles_count,
                       COALESCE(ad.cnt, 0) AS admins_count
                FROM {ACCESS_POLICIES_TABLE} p
                LEFT JOIN (SELECT policy_id, COUNT(*) cnt FROM {ACCESS_POLICY_RULES_TABLE} GROUP BY policy_id) rc
                       ON rc.policy_id = p.id
                LEFT JOIN (SELECT policy_id, COUNT(*) cnt FROM {ROLE_ACCESS_POLICIES_TABLE} GROUP BY policy_id) rl
                       ON rl.policy_id = p.id
                LEFT JOIN (SELECT policy_id, COUNT(*) cnt FROM {ADMIN_ACCESS_POLICIES_TABLE} GROUP BY policy_id) ad
                       ON ad.policy_id = p.id
                ORDER BY p.name
                """
            )
            return [dict(r) for r in rows]

    async def get_access_policy(self, policy_id: int) -> Optional[Dict[str, Any]]:
        if not self.is_connected:
            return None
        async with self.acquire() as conn:
            policy = await conn.fetchrow(
                select_sql(ACCESS_POLICIES_TABLE, "*", "WHERE id = $1"), policy_id,
            )
            if not policy:
                return None
            rules = await conn.fetch(
                select_sql(
                    ACCESS_POLICY_RULES_TABLE,
                    "id, resource_type, scope_type, scope_value, actions",
                    "WHERE policy_id = $1 ORDER BY id",
                ),
                policy_id,
            )
            roles = await conn.fetch(
                select_sql(ROLE_ACCESS_POLICIES_TABLE, "role_id", "WHERE policy_id = $1"), policy_id,
            )
            admins = await conn.fetch(
                select_sql(
                    ADMIN_ACCESS_POLICIES_TABLE,
                    "admin_id",
                    "WHERE policy_id = $1",
                ),
                policy_id,
            )
            return {
                **dict(policy),
                "rules": [dict(r) for r in rules],
                "role_ids": [r["role_id"] for r in roles],
                "admin_ids": [r["admin_id"] for r in admins],
            }

    async def create_access_policy(
        self, name: str, description: Optional[str],
        created_by: Optional[int], rules: List[Dict[str, Any]],
    ) -> int:
        async with self.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    f"""
                    INSERT INTO {ACCESS_POLICIES_TABLE} (name, description, created_by)
                    VALUES ($1, $2, $3) RETURNING id
                    """,
                    name, description, created_by,
                )
                policy_id = int(row["id"])
                for rule in rules:
                    await conn.execute(
                        f"""
                        INSERT INTO {ACCESS_POLICY_RULES_TABLE}
                            (policy_id, resource_type, scope_type, scope_value, actions)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        policy_id,
                        rule["resource_type"], rule["scope_type"],
                        rule["scope_value"], rule["actions"],
                    )
                return policy_id

    async def update_access_policy(
        self, policy_id: int, name: Optional[str] = None,
        description: Optional[str] = None,
        rules: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        async with self.acquire() as conn:
            async with conn.transaction():
                if name is not None or description is not None:
                    await conn.execute(
                        update_sql(
                            ACCESS_POLICIES_TABLE,
                            "name = COALESCE($2, name), description = COALESCE($3, description), updated_at = NOW()",
                            "id = $1",
                        ),
                        policy_id, name, description,
                    )
                if rules is not None:
                    await conn.execute(
                        delete_sql(ACCESS_POLICY_RULES_TABLE, "policy_id = $1"), policy_id,
                    )
                    for rule in rules:
                        await conn.execute(
                            f"""
                            INSERT INTO {ACCESS_POLICY_RULES_TABLE}
                                (policy_id, resource_type, scope_type, scope_value, actions)
                            VALUES ($1, $2, $3, $4, $5)
                            """,
                            policy_id,
                            rule["resource_type"], rule["scope_type"],
                            rule["scope_value"], rule["actions"],
                        )
                return True

    async def delete_access_policy(self, policy_id: int) -> bool:
        async with self.acquire() as conn:
            result = await conn.execute(
                delete_sql(ACCESS_POLICIES_TABLE, "id = $1"), policy_id,
            )
            return "DELETE 1" in (result or "")

    async def set_role_policies(self, role_id: int, policy_ids: List[int]) -> None:
        async with self.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    delete_sql(ROLE_ACCESS_POLICIES_TABLE, "role_id = $1"), role_id,
                )
                for pid in policy_ids:
                    await conn.execute(
                        f"""
                        INSERT INTO {ROLE_ACCESS_POLICIES_TABLE} (role_id, policy_id)
                        VALUES ($1, $2) ON CONFLICT DO NOTHING
                        """,
                        role_id, pid,
                    )

    async def set_admin_policies(self, admin_id: int, policy_ids: List[int]) -> None:
        async with self.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    delete_sql(
                        ADMIN_ACCESS_POLICIES_TABLE,
                        "admin_id = $1",
                    ),
                    admin_id,
                )
                for pid in policy_ids:
                    await conn.execute(
                        insert_sql(
                            ADMIN_ACCESS_POLICIES_TABLE,
                            ["admin_id", "policy_id"],
                            suffix="ON CONFLICT DO NOTHING",
                        ),
                        admin_id, pid,
                    )

    async def get_effective_policy_rules(
        self, admin_id: Optional[int], role_id: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Return all policy rules that apply to the given admin/role.

        Union of rules from: policies attached to the role + policies
        attached directly to the admin. Empty result = no policies => full access.
        """
        if not self.is_connected or (admin_id is None and role_id is None):
            return []
        async with self.acquire() as conn:
            rows = await conn.fetch(
                f"""
                WITH effective AS (
                    SELECT policy_id FROM {ROLE_ACCESS_POLICIES_TABLE} WHERE role_id = $1
                    UNION
                    SELECT policy_id FROM {ADMIN_ACCESS_POLICIES_TABLE} WHERE admin_id = $2
                )
                SELECT r.resource_type, r.scope_type, r.scope_value, r.actions
                FROM {ACCESS_POLICY_RULES_TABLE} r
                JOIN effective e ON e.policy_id = r.policy_id
                """,
                role_id, admin_id,
            )
            return [dict(r) for r in rows]

    async def get_user_uuids_by_nodes(self, node_uuids: List[str]) -> Set[str]:
        """User UUIDs that have any activity on the given nodes.

        Uses user_node_traffic table — users who ever accumulated traffic
        on one of the nodes. Returns lowercase str UUIDs.
        """
        if not self.is_connected or not node_uuids:
            return set()
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(
                        USER_NODE_TRAFFIC_TABLE,
                        "DISTINCT user_uuid::text AS uuid",
                        "WHERE node_uuid = ANY($1::uuid[])",
                    ),
                    node_uuids,
                )
                return {r["uuid"].lower() for r in rows if r["uuid"]}
        except Exception as e:
            logger.debug("get_user_uuids_by_nodes failed: %s", e)
            return set()

    async def get_user_uuids_by_squads(self, squad_uuids: List[str]) -> Set[str]:
        """User UUIDs that belong to any of the given internal squads.

        Parses users.raw_data -> activeInternalSquads (list of uuid strings
        or dicts with uuid field). Case-insensitive comparison.
        """
        if not self.is_connected or not squad_uuids:
            return set()
        squad_lower = {s.lower() for s in squad_uuids}
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    select_sql(USERS_TABLE, "uuid::text AS uuid, raw_data", "WHERE raw_data IS NOT NULL")
                )
        except Exception as e:
            logger.debug("get_user_uuids_by_squads fetch failed: %s", e)
            return set()
        result: Set[str] = set()
        for r in rows:
            raw = r["raw_data"]
            if isinstance(raw, str):
                try:
                    import json as _json
                    raw = _json.loads(raw)
                except (ValueError, TypeError):
                    continue
            if not isinstance(raw, dict):
                continue
            sqs = raw.get("activeInternalSquads") or []
            if not isinstance(sqs, list):
                continue
            for sq in sqs:
                sq_uuid = None
                if isinstance(sq, str):
                    sq_uuid = sq
                elif isinstance(sq, dict):
                    sq_uuid = sq.get("uuid") or sq.get("squadUuid")
                if sq_uuid and str(sq_uuid).lower() in squad_lower:
                    result.add(str(r["uuid"]).lower())
                    break
        return result

    async def get_uuids_by_tag(self, resource_type: str, tag: str) -> List[str]:
        """Return UUIDs of nodes/hosts of a given type whose tags include the tag.

        Tags are stored in raw_data JSON (Panel API payload). We cast to jsonb
        for the containment check. Squads have no tags yet -> empty result.
        """
        if not self.is_connected:
            return []
        if resource_type == "node":
            table = NODES_TABLE
        elif resource_type == "host":
            table = HOSTS_TABLE
        else:
            return []
        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT uuid::text AS uuid
                    FROM {table}
                    WHERE (raw_data::jsonb)->'tags' ? $1
                    """,
                    tag,
                )
                return [r["uuid"] for r in rows]
        except Exception as e:
            logger.debug("get_uuids_by_tag failed: %s", e)
            return []

    # ── User-node traffic history (deltas) ─────────────────

    async def insert_user_node_traffic_deltas(
        self, deltas: List[Tuple[str, str, int]]
    ) -> None:
        """Bulk-insert per-user-per-node traffic deltas.

        Args:
            deltas: list of (user_uuid, node_uuid, delta_bytes) tuples.
        """
        if not self.is_connected or not deltas:
            return
        async with self.acquire() as conn:
            await conn.executemany(
                f"""
                INSERT INTO {USER_NODE_TRAFFIC_HISTORY_TABLE}
                    (user_uuid, node_uuid, delta_bytes, recorded_at)
                VALUES ($1::uuid, $2::uuid, $3, NOW())
                """,
                deltas,
            )

    async def get_user_node_traffic_today(
        self, node_uuid: str | None = None, threshold_bytes: int = 0
    ) -> List[Dict[str, Any]]:
        """Sum per-user traffic deltas since start of today (UTC).

        Args:
            node_uuid: optional filter by specific node.
            threshold_bytes: only return users above this threshold.

        Returns list of dicts with user_uuid, username, node_name, traffic_bytes.
        """
        if not self.is_connected:
            return []
        async with self.acquire() as conn:
            if node_uuid:
                rows = await conn.fetch(
                    f"""
                    SELECT h.user_uuid, u.username,
                           n.name AS node_name,
                           SUM(h.delta_bytes) AS traffic_bytes
                    FROM {USER_NODE_TRAFFIC_HISTORY_TABLE} h
                    JOIN {USERS_TABLE} u ON u.uuid = h.user_uuid
                    JOIN {NODES_TABLE} n ON n.uuid = h.node_uuid
                    WHERE h.recorded_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
                      AND h.node_uuid = $1::uuid
                      AND u.status NOT IN ('EXPIRED', 'DISABLED', 'LIMITED')
                    GROUP BY h.user_uuid, u.username, n.name
                    HAVING SUM(h.delta_bytes) >= $2
                    ORDER BY traffic_bytes DESC
                    """,
                    node_uuid, threshold_bytes,
                )
            else:
                rows = await conn.fetch(
                    f"""
                    SELECT h.user_uuid, u.username,
                           n.name AS node_name, h.node_uuid,
                           SUM(h.delta_bytes) AS traffic_bytes
                    FROM {USER_NODE_TRAFFIC_HISTORY_TABLE} h
                    JOIN {USERS_TABLE} u ON u.uuid = h.user_uuid
                    JOIN {NODES_TABLE} n ON n.uuid = h.node_uuid
                    WHERE h.recorded_at >= date_trunc('day', NOW() AT TIME ZONE 'UTC')
                      AND u.status NOT IN ('EXPIRED', 'DISABLED', 'LIMITED')
                    GROUP BY h.user_uuid, u.username, h.node_uuid, n.name
                    HAVING SUM(h.delta_bytes) >= $1
                    ORDER BY traffic_bytes DESC
                    """,
                    threshold_bytes,
                )
            return [dict(r) for r in rows]

    async def cleanup_old_user_node_traffic_history(self, keep_hours: int = 48) -> int:
        """Delete user-node traffic history older than keep_hours."""
        if not self.is_connected:
            return 0
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM user_node_traffic_history WHERE recorded_at < NOW() - INTERVAL '1 hour' * $1",
                keep_hours,
            )
            return int(result.split()[-1]) if result else 0

