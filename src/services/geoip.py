"""
GeoIP сервис для получения геолокации IP адресов.

Провайдеры (по приоритету):
1. MaxMind GeoLite2 — локальная .mmdb база (мгновенно, без лимитов).
   Настройка: MAXMIND_CITY_DB=/path/to/GeoLite2-City.mmdb
              MAXMIND_ASN_DB=/path/to/GeoLite2-ASN.mmdb  (опционально)
2. ip-api.com — бесплатный HTTP API (fallback, ~45 req/min).
"""
import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime, timedelta

import httpx
from src.config import get_settings
from src.services.database import DatabaseService, db_service as global_db_service
from src.utils.logger import logger

# Optional MaxMind imports
try:
    import geoip2.database
    import geoip2.errors
    HAS_GEOIP2 = True
except ImportError:
    HAS_GEOIP2 = False


@dataclass
class IPMetadata:
    """Метаданные IP адреса."""
    ip: str
    country_code: Optional[str] = None
    country_name: Optional[str] = None
    region: Optional[str] = None
    city: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timezone: Optional[str] = None
    asn: Optional[int] = None
    asn_org: Optional[str] = None
    connection_type: Optional[str] = None  # 'residential', 'mobile', 'datacenter', 'hosting'
    is_proxy: bool = False
    is_vpn: bool = False
    is_tor: bool = False
    is_hosting: bool = False
    is_mobile: bool = False


