"""Auto-extracted from shared/violation_detector.py."""
import asyncio
import json
import re
import time
from collections import defaultdict, Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone as tz
from itertools import combinations
from math import radians, sin, cos, sqrt, atan2
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from shared.analyzers.models import (
    ViolationAction, TemporalScore, GeoScore, ASNScore, ProfileScore,
    DeviceScore, HwidScore, UserAgentClassification, SuspiciousAgent,
    UserAgentScore, ViolationScore, MAX_EVIDENCE, connection_evidence,
)
from shared.connection_monitor import ConnectionMonitor, ActiveConnection, ConnectionStats
from shared.logger import logger
from shared.geoip import GeoIPService, IPMetadata, get_geoip_service
from shared.database import DatabaseService

class ASNAnalyzer:
    """
    Анализ типа интернет-провайдера (ASN).
    
    Использует локальную базу ASN по РФ для более точного определения типа провайдера.
    
    Детальная классификация типов провайдеров:
    - mobile: Точно мобильные пулы (CGNAT, LTE, GPRS) - ×0.3 модификатор (низкая подозрительность)
    - mobile_isp: Сети мобильных операторов (MegaFon, MTS, Beeline, Tele2) - ×0.5 модификатор
    - fixed: Проводной ШПД (Broadband, DSL, GPON) - ×0.8 модификатор (норма)
    - isp: Крупные провайдеры (ER-Telecom, ТТК, Ростелеком) - ×1.0 модификатор (стандартный)
    - regional_isp: Региональные ISP - ×1.0 модификатор (стандартный)
    - business: Корпоративные (Yandex, Mail.ru) - ×1.2 модификатор (повышенное внимание)
    - hosting: Хостинг (Selectel, Timeweb, Beget, VDSina) - ×1.5 модификатор (высокое внимание)
    - infrastructure: Магистральная инфраструктура - ×1.3 модификатор
    - vpn: VPN/Proxy - ×1.8 модификатор (очень высокое внимание)
    """
    
    # Модификаторы подозрительности для разных типов провайдеров
    PROVIDER_TYPE_MODIFIERS = {
        'mobile': 0.3,           # Мобильные пулы - очень низкая подозрительность
        'mobile_isp': 0.5,       # Мобильные операторы - низкая подозрительность
        'fixed': 0.8,           # Проводной ШПД - норма
        'isp': 1.0,             # Крупные провайдеры - стандарт
        'regional_isp': 1.0,     # Региональные ISP - стандарт
        'residential': 1.0,      # Домашние (legacy) - стандарт
        'business': 1.2,        # Корпоративные - повышенное внимание
        'infrastructure': 1.3,   # Магистральная инфраструктура - повышенное внимание
        'hosting': 1.5,         # Хостинг - высокое внимание
        'datacenter': 1.5,      # Датацентр (legacy) - высокое внимание
        'vpn': 1.8,             # VPN/Proxy - очень высокое внимание
        'unknown': 1.0,         # Неизвестный тип - стандарт
    }
    
    # Типы провайдеров, которые считаются мобильными
    MOBILE_TYPES = {'mobile', 'mobile_isp'}
    
    # Типы провайдеров, которые считаются датацентрами/хостингом
    DATACENTER_TYPES = {'hosting', 'datacenter'}
    
    # Типы провайдеров, которые считаются VPN
    VPN_TYPES = {'vpn'}
    
    def __init__(self, geoip_service: Optional[GeoIPService] = None, db_service: Optional[DatabaseService] = None):
        """
        Инициализирует ASNAnalyzer.
        
        Args:
            geoip_service: Сервис для получения метаданных IP (по умолчанию используется глобальный)
            db_service: Сервис для работы с БД (для доступа к базе ASN)
        """
        self.geoip = geoip_service or get_geoip_service()
        from shared.database import db_service as global_db_service
        self.db = db_service or global_db_service
    
    async def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]],
        ip_metadata_cache: Optional[Dict[str, 'IPMetadata']] = None,
    ) -> ASNScore:
        """
        Анализирует типы провайдеров для IP адресов.

        Args:
            connections: Активные подключения
            connection_history: История подключений
            ip_metadata_cache: Предзагруженный кэш GeoIP данных (для оптимизации)

        Returns:
            ASNScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        asn_types: Set[str] = set()
        is_mobile_carrier = False
        is_datacenter = False
        is_vpn = False

        # Собираем уникальные IP
        all_ips = set()
        for conn in connections:
            all_ips.add(str(conn.ip_address))
        for conn in connection_history:
            ip = str(conn.get("ip_address", ""))
            if ip:
                all_ips.add(ip)

        # Используем кэш если передан, иначе делаем lookup
        if ip_metadata_cache is not None:
            ip_metadata = {ip: ip_metadata_cache[ip] for ip in all_ips if ip in ip_metadata_cache}
        else:
            ip_metadata: Dict[str, IPMetadata] = await self.geoip.lookup_batch(list(all_ips))
        
        if not ip_metadata:
            if all_ips:
                logger.warning(
                    "GeoIP lookup returned empty result for %d IPs, ASN analysis skipped",
                    len(all_ips)
                )
            return ASNScore(
                score=0.0,
                reasons=[],
                asn_types=asn_types,
                is_mobile_carrier=False,
                is_datacenter=False,
                is_vpn=False
            )
        
        # Анализируем типы провайдеров с детальной классификацией
        provider_type_counts: Dict[str, int] = {}
        mobile_count = 0
        datacenter_count = 0
        vpn_count = 0
        business_count = 0
        infrastructure_count = 0
        
        for metadata in ip_metadata.values():
            if metadata.connection_type:
                asn_types.add(metadata.connection_type)
                provider_type = metadata.connection_type
                
                # Подсчитываем по типам
                provider_type_counts[provider_type] = provider_type_counts.get(provider_type, 0) + 1
                
                # Определяем категории для обратной совместимости
                if provider_type in self.MOBILE_TYPES:
                    mobile_count += 1
                    is_mobile_carrier = True
                elif provider_type in self.DATACENTER_TYPES:
                    datacenter_count += 1
                    is_datacenter = True
                elif provider_type in self.VPN_TYPES:
                    vpn_count += 1
                    is_vpn = True
                elif provider_type == 'business':
                    business_count += 1
                elif provider_type == 'infrastructure':
                    infrastructure_count += 1
        
        # Оценка на основе типов провайдеров в активных подключениях
        active_ips = {str(conn.ip_address) for conn in connections}
        active_provider_types: Dict[str, int] = {}
        
        for ip, meta in ip_metadata.items():
            if ip in active_ips and meta.connection_type:
                provider_type = meta.connection_type
                active_provider_types[provider_type] = active_provider_types.get(provider_type, 0) + 1
        
        # Подсчитываем подозрительные типы в активных подключениях
        active_datacenter_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype in self.DATACENTER_TYPES
        )
        active_vpn_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype in self.VPN_TYPES
        )
        active_business_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype == 'business'
        )
        active_infrastructure_count = sum(
            count for ptype, count in active_provider_types.items()
            if ptype == 'infrastructure'
        )
        
        # Оценка на основе типов провайдеров
        # Хостинг/датацентры - очень подозрительно
        if active_datacenter_count > 0:
            score += 25.0
            reasons.append(f"Подключения через хостинг/датацентр ({active_datacenter_count} IP)")
        
        # VPN - подозрительно
        if active_vpn_count > 0:
            score += 15.0
            reasons.append(f"Подключения через VPN ({active_vpn_count} IP)")
        
        # Корпоративные сети - умеренно подозрительно (может быть шаринг)
        if active_business_count > 0:
            score += 10.0
            reasons.append(f"Подключения через корпоративные сети ({active_business_count} IP)")
        
        # Магистральная инфраструктура - редко используется конечными пользователями
        if active_infrastructure_count > 0:
            score += 8.0
            reasons.append(f"Подключения через магистральную инфраструктуру ({active_infrastructure_count} IP)")
        
        # Если большинство подключений через подозрительные типы - более критично
        if len(active_ips) > 0:
            suspicious_count = active_datacenter_count + active_vpn_count + active_business_count
            suspicious_ratio = suspicious_count / len(active_ips)
            
            if suspicious_ratio > 0.7:
                score += 20.0
                reasons.append(f"Большинство подключений через подозрительные типы провайдеров ({suspicious_ratio*100:.0f}%)")
            elif suspicious_ratio > 0.5:
                score += 10.0
                reasons.append(f"Много подключений через подозрительные типы провайдеров ({suspicious_ratio*100:.0f}%)")
        
        # Улики: какие именно активные адреса дали подозрительный тип сети
        suspicious_types = self.DATACENTER_TYPES | self.VPN_TYPES | {"business", "infrastructure"}
        evidence = [
            connection_evidence(conn, ip_metadata[str(conn.ip_address)])
            for conn in connections
            if str(conn.ip_address) in ip_metadata
            and ip_metadata[str(conn.ip_address)].connection_type in suspicious_types
        ][:MAX_EVIDENCE]

        return ASNScore(
            score=min(score, 100.0),
            reasons=reasons,
            asn_types=asn_types,
            is_mobile_carrier=is_mobile_carrier,
            is_datacenter=is_datacenter,
            is_vpn=is_vpn,
            evidence=evidence,
        )


