"""
Сервис для парсинга и импорта базы ASN по РФ из RIPE Database.

Использует RIPE Database REST API для получения данных об ASN в России.
"""
import asyncio
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

import httpx
from shared.config import get_shared_settings as get_settings
from shared.database import DatabaseService
from shared.logger import logger


@dataclass
class ASNRecord:
    """Запись ASN из базы данных."""
    asn: int
    org_name: str
    org_name_en: Optional[str] = None
    provider_type: Optional[str] = None  # mobile/residential/datacenter/vpn/isp
    region: Optional[str] = None
    city: Optional[str] = None
    country_code: str = "RU"
    description: Optional[str] = None
    ip_ranges: Optional[List[str]] = None


class ASNParser:
    """
    Парсер базы ASN по РФ из RIPE Database.
    
    Использует RIPE Database REST API для получения данных об ASN.
    """
    
    # URL для RIPE Database API
    RIPE_API_URL = "https://rest.db.ripe.net"
    
    # Ключевые слова для определения типа провайдера
    # Классификация по типам из таблицы статистики
    
    # Крупные провайдеры (ER-Telecom, ТТК, Ростелеком)
    ISP_KEYWORDS = {
        'ростелеком', 'rostelecom', 'рт', 'rt', 'er-telecom', 'er telecom', 'ттк', 'ttk',
        'transit', 'транзит', 'mts', 'мтс', 'mts telecom', 'мтс телеком',
        'большой провайдер', 'major isp', 'tier 1', 'tier-1'
    }
    
    # Региональные ISP
    REGIONAL_ISP_KEYWORDS = {
        'региональный', 'regional', 'областной', 'область', 'область связи',
        'городской', 'city', 'муниципальный', 'municipal', 'локальный', 'local',
        'районный', 'district', 'областной провайдер', 'regional isp'
    }
    
    # Проводной ШПД (Broadband, DSL, GPON)
    FIXED_KEYWORDS = {
        'dsl', 'adsl', 'vdsl', 'gpon', 'ftth', 'fttb', 'ethernet', 'ethernet',
        'проводной', 'wired', 'broadband', 'широкополосный', 'шпд',
        'кабель', 'cable', 'оптика', 'fiber', 'волокно', 'волоконно',
        'домашний интернет', 'home internet', 'residential', 'домашний'
    }
    
    # Сети мобильных операторов (MegaFon, MTS, Beeline, Tele2)
    MOBILE_ISP_KEYWORDS = {
        'мегафон', 'megafon', 'мтс', 'mts', 'билайн', 'beeline', 'теле2', 'tele2',
        'йота', 'yota', 'ростелеком мобайл', 'rostelecom mobile',
        'мобильный оператор', 'mobile operator', 'cellular operator',
        'сотовый оператор', 'mobile network', 'мобильная сеть'
    }
    
    # Хостинг (Selectel, Timeweb, Beget, VDSina)
    HOSTING_KEYWORDS = {
        'selectel', 'селектел', 'timeweb', 'таймвеб', 'beget', 'бегет',
        'vdsina', 'вдсина', 'хостинг', 'hosting', 'vps', 'vds', 'dedicated',
        'сервер', 'server', 'colo', 'colocation', 'idc', 'datacenter',
        'data center', 'датацентр', 'cloud', 'облако', 'cloud provider'
    }
    
    # Корпоративные (Yandex, Mail.ru)
    BUSINESS_KEYWORDS = {
        'yandex', 'яндекс', 'mail.ru', 'mailru', 'корпоративный', 'corporate',
        'enterprise', 'бизнес', 'business', 'компания', 'company',
        'корпорация', 'corporation', 'холдинг', 'holding'
    }
    
    # Точно мобильные пулы (CGNAT, LTE, GPRS)
    MOBILE_KEYWORDS = {
        'cgnat', 'cg-nat', 'lte', '4g', '5g', 'gprs', 'umts', 'wcdma',
        'мобильный пул', 'mobile pool', 'mobile ip', 'мобильный ip',
        'nat', 'carrier grade nat', 'carrier-grade nat'
    }
    
    # Магистральная инфраструктура
    INFRASTRUCTURE_KEYWORDS = {
        'магистраль', 'backbone', 'транзит', 'transit', 'peering', 'пиринг',
        'ix', 'internet exchange', 'интернет-обмен', 'транспорт', 'transport',
        'core network', 'основная сеть', 'магистральная сеть'
    }
    
    # VPN/Proxy (для обратной совместимости)
    VPN_KEYWORDS = {
        'vpn', 'прокси', 'proxy', 'анонимайзер', 'anonymizer', 'privacy',
        'tunnel', 'туннель'
    }
    
    # Маппинг регионов РФ (для определения региона из описания)
    REGION_KEYWORDS = {
        'москва': 'Москва',
        'moscow': 'Москва',
        'санкт-петербург': 'Санкт-Петербург',
        'saint-petersburg': 'Санкт-Петербург',
        'st. petersburg': 'Санкт-Петербург',
        'spb': 'Санкт-Петербург',
        'новосибирск': 'Новосибирск',
        'novosibirsk': 'Новосибирск',
        'екатеринбург': 'Екатеринбург',
        'ekaterinburg': 'Екатеринбург',
        'казань': 'Казань',
        'kazan': 'Казань',
        'нижний новгород': 'Нижний Новгород',
        'nizhny novgorod': 'Нижний Новгород',
        'челябинск': 'Челябинск',
        'chelyabinsk': 'Челябинск',
        'самара': 'Самара',
        'samara': 'Самара',
        'омск': 'Омск',
        'omsk': 'Омск',
        'ростов-на-дону': 'Ростов-на-Дону',
        'rostov-on-don': 'Ростов-на-Дону',
        'уфа': 'Уфа',
        'ufa': 'Уфа',
        'красноярск': 'Красноярск',
        'krasnoyarsk': 'Красноярск',
        'воронеж': 'Воронеж',
        'voronezh': 'Воронеж',
        'пермь': 'Пермь',
        'perm': 'Пермь',
        'волгоград': 'Волгоград',
        'volgograd': 'Волгоград',
        'краснодар': 'Краснодар',
        'krasnodar': 'Краснодар',
        'саратов': 'Саратов',
        'saratov': 'Саратов',
        'тюмень': 'Тюмень',
        'tyumen': 'Тюмень',
        'тольятти': 'Тольятти',
        'tolyatti': 'Тольятти',
    }
    
    def __init__(self, db_service: DatabaseService):
        """
        Инициализирует ASNParser.
        
        Args:
            db_service: Сервис для работы с БД
        """
        self.settings = get_settings()
        self.db = db_service
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Получить или создать HTTP клиент."""
        if self._client is None:
            timeout = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=30.0)
            headers = {
                'Accept': 'application/json',
                'User-Agent': 'Remnawave-Admin-Bot/1.0'
            }
            self._client = httpx.AsyncClient(timeout=timeout, headers=headers)
        return self._client
    
    async def close(self):
        """Закрыть HTTP клиент."""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _classify_provider_type(self, org_name: str, description: Optional[str] = None) -> Optional[str]:
        """
        Классифицирует тип провайдера на основе названия организации и описания.
        
        Использует детальную классификацию:
        - mobile: Точно мобильные пулы (CGNAT, LTE, GPRS)
        - mobile_isp: Сети мобильных операторов (MegaFon, MTS, Beeline, Tele2)
        - isp: Крупные провайдеры (ER-Telecom, ТТК, Ростелеком)
        - regional_isp: Региональные ISP
        - fixed: Проводной ШПД (Broadband, DSL, GPON)
        - hosting: Хостинг (Selectel, Timeweb, Beget, VDSina)
        - business: Корпоративные (Yandex, Mail.ru)
        - infrastructure: Магистральная инфраструктура
        - vpn: VPN/Proxy (для обратной совместимости)
        
        Args:
            org_name: Название организации
            description: Описание ASN
        
        Returns:
            Тип провайдера или None
        """
        text = (org_name + " " + (description or "")).lower()
        
        # Приоритет проверки: от более специфичных к общим
        
        # 1. Точно мобильные пулы (CGNAT, LTE, GPRS) - самый специфичный
        if any(keyword in text for keyword in self.MOBILE_KEYWORDS):
            return 'mobile'
        
        # 2. VPN/Proxy
        if any(keyword in text for keyword in self.VPN_KEYWORDS):
            return 'vpn'
        
        # 3. Хостинг (проверяем раньше, так как может содержать "server")
        if any(keyword in text for keyword in self.HOSTING_KEYWORDS):
            return 'hosting'
        
        # 4. Корпоративные сети
        if any(keyword in text for keyword in self.BUSINESS_KEYWORDS):
            return 'business'
        
        # 5. Магистральная инфраструктура
        if any(keyword in text for keyword in self.INFRASTRUCTURE_KEYWORDS):
            return 'infrastructure'
        
        # 6. Сети мобильных операторов (проверяем после mobile, так как более общий)
        if any(keyword in text for keyword in self.MOBILE_ISP_KEYWORDS):
            return 'mobile_isp'
        
        # 7. Проводной ШПД (проверяем перед ISP, так как более специфичный)
        if any(keyword in text for keyword in self.FIXED_KEYWORDS):
            return 'fixed'
        
        # 8. Крупные провайдеры
        if any(keyword in text for keyword in self.ISP_KEYWORDS):
            return 'isp'
        
        # 9. Региональные ISP (проверяем последним среди ISP)
        if any(keyword in text for keyword in self.REGIONAL_ISP_KEYWORDS):
            return 'regional_isp'
        
        # По умолчанию считаем fixed (проводной ШПД) - наиболее распространённый тип
        return 'fixed'
    
    def _extract_region_city(self, org_name: str, description: Optional[str] = None) -> tuple[Optional[str], Optional[str]]:
        """
        Извлекает регион и город из названия организации и описания.
        
        Args:
            org_name: Название организации
            description: Описание ASN
        
        Returns:
            Кортеж (region, city)
        """
        text = (org_name + " " + (description or "")).lower()
        
        region = None
        city = None
        
        # Ищем города в тексте
        for keyword, city_name in self.REGION_KEYWORDS.items():
            if keyword in text:
                city = city_name
                # Определяем регион на основе города
                if city_name in ['Москва', 'Санкт-Петербург']:
                    region = city_name
                else:
                    # Для других городов можно добавить маппинг регионов
                    # Пока оставляем None
                    pass
                break
        
        return region, city
    
    async def fetch_asn_from_ripe(self, asn: int) -> Optional[Dict]:
        """
        Получить данные об ASN из RIPE Database.
        
        Args:
            asn: Номер ASN
        
        Returns:
            Словарь с данными ASN или None при ошибке
        """
        try:
            client = await self._get_client()
            url = f"{self.RIPE_API_URL}/ripe/aut-num/AS{asn}.json"
            
            response = await client.get(url)
            response.raise_for_status()
            
            data = response.json()
            
            # Парсим данные из формата RIPE Database
            # Структура: data['objects']['object'] - массив объектов
            if 'objects' in data:
                objects_data = data['objects']
                # objects может быть словарём с ключом 'object' (список) или списком
                if isinstance(objects_data, dict) and 'object' in objects_data:
                    objects_list = objects_data['object']
                elif isinstance(objects_data, list):
                    objects_list = objects_data
                else:
                    logger.debug("Unexpected objects structure for ASN %d: %s", asn, type(objects_data))
                    return None
                
                if not objects_list or len(objects_list) == 0:
                    logger.debug("No objects found for ASN %d", asn)
                    return None
                
                obj = objects_list[0]
                
                # attributes может быть словарём с ключом 'attribute' (список) или списком
                attributes_data = obj.get('attributes', {})
                if isinstance(attributes_data, dict) and 'attribute' in attributes_data:
                    attributes = attributes_data['attribute']
                elif isinstance(attributes_data, list):
                    attributes = attributes_data
                else:
                    logger.debug("Unexpected attributes structure for ASN %d: %s", asn, type(attributes_data))
                    attributes = []
                
                # Извлекаем атрибуты
                result = {
                    'asn': asn,
                    'org_name': '',
                    'org_name_en': None,
                    'description': None,
                    'country': 'RU'
                }
                
                # Парсим атрибуты
                for attr in attributes:
                    if not isinstance(attr, dict):
                        continue
                    
                    attr_name = attr.get('name', '').lower()
                    attr_value = attr.get('value', '')
                    
                    if attr_name == 'org':
                        result['org_name'] = attr_value
                    elif attr_name == 'as-name':
                        # ASN название (может быть на английском)
                        if not result['org_name']:
                            result['org_name'] = attr_value
                        result['org_name_en'] = attr_value
                    elif attr_name == 'descr':
                        if not result['description']:
                            result['description'] = attr_value
                        else:
                            result['description'] += f"; {attr_value}"
                    elif attr_name == 'country':
                        result['country'] = attr_value.upper()
                
                # Если org_name не найден, используем as-name или aut-num
                if not result['org_name']:
                    result['org_name'] = result.get('org_name_en') or f'AS{asn}'
                
                return result
            
            return None
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.debug("ASN %d not found in RIPE Database", asn)
            else:
                logger.warning("HTTP error fetching ASN %d from RIPE: %s", asn, e)
            return None
        except Exception as e:
            logger.error("Error fetching ASN %d from RIPE: %s", asn, e, exc_info=True)
            return None
    
    async def fetch_russian_asn_list(self) -> List[int]:
        """
        Получить список всех ASN в России из RIPE Stat API.
        
        Returns:
            Список номеров ASN
        """
        try:
            client = await self._get_client()
            # Используем RIPE Stat API для получения списка ASN по стране
            url = "https://stat.ripe.net/data/country-resource-list/data.json"
            params = {
                'resource': 'RU',
                'lod': 1  # Level of detail: 1 = ASN only
            }
            
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            asn_list = []
            if 'data' in data and 'resources' in data['data']:
                resources = data['data']['resources']
                if 'asn' in resources:
                    for asn_str in resources['asn']:
                        # Извлекаем номер ASN из строки (может быть "AS12345" или "12345")
                        asn_match = re.search(r'(\d+)', str(asn_str))
                        if asn_match:
                            asn_num = int(asn_match.group(1))
                            asn_list.append(asn_num)
            
            logger.info("Found %d ASN numbers for Russia", len(asn_list))
            return asn_list
            
        except Exception as e:
            logger.error("Error fetching Russian ASN list: %s", e, exc_info=True)
            return []
    
    async def parse_and_save_asn(self, asn: int) -> bool:
        """
        Парсит данные об ASN и сохраняет в БД.
        
        Args:
            asn: Номер ASN
        
        Returns:
            True если успешно, False при ошибке
        """
        try:
            # Получаем данные из RIPE
            ripe_data = await self.fetch_asn_from_ripe(asn)
            
            if not ripe_data:
                return False
            
            # Классифицируем тип провайдера
            provider_type = self._classify_provider_type(
                ripe_data.get('org_name', ''),
                ripe_data.get('description')
            )
            
            # Извлекаем регион и город
            region, city = self._extract_region_city(
                ripe_data.get('org_name', ''),
                ripe_data.get('description')
            )
            
            # Создаём запись ASN
            asn_record = ASNRecord(
                asn=asn,
                org_name=ripe_data.get('org_name', f'AS{asn}'),
                org_name_en=ripe_data.get('org_name_en'),
                provider_type=provider_type,
                region=region,
                city=city,
                country_code=ripe_data.get('country', 'RU'),
                description=ripe_data.get('description')
            )
            
            # Сохраняем в БД
            return await self.db.save_asn_record(asn_record)
            
        except Exception as e:
            logger.error("Error parsing and saving ASN %d: %s", asn, e, exc_info=True)
            return False
    
    async def sync_russian_asn_database(self, limit: Optional[int] = None) -> Dict[str, int]:
        """
        Синхронизирует базу ASN по РФ из RIPE Database.
        
        Args:
            limit: Максимальное количество ASN для обработки (None = все)
        
        Returns:
            Словарь со статистикой: {'total': ..., 'success': ..., 'failed': ..., 'skipped': ...}
        """
        logger.info("Starting Russian ASN database sync...")
        
        # Получаем список ASN
        asn_list = await self.fetch_russian_asn_list()
        
        if not asn_list:
            logger.warning("No ASN numbers found for Russia")
            return {'total': 0, 'success': 0, 'failed': 0, 'skipped': 0}
        
        if limit:
            asn_list = asn_list[:limit]
        
        total = len(asn_list)
        success = 0
        failed = 0
        skipped = 0
        
        # Обрабатываем каждый ASN
        for i, asn in enumerate(asn_list, 1):
            try:
                # Проверяем, существует ли уже запись
                existing = await self.db.get_asn_record(asn)
                if existing:
                    skipped += 1
                    if i % 100 == 0:
                        logger.info("Progress: %d/%d (success: %d, failed: %d, skipped: %d)", 
                                  i, total, success, failed, skipped)
                    continue
                
                # Парсим и сохраняем
                if await self.parse_and_save_asn(asn):
                    success += 1
                else:
                    failed += 1
                
                # Логируем прогресс каждые 100 ASN
                if i % 100 == 0:
                    logger.info("Progress: %d/%d (success: %d, failed: %d, skipped: %d)", 
                              i, total, success, failed, skipped)
                
                # Небольшая задержка, чтобы не перегружать API
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error("Error processing ASN %d: %s", asn, e, exc_info=True)
                failed += 1
        
        logger.info("Russian ASN database sync completed: total=%d, success=%d, failed=%d, skipped=%d",
                   total, success, failed, skipped)
        
        # Обновляем время последней синхронизации
        await self.db.update_asn_sync_time()
        
        return {
            'total': total,
            'success': success,
            'failed': failed,
            'skipped': skipped
        }