class GeoIPService:
    """
    Сервис для получения геолокации IP адресов.

    Поддерживает два провайдера:
    - MaxMind GeoLite2 (локальный .mmdb) — приоритетный, без лимитов
    - ip-api.com (HTTP API) — fallback, ~45 req/min
    """

    # ── ip-api.com конфигурация ──────────────────────────────────
    API_URL = "http://ip-api.com/json/{ip}"
    FIELDS = "status,message,country,countryCode,region,regionName,city,lat,lon,timezone,as,asname,isp,org,mobile,proxy,hosting,query"

    # Классификация ASN организаций
    MOBILE_CARRIERS = {
        'mts', 'beeline', 'megafon', 'tele2', 'yota', 'rostelecom mobile',
        'vodafone', 'orange', 't-mobile', 'verizon', 'at&t', 'sprint',
        'ee', 'three', 'o2', 'china mobile', 'china unicom', 'china telecom'
    }

    DATACENTER_KEYWORDS = {
        'digitalocean', 'aws', 'amazon', 'hetzner', 'ovh', 'linode', 'vultr',
        'google cloud', 'azure', 'microsoft', 'rackspace', 'ibm cloud',
        'oracle cloud', 'alibaba cloud', 'tencent cloud', 'huawei cloud'
    }

    VPN_KEYWORDS = {
        'nordvpn', 'expressvpn', 'surfshark', 'cyberghost', 'pia', 'private internet access',
        'mullvad', 'protonvpn', 'windscribe', 'tunnelbear', 'vyprvpn', 'hotspot shield',
        'hide.me', 'vpn', 'proxy', 'anonymizer'
    }

    def __init__(self, db_service: Optional[DatabaseService] = None):
        """
        Инициализирует GeoIP сервис.

        Args:
            db_service: Сервис для работы с БД (по умолчанию используется глобальный)
        """
        self.settings = get_settings()
        self.db = db_service or global_db_service
        self._cache: Dict[str, tuple[IPMetadata, datetime]] = {}
        self._cache_ttl = timedelta(hours=24)  # Кэш в памяти на 24 часа
        self._db_cache_ttl_days = 30  # Кэш в БД на 30 дней
        self._rate_limit_delay = 1.5  # Задержка между запросами (45 запросов/мин = ~1.3 сек/запрос)
        self._last_request_time: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None

        # MaxMind readers
        self._maxmind_city = None
        self._maxmind_asn = None
        self._init_maxmind()

    # ── MaxMind ──────────────────────────────────────────────────

    def _init_maxmind(self):
        """Инициализация MaxMind GeoLite2 баз (если настроены)."""
        if not HAS_GEOIP2:
            return

        city_path = self.settings.maxmind_city_db
        asn_path = self.settings.maxmind_asn_db

        if city_path and Path(city_path).is_file():
            try:
                self._maxmind_city = geoip2.database.Reader(city_path)
                logger.info("MaxMind City DB loaded: %s", city_path)
            except Exception as e:
                logger.warning("Failed to open MaxMind City DB %s: %s", city_path, e)

        if asn_path and Path(asn_path).is_file():
            try:
                self._maxmind_asn = geoip2.database.Reader(asn_path)
                logger.info("MaxMind ASN DB loaded: %s", asn_path)
            except Exception as e:
                logger.warning("Failed to open MaxMind ASN DB %s: %s", asn_path, e)

        if self._maxmind_city:
            logger.info("GeoIP provider: MaxMind GeoLite2 (local, no rate limits)")
        else:
            logger.info("GeoIP provider: ip-api.com (HTTP API, rate-limited)")

    @property
    def has_maxmind(self) -> bool:
        """Доступна ли локальная MaxMind база."""
        return self._maxmind_city is not None

    def _lookup_maxmind(self, ip_address: str) -> Optional[IPMetadata]:
        """
        Синхронный lookup через MaxMind GeoLite2 .mmdb файлы.

        Returns:
            IPMetadata или None если IP не найден в базе
        """
        if not self._maxmind_city:
            return None

        try:
            city_resp = self._maxmind_city.city(ip_address)
        except geoip2.errors.AddressNotFoundError:
            return None
        except Exception as e:
            logger.debug("MaxMind city lookup error for %s: %s", ip_address, e)
            return None

        country_code = city_resp.country.iso_code
        country_name = city_resp.country.name
        region = None
        if city_resp.subdivisions and city_resp.subdivisions.most_specific:
            region = city_resp.subdivisions.most_specific.name
        city_name = city_resp.city.name if city_resp.city else None
        latitude = city_resp.location.latitude if city_resp.location else None
        longitude = city_resp.location.longitude if city_resp.location else None
        timezone = city_resp.location.time_zone if city_resp.location else None

        # ASN data (отдельная база)
        asn = None
        asn_org = None
        if self._maxmind_asn:
            try:
                asn_resp = self._maxmind_asn.asn(ip_address)
                asn = asn_resp.autonomous_system_number
                asn_org = asn_resp.autonomous_system_organization
            except Exception:
                pass

        # Базовая классификация по ASN (без флагов proxy/hosting — MaxMind City не даёт)
        connection_type = 'residential'
        is_mobile_flag = False
        is_hosting_flag = False
        is_vpn_flag = False

        if asn_org:
            asn_lower = asn_org.lower()
            if any(kw in asn_lower for kw in self.VPN_KEYWORDS):
                connection_type = 'vpn'
                is_vpn_flag = True
            elif any(kw in asn_lower for kw in self.MOBILE_CARRIERS):
                connection_type = 'mobile'
                is_mobile_flag = True
            elif any(kw in asn_lower for kw in self.DATACENTER_KEYWORDS):
                connection_type = 'datacenter'
                is_hosting_flag = True

        return IPMetadata(
            ip=ip_address,
            country_code=country_code,
            country_name=country_name,
            region=region,
            city=city_name,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            asn=asn,
            asn_org=asn_org,
            connection_type=connection_type,
            is_proxy=False,
            is_vpn=is_vpn_flag,
            is_tor=False,
            is_hosting=is_hosting_flag,
            is_mobile=is_mobile_flag,
        )

    # ── ip-api.com (HTTP) ────────────────────────────────────────

    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент."""
        if self._client is None:
            timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=10.0)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client

    async def _rate_limit(self):
        """Ограничение скорости запросов."""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            if elapsed < self._rate_limit_delay:
                await asyncio.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = datetime.utcnow()

    async def _lookup_ipapi(self, ip_address: str) -> Optional[IPMetadata]:
        """Lookup через ip-api.com HTTP API."""
        try:
            await self._rate_limit()

            client = await self._get_client()
            url = self.API_URL.format(ip=ip_address)

            response = await client.get(url, params={'fields': self.FIELDS})
            response.raise_for_status()

            data = response.json()

            if data.get('status') != 'success':
                error_message = data.get('message', 'Unknown error')
                logger.warning("GeoIP lookup failed for %s: %s", ip_address, error_message)
                return None

            # Извлекаем ASN из поля 'as' (формат: "AS12345 Organization Name")
            asn = None
            asn_raw = data.get('as', '')
            if asn_raw:
                asn_parts = asn_raw.split()
                for part in asn_parts:
                    if part.startswith('AS') and part[2:].isdigit():
                        try:
                            asn = int(part[2:])
                            break
                        except ValueError:
                            pass

            asn_org = data.get('asname', '') or data.get('org', '') or data.get('isp', '')
            is_mobile = data.get('mobile', False)
            is_hosting = data.get('hosting', False)
            is_proxy = data.get('proxy', False)
            country_code = data.get('countryCode')

            connection_type, is_mobile_carrier, is_datacenter, is_vpn, asn_region, asn_city = await self._classify_asn(
                asn, asn_org, is_mobile, is_hosting, country_code
            )

            final_region = asn_region or data.get('regionName')
            final_city = asn_city or data.get('city')

            return IPMetadata(
                ip=ip_address,
                country_code=country_code,
                country_name=data.get('country'),
                region=final_region,
                city=final_city,
                latitude=data.get('lat'),
                longitude=data.get('lon'),
                timezone=data.get('timezone'),
                asn=asn,
                asn_org=asn_org,
                connection_type=connection_type,
                is_proxy=is_proxy,
                is_vpn=is_vpn,
                is_tor=False,
                is_hosting=is_hosting,
                is_mobile=is_mobile_carrier
            )

        except httpx.HTTPError as e:
            logger.error("HTTP error during GeoIP lookup for %s: %s", ip_address, e)
            return None
        except Exception as e:
            logger.error("Error during GeoIP lookup for %s: %s", ip_address, e, exc_info=True)
            return None

    # ── ASN classification ───────────────────────────────────────

    async def _classify_asn(self, asn: Optional[int], asn_org: Optional[str], is_mobile: bool, is_hosting: bool, country_code: Optional[str] = None) -> tuple[str, bool, bool, bool, Optional[str], Optional[str]]:
        """
        Классифицирует тип провайдера на основе ASN организации.

        Использует локальную базу ASN по РФ для более точного определения.

        Returns:
            (connection_type, is_mobile_carrier, is_datacenter, is_vpn, region, city)
        """
        region = None
        city = None

        # Если есть ASN и это Россия - проверяем локальную базу
        if asn and country_code == 'RU' and self.db and self.db.is_connected:
            try:
                asn_record = await self.db.get_asn_record(asn)
                if asn_record:
                    provider_type = asn_record.get('provider_type')
                    if provider_type:
                        is_mobile_carrier = provider_type in ('mobile', 'mobile_isp')
                        is_datacenter = provider_type in ('hosting', 'datacenter')
                        is_vpn = provider_type == 'vpn'
                        connection_type = provider_type
                        region = asn_record.get('region')
                        city = asn_record.get('city')

                        logger.debug("Using ASN database for AS%d: type=%s, region=%s, city=%s",
                                   asn, provider_type, region, city)

                        return (connection_type, is_mobile_carrier, is_datacenter, is_vpn, region, city)
            except Exception as e:
                logger.debug("Error checking ASN database for AS%d: %s", asn, e)

        # Fallback: эвристика по названию организации
        if not asn_org:
            return ('unknown', False, False, False, None, None)

        asn_lower = asn_org.lower()

        is_vpn = any(keyword in asn_lower for keyword in self.VPN_KEYWORDS)
        if is_vpn:
            return ('vpn', False, False, True, None, None)

        is_mobile_carrier = is_mobile or any(carrier in asn_lower for carrier in self.MOBILE_CARRIERS)
        if is_mobile_carrier:
            return ('mobile', True, False, False, None, None)

        is_datacenter = is_hosting or any(keyword in asn_lower for keyword in self.DATACENTER_KEYWORDS)
        if is_datacenter:
            return ('datacenter', False, True, False, None, None)

        return ('residential', False, False, False, None, None)

    # ── DB helpers ───────────────────────────────────────────────

    def _metadata_from_db(self, db_row: Dict) -> IPMetadata:
        """Конвертировать строку из БД в IPMetadata."""
        return IPMetadata(
            ip=db_row['ip_address'],
            country_code=db_row.get('country_code'),
            country_name=db_row.get('country_name'),
            region=db_row.get('region'),
            city=db_row.get('city'),
            latitude=float(db_row['latitude']) if db_row.get('latitude') is not None else None,
            longitude=float(db_row['longitude']) if db_row.get('longitude') is not None else None,
            timezone=db_row.get('timezone'),
            asn=db_row.get('asn'),
            asn_org=db_row.get('asn_org'),
            connection_type=db_row.get('connection_type'),
            is_proxy=db_row.get('is_proxy', False),
            is_vpn=db_row.get('is_vpn', False),
            is_tor=db_row.get('is_tor', False),
            is_hosting=db_row.get('is_hosting', False),
            is_mobile=db_row.get('is_mobile', False)
        )

    async def _save_metadata_to_db(self, metadata: IPMetadata) -> bool:
        """Сохранить метаданные в БД."""
        if not self.db or not self.db.is_connected:
            return False

        try:
            return await self.db.save_ip_metadata(
                ip_address=metadata.ip,
                country_code=metadata.country_code,
                country_name=metadata.country_name,
                region=metadata.region,
                city=metadata.city,
                latitude=metadata.latitude,
                longitude=metadata.longitude,
                timezone=metadata.timezone,
                asn=metadata.asn,
                asn_org=metadata.asn_org,
                connection_type=metadata.connection_type,
                is_proxy=metadata.is_proxy,
                is_vpn=metadata.is_vpn,
                is_tor=metadata.is_tor,
                is_hosting=metadata.is_hosting,
                is_mobile=metadata.is_mobile
            )
        except Exception as e:
            logger.error("Error saving IP metadata to DB for %s: %s", metadata.ip, e, exc_info=True)
            return False

    # ── Public API ───────────────────────────────────────────────

    async def lookup(self, ip_address: str, use_cache: bool = True) -> Optional[IPMetadata]:
        """
        Получить метаданные IP адреса.

        Порядок:
        1. In-Memory кэш (24 часа)
        2. БД кэш (30 дней)
        3. MaxMind GeoLite2 (если доступен)
        4. ip-api.com HTTP API (fallback)

        Args:
            ip_address: IP адрес для поиска
            use_cache: Использовать кэш если доступен

        Returns:
            IPMetadata или None при ошибке
        """
        # Пропускаем приватные IP
        if ip_address.startswith(('127.', '192.168.', '10.', '172.16.')):
            return IPMetadata(ip=ip_address, country_code='PRIVATE', country_name='Private Network')

        # Уровень 1: in-memory кэш
        if use_cache and ip_address in self._cache:
            metadata, cached_at = self._cache[ip_address]
            if datetime.utcnow() - cached_at < self._cache_ttl:
                logger.debug("GeoIP in-memory cache hit for %s", ip_address)
                return metadata

        # Уровень 2: БД кэш
        if use_cache and self.db and self.db.is_connected:
            should_refresh = await self.db.should_refresh_ip_metadata(
                ip_address, max_age_days=self._db_cache_ttl_days
            )

            if not should_refresh:
                db_row = await self.db.get_ip_metadata(ip_address)
                if db_row:
                    metadata = self._metadata_from_db(db_row)
                    self._cache[ip_address] = (metadata, datetime.utcnow())
                    logger.debug("GeoIP DB cache hit for %s", ip_address)
                    return metadata

        # Уровень 3: MaxMind (мгновенный, без лимитов)
        if self.has_maxmind:
            metadata = self._lookup_maxmind(ip_address)
            if metadata:
                # Обогащаем данными из локальной базы ASN для РФ
                if metadata.asn and metadata.country_code == 'RU':
                    ct, is_mob, is_dc, is_v, asn_r, asn_c = await self._classify_asn(
                        metadata.asn, metadata.asn_org, metadata.is_mobile, metadata.is_hosting, metadata.country_code
                    )
                    metadata.connection_type = ct
                    metadata.is_mobile = is_mob
                    metadata.is_hosting = is_dc
                    metadata.is_vpn = is_v
                    if asn_r:
                        metadata.region = asn_r
                    if asn_c:
                        metadata.city = asn_c

                self._cache[ip_address] = (metadata, datetime.utcnow())
                await self._save_metadata_to_db(metadata)
                logger.debug("GeoIP MaxMind lookup for %s: %s, %s", ip_address, metadata.country_code, metadata.city)
                return metadata

        # Уровень 4: ip-api.com (с rate limiting)
        metadata = await self._lookup_ipapi(ip_address)
        if metadata:
            self._cache[ip_address] = (metadata, datetime.utcnow())
            await self._save_metadata_to_db(metadata)
            logger.debug("GeoIP API lookup for %s: %s, %s", ip_address, metadata.country_code, metadata.city)

        return metadata

    async def lookup_batch(self, ip_addresses: list[str]) -> Dict[str, IPMetadata]:
        """
        Получить метаданные для нескольких IP адресов.

        Args:
            ip_addresses: Список IP адресов

        Returns:
            Словарь {ip: IPMetadata}
        """
        results = {}
        ips_to_check_db = []
        ips_to_fetch_api = []

        now = datetime.utcnow()

        # Уровень 1: in-memory кэш
        for ip in ip_addresses:
            if ip.startswith(('127.', '192.168.', '10.', '172.16.')):
                results[ip] = IPMetadata(ip=ip, country_code='PRIVATE', country_name='Private Network')
                continue

            if ip in self._cache:
                metadata, cached_at = self._cache[ip]
                if now - cached_at < self._cache_ttl:
                    results[ip] = metadata
                    continue

            ips_to_check_db.append(ip)

        # Уровень 2: БД batch запрос
        db_hits = 0
        if ips_to_check_db and self.db and self.db.is_connected:
            db_results = await self.db.get_ip_metadata_batch(ips_to_check_db)

            for ip in ips_to_check_db:
                db_row = db_results.get(ip)

                if db_row:
                    should_refresh = await self.db.should_refresh_ip_metadata(
                        ip, max_age_days=self._db_cache_ttl_days
                    )

                    if not should_refresh:
                        metadata = self._metadata_from_db(db_row)
                        results[ip] = metadata
                        self._cache[ip] = (metadata, datetime.utcnow())
                        db_hits += 1
                        continue

                ips_to_fetch_api.append(ip)
        else:
            ips_to_fetch_api = ips_to_check_db

        # Уровень 3 + 4: MaxMind / ip-api.com
        if ips_to_fetch_api:
            in_memory_hits = len(results) - db_hits
            provider = "MaxMind" if self.has_maxmind else "ip-api.com"
            logger.info(
                "GeoIP batch: %d cached (mem: %d, DB: %d), %d to fetch via %s",
                len(results), in_memory_hits, db_hits, len(ips_to_fetch_api), provider,
            )

            for ip in ips_to_fetch_api:
                metadata = await self.lookup(ip, use_cache=False)
                if metadata:
                    results[ip] = metadata

        return results

    async def close(self):
        """Закрыть все ресурсы."""
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._maxmind_city:
            self._maxmind_city.close()
            self._maxmind_city = None
        if self._maxmind_asn:
            self._maxmind_asn.close()
            self._maxmind_asn = None

    def clear_cache(self):
        """Очистить кэш."""
        self._cache.clear()


# Глобальный экземпляр сервиса
_geoip_service: Optional[GeoIPService] = None


def get_geoip_service(db_service: Optional[DatabaseService] = None) -> GeoIPService:
    """
    Получить глобальный экземпляр GeoIP сервиса.

    Args:
        db_service: Опциональный DB сервис (по умолчанию используется глобальный)
    """
    global _geoip_service
    if _geoip_service is None:
        _geoip_service = GeoIPService(db_service=db_service)
    return _geoip_service
