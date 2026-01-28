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
    
    def __init__(self):
        self.settings = get_settings()
        self._cache: Dict[str, tuple[IPMetadata, datetime]] = {}
        self._cache_ttl = timedelta(hours=24)  # Кэш на 24 часа
        self._rate_limit_delay = 1.5  # Задержка между запросами (45 запросов/мин = ~1.3 сек/запрос)
        self._last_request_time: Optional[datetime] = None
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент."""
        if self._client is None:
            timeout = httpx.Timeout(connect=5.0, read=10.0)
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
    
    def _classify_asn(self, asn_org: Optional[str], is_mobile: bool, is_hosting: bool) -> tuple[str, bool, bool, bool]:
        """
        Классифицирует тип провайдера на основе ASN организации.
        
        Returns:
            (connection_type, is_mobile_carrier, is_datacenter, is_vpn)
        """
        if not asn_org:
            return ('unknown', False, False, False)
        
        asn_lower = asn_org.lower()
        
        # Проверка на VPN
        is_vpn = any(keyword in asn_lower for keyword in self.VPN_KEYWORDS)
        if is_vpn:
            return ('vpn', False, False, True)
        
        # Проверка на мобильный оператор
        is_mobile_carrier = is_mobile or any(carrier in asn_lower for carrier in self.MOBILE_CARRIERS)
        if is_mobile_carrier:
            return ('mobile', True, False, False)
        
        # Проверка на датацентр/хостинг
        is_datacenter = is_hosting or any(keyword in asn_lower for keyword in self.DATACENTER_KEYWORDS)
        if is_datacenter:
            return ('datacenter', False, True, False)
        
        # По умолчанию - домашний провайдер
        return ('residential', False, False, False)
    
    async def lookup(self, ip_address: str, use_cache: bool = True) -> Optional[IPMetadata]:
        """
        Получить метаданные IP адреса.
        
        Args:
            ip_address: IP адрес для поиска
            use_cache: Использовать кэш если доступен
        
        Returns:
            IPMetadata или None при ошибке
        """
        # Проверяем кэш
        if use_cache and ip_address in self._cache:
            metadata, cached_at = self._cache[ip_address]
            if datetime.utcnow() - cached_at < self._cache_ttl:
                return metadata
        
        # Пропускаем приватные IP
        if ip_address.startswith(('127.', '192.168.', '10.', '172.16.')):
            return IPMetadata(ip=ip_address, country_code='PRIVATE', country_name='Private Network')
        
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
            
            # Классифицируем тип провайдера
            asn_org = data.get('asname', '') or data.get('org', '') or data.get('isp', '')
            is_mobile = data.get('mobile', False)
            is_hosting = data.get('hosting', False)
            is_proxy = data.get('proxy', False)
            
            connection_type, is_mobile_carrier, is_datacenter, is_vpn = self._classify_asn(
                asn_org, is_mobile, is_hosting
            )
            
            metadata = IPMetadata(
                ip=ip_address,
                country_code=data.get('countryCode'),
                country_name=data.get('country'),
                region=data.get('regionName'),
                city=data.get('city'),
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
            
            # Сохраняем в кэш
            self._cache[ip_address] = (metadata, datetime.utcnow())
            
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
        
        Args:
            ip_addresses: Список IP адресов
        
        Returns:
            Словарь {ip: IPMetadata}
        """
        results = {}
        
        for ip in ip_addresses:
            metadata = await self.lookup(ip)
            if metadata:
                results[ip] = metadata
        
        return results
    
    def clear_cache(self):
        """Очистить кэш."""
        self._cache.clear()


# Глобальный экземпляр сервиса
_geoip_service: Optional[GeoIPService] = None


def get_geoip_service() -> GeoIPService:
    """Получить глобальный экземпляр GeoIP сервиса."""
    global _geoip_service
    if _geoip_service is None:
        _geoip_service = GeoIPService()
    return _geoip_service
