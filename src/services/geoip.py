"""
GeoIP сервис для получения геолокации IP адресов.

Использует ip-api.com (бесплатный, без API ключа) для получения:
- Страны, города, региона
- Координат (широта/долгота)
- ASN и организации провайдера
- Типа подключения (мобильный/домашний/датацентр)
- Флагов VPN/Proxy/Tor
"""
import asyncio
from dataclasses import dataclass
from typing import Dict, Optional, Set
from datetime import datetime, timedelta

import httpx
from src.config import get_settings
from src.services.database import DatabaseService, db_service as global_db_service
from src.utils.logger import logger


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
    Сервис для получения геолокации IP адресов через ip-api.com.
    
    ip-api.com предоставляет бесплатный API:
    - До 45 запросов в минуту без регистрации
    - До 1000 запросов в день без регистрации
    - С регистрацией: до 15 запросов в минуту, 45k в месяц
    
    Формат запроса: http://ip-api.com/json/{ip}?fields=status,message,country,countryCode,region,regionName,city,lat,lon,timezone,as,asname,isp,org,mobile,proxy,hosting,query
    """
    
    # URL для запросов
    API_URL = "http://ip-api.com/json/{ip}"
    
    # Поля для запроса
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
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент."""
        if self._client is None:
            timeout = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=10.0)
            self._client = httpx.AsyncClient(timeout=timeout)
        return self._client
    
    async def close(self):
        """Закрыть HTTP клиент."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def _rate_limit(self):
        """Ограничение скорости запросов."""
        if self._last_request_time:
            elapsed = (datetime.utcnow() - self._last_request_time).total_seconds()
            if elapsed < self._rate_limit_delay:
                await asyncio.sleep(self._rate_limit_delay - elapsed)
        self._last_request_time = datetime.utcnow()
    
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
                    # Используем данные из локальной базы
                    provider_type = asn_record.get('provider_type')
                    if provider_type:
                        is_mobile_carrier = provider_type == 'mobile'
                        is_datacenter = provider_type == 'datacenter'
                        is_vpn = provider_type == 'vpn'
                        
                        # Определяем connection_type
                        if provider_type == 'mobile':
                            connection_type = 'mobile'
                        elif provider_type == 'datacenter':
                            connection_type = 'datacenter'
                        elif provider_type == 'vpn':
                            connection_type = 'vpn'
                        elif provider_type == 'isp':
                            connection_type = 'residential'
                        else:
                            connection_type = provider_type or 'residential'
                        
                        # Извлекаем регион и город из базы ASN
                        region = asn_record.get('region')
                        city = asn_record.get('city')
                        
                        logger.debug("Using ASN database for AS%d: type=%s, region=%s, city=%s", 
                                   asn, provider_type, region, city)
                        
                        return (connection_type, is_mobile_carrier, is_datacenter, is_vpn, region, city)
            except Exception as e:
                logger.debug("Error checking ASN database for AS%d: %s", asn, e)
        
        # Fallback: используем эвристику на основе названия организации
        if not asn_org:
            return ('unknown', False, False, False, None, None)
        
        asn_lower = asn_org.lower()
        
        # Проверка на VPN
        is_vpn = any(keyword in asn_lower for keyword in self.VPN_KEYWORDS)
        if is_vpn:
            return ('vpn', False, False, True, None, None)
        
        # Проверка на мобильный оператор
        is_mobile_carrier = is_mobile or any(carrier in asn_lower for carrier in self.MOBILE_CARRIERS)
        if is_mobile_carrier:
            return ('mobile', True, False, False, None, None)
        
        # Проверка на датацентр/хостинг
        is_datacenter = is_hosting or any(keyword in asn_lower for keyword in self.DATACENTER_KEYWORDS)
        if is_datacenter:
            return ('datacenter', False, True, False, None, None)
        
        # По умолчанию - домашний провайдер
        return ('residential', False, False, False, None, None)
    
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
    
    async def lookup(self, ip_address: str, use_cache: bool = True) -> Optional[IPMetadata]:
        """
        Получить метаданные IP адреса.
        
        Использует трёхуровневое кэширование:
        1. БД (30 дней) - персистентное хранилище
        2. In-Memory (24 часа) - быстрый доступ
        3. Внешний API - только если данных нет
        
        Args:
            ip_address: IP адрес для поиска
            use_cache: Использовать кэш если доступен
        
        Returns:
            IPMetadata или None при ошибке
        """
        # Пропускаем приватные IP
        if ip_address.startswith(('127.', '192.168.', '10.', '172.16.')):
            return IPMetadata(ip=ip_address, country_code='PRIVATE', country_name='Private Network')
        
        # Уровень 1: Проверяем in-memory кэш
        if use_cache and ip_address in self._cache:
            metadata, cached_at = self._cache[ip_address]
            if datetime.utcnow() - cached_at < self._cache_ttl:
                logger.debug("GeoIP in-memory cache hit for %s", ip_address)
                return metadata
        
        # Уровень 2: Проверяем БД (если данные свежие)
        if use_cache and self.db and self.db.is_connected:
            # Проверяем, нужно ли обновлять данные из БД
            should_refresh = await self.db.should_refresh_ip_metadata(
                ip_address, max_age_days=self._db_cache_ttl_days
            )
            
            if not should_refresh:
                # Данные в БД свежие - используем их
                db_row = await self.db.get_ip_metadata(ip_address)
                if db_row:
                    metadata = self._metadata_from_db(db_row)
                    # Сохраняем в in-memory кэш для быстрого доступа
                    self._cache[ip_address] = (metadata, datetime.utcnow())
                    logger.debug("GeoIP DB cache hit for %s", ip_address)
                    return metadata
        
        # Уровень 3: Запрос к внешнему API
        try:
            await self._rate_limit()
            
            client = await self._get_client()
            url = self.API_URL.format(ip=ip_address)
            
            response = await client.get(url, params={'fields': self.FIELDS})
            response.raise_for_status()
            
            data = response.json()
            
            # Проверяем статус ответа
            if data.get('status') != 'success':
                error_message = data.get('message', 'Unknown error')
                logger.warning("GeoIP lookup failed for %s: %s", ip_address, error_message)
                return None
            
            # Извлекаем ASN из поля 'as' (формат: "AS12345 Organization Name")
            asn = None
            asn_raw = data.get('as', '')
            if asn_raw:
                # Парсим "AS12345 Organization Name" -> 12345
                asn_parts = asn_raw.split()
                for part in asn_parts:
                    if part.startswith('AS') and part[2:].isdigit():
                        try:
                            asn = int(part[2:])
                            break
                        except ValueError:
                            pass
            
            # Классифицируем тип провайдера (используем локальную базу ASN для РФ)
            asn_org = data.get('asname', '') or data.get('org', '') or data.get('isp', '')
            is_mobile = data.get('mobile', False)
            is_hosting = data.get('hosting', False)
            is_proxy = data.get('proxy', False)
            country_code = data.get('countryCode')
            
            connection_type, is_mobile_carrier, is_datacenter, is_vpn, asn_region, asn_city = await self._classify_asn(
                asn, asn_org, is_mobile, is_hosting, country_code
            )
            
            # Используем регион и город из базы ASN, если они есть (более точные данные для РФ)
            # Иначе используем данные из API
            final_region = asn_region or data.get('regionName')
            final_city = asn_city or data.get('city')
            
            metadata = IPMetadata(
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
                is_tor=False,  # ip-api.com не определяет Tor напрямую
                is_hosting=is_hosting,
                is_mobile=is_mobile_carrier
            )
            
            # Сохраняем в оба кэша: in-memory и БД
            self._cache[ip_address] = (metadata, datetime.utcnow())
            await self._save_metadata_to_db(metadata)
            
            logger.debug("GeoIP API lookup for %s: %s, %s", ip_address, metadata.country_code, metadata.city)
            
            return metadata
            
        except httpx.HTTPError as e:
            logger.error("HTTP error during GeoIP lookup for %s: %s", ip_address, e)
            return None
        except Exception as e:
            logger.error("Error during GeoIP lookup for %s: %s", ip_address, e, exc_info=True)
            return None
    
    async def lookup_batch(self, ip_addresses: list[str]) -> Dict[str, IPMetadata]:
        """
        Получить метаданные для нескольких IP адресов.
        
        Оптимизированная версия с трёхуровневым кэшированием:
        1. In-Memory кэш (24 часа)
        2. БД кэш (30 дней) - batch запрос
        3. Внешний API - только для отсутствующих
        
        Args:
            ip_addresses: Список IP адресов
        
        Returns:
            Словарь {ip: IPMetadata}
        """
        results = {}
        ips_to_check_db = []
        ips_to_fetch_api = []
        
        now = datetime.utcnow()
        
        # Уровень 1: Проверяем in-memory кэш для всех IP
        for ip in ip_addresses:
            # Пропускаем приватные IP
            if ip.startswith(('127.', '192.168.', '10.', '172.16.')):
                results[ip] = IPMetadata(ip=ip, country_code='PRIVATE', country_name='Private Network')
                continue
            
            if ip in self._cache:
                metadata, cached_at = self._cache[ip]
                if now - cached_at < self._cache_ttl:
                    results[ip] = metadata
                    logger.debug("GeoIP batch in-memory cache hit for %s", ip)
                    continue
            
            ips_to_check_db.append(ip)
        
        # Уровень 2: Проверяем БД batch запросом (если есть IP для проверки)
        db_hits = 0
        if ips_to_check_db and self.db and self.db.is_connected:
            # Получаем все доступные метаданные из БД одним запросом
            db_results = await self.db.get_ip_metadata_batch(ips_to_check_db)
            
            for ip in ips_to_check_db:
                db_row = db_results.get(ip)
                
                if db_row:
                    # Проверяем, свежие ли данные в БД
                    should_refresh = await self.db.should_refresh_ip_metadata(
                        ip, max_age_days=self._db_cache_ttl_days
                    )
                    
                    if not should_refresh:
                        # Данные свежие - используем их
                        metadata = self._metadata_from_db(db_row)
                        results[ip] = metadata
                        # Сохраняем в in-memory кэш
                        self._cache[ip] = (metadata, datetime.utcnow())
                        logger.debug("GeoIP batch DB cache hit for %s", ip)
                        db_hits += 1
                        continue
                
                # Данных нет или они устарели - нужно запросить у API
                ips_to_fetch_api.append(ip)
        else:
            # БД недоступна - все IP идут в API
            ips_to_fetch_api = ips_to_check_db
        
        # Уровень 3: Запросы к внешнему API только для отсутствующих IP
        if ips_to_fetch_api:
            in_memory_hits = len(results) - db_hits
            logger.info("GeoIP batch lookup: %d IPs from cache (in-memory: %d, DB: %d), %d IPs to fetch from API", 
                       len(results), in_memory_hits, db_hits, len(ips_to_fetch_api))
            
            for ip in ips_to_fetch_api:
                metadata = await self.lookup(ip, use_cache=False)  # use_cache=False так как уже проверили все уровни
                if metadata:
                    results[ip] = metadata
        
        return results
    
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
