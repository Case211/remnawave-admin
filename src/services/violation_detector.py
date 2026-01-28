"""
IntelligentViolationDetector — система многофакторного анализа для детектирования нарушений.

Анализирует подключения пользователей на основе:
- Временных паттернов
- Геолокации
- Типа провайдера (ASN)
- Исторического профиля пользователя
- Fingerprint устройств
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Set
from enum import Enum

from src.services.database import DatabaseService
from src.services.connection_monitor import ConnectionMonitor, ActiveConnection, ConnectionStats
from src.utils.logger import logger


class ViolationAction(Enum):
    """Рекомендуемое действие при нарушении."""
    NO_ACTION = "no_action"
    MONITOR = "monitor"
    WARN = "warn"
    SOFT_BLOCK = "soft_block"
    TEMP_BLOCK = "temp_block"
    HARD_BLOCK = "hard_block"


@dataclass
class TemporalScore:
    """Скор временного анализа."""
    score: float
    reasons: List[str]
    simultaneous_connections_count: int = 0
    rapid_switches_count: int = 0


@dataclass
class GeoScore:
    """Скор географического анализа."""
    score: float
    reasons: List[str]
    countries: Set[str]
    cities: Set[str]
    impossible_travel_detected: bool = False


@dataclass
class ASNScore:
    """Скор анализа провайдера."""
    score: float
    reasons: List[str]
    asn_types: Set[str]
    is_mobile_carrier: bool = False
    is_datacenter: bool = False
    is_vpn: bool = False


@dataclass
class ProfileScore:
    """Скор анализа профиля пользователя."""
    score: float
    reasons: List[str]
    deviation_from_baseline: float = 0.0


@dataclass
class DeviceScore:
    """Скор анализа устройств."""
    score: float
    reasons: List[str]
    unique_fingerprints_count: int = 0
    different_os_count: int = 0


@dataclass
class ViolationScore:
    """Итоговый скор нарушения."""
    total: float
    breakdown: Dict[str, Any]
    recommended_action: ViolationAction
    confidence: float
    reasons: List[str]


class TemporalAnalyzer:
    """
    Анализ временных паттернов смены IP.
    
    Правила:
    - Последовательная смена IP (gap > 5 мин) = 0 (нормально)
    - Быстрая смена IP (gap < 1 мин), близкие гео = +10
    - Быстрая смена IP, далёкие гео = +40
    - Одновременные соединения = +80
    - Одновременные соединения > 3 IP = +100
    """
    
    def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]]
    ) -> TemporalScore:
        """
        Анализирует временные паттерны подключений.
        
        Args:
            connections: Активные подключения
            connection_history: История подключений за период
        
        Returns:
            TemporalScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        simultaneous_count = len(connections)
        rapid_switches = 0
        
        # Проверка одновременных подключений
        if simultaneous_count > 1:
            if simultaneous_count > 3:
                score = 100.0
                reasons.append(f"Одновременные подключения с {simultaneous_count} разных IP (> 3)")
            else:
                score = 80.0
                reasons.append(f"Одновременные подключения с {simultaneous_count} разных IP")
        
        # Анализ быстрой смены IP в истории
        if len(connection_history) > 1:
            # Сортируем по времени подключения
            sorted_history = sorted(
                connection_history,
                key=lambda x: x.get("connected_at") or datetime.min
            )
            
            for i in range(1, len(sorted_history)):
                prev_conn = sorted_history[i - 1]
                curr_conn = sorted_history[i]
                
                prev_time = prev_conn.get("connected_at")
                curr_time = curr_conn.get("connected_at")
                
                if not prev_time or not curr_time:
                    continue
                
                # Преобразуем в datetime если нужно
                if isinstance(prev_time, str):
                    try:
                        prev_time = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                    except ValueError:
                        continue
                if isinstance(curr_time, str):
                    try:
                        curr_time = datetime.fromisoformat(curr_time.replace('Z', '+00:00'))
                    except ValueError:
                        continue
                
                if not isinstance(prev_time, datetime) or not isinstance(curr_time, datetime):
                    continue
                
                # Убираем timezone для сравнения
                if prev_time.tzinfo:
                    prev_time = prev_time.replace(tzinfo=None)
                if curr_time.tzinfo:
                    curr_time = curr_time.replace(tzinfo=None)
                
                time_diff = (curr_time - prev_time).total_seconds() / 60  # минуты
                
                prev_ip = str(prev_conn.get("ip_address", ""))
                curr_ip = str(curr_conn.get("ip_address", ""))
                
                # Если IP разные и переключение быстрое (< 1 минуты)
                if prev_ip != curr_ip and time_diff < 1:
                    rapid_switches += 1
                    # Проверяем, есть ли информация о геолокации
                    # Пока добавляем базовый скор, геолокация будет добавлена позже
                    if rapid_switches == 1:
                        score += 10.0
                        reasons.append(f"Быстрое переключение между IP ({prev_ip} → {curr_ip} за {time_diff:.1f} мин)")
                    else:
                        score += 5.0  # Дополнительные быстрые переключения
        
        return TemporalScore(
            score=min(score, 100.0),  # Максимум 100
            reasons=reasons,
            simultaneous_connections_count=simultaneous_count,
            rapid_switches_count=rapid_switches
        )


class GeoAnalyzer:
    """
    Анализ географического распределения IP.
    
    Правила:
    - Все IP из одного города = 0
    - IP из разных городов одной страны = +5
    - IP из разных стран, последовательно, реалистично = +15
    - IP из разных стран, нереалистичное время = +50
    - IP из разных стран одновременно = +90
    """
    
    # Скорости перемещения (км/ч)
    TRAVEL_SPEEDS = {
        'same_city': 50,      # км/ч (такси/метро)
        'same_country': 200,  # км/ч (поезд/машина)
        'international': 800, # км/ч (самолёт)
    }
    
    def __init__(self):
        # TODO: Интеграция с GeoIP сервисом (MaxMind, ip-api.com и т.д.)
        # Пока используем заглушку
        self._geo_cache: Dict[str, Dict[str, str]] = {}
    
    def _get_ip_location(self, ip_address: str) -> Optional[Dict[str, str]]:
        """
        Получить геолокацию IP адреса.
        
        TODO: Интегрировать с GeoIP сервисом
        
        Args:
            ip_address: IP адрес
        
        Returns:
            Словарь с 'country', 'city' или None
        """
        # Заглушка - в реальности нужно использовать GeoIP API
        # Например: ip-api.com, MaxMind GeoIP2, ip2location и т.д.
        if ip_address in self._geo_cache:
            return self._geo_cache[ip_address]
        
        # Пока возвращаем None - геолокация будет добавлена позже
        return None
    
    def _haversine_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Вычислить расстояние между двумя точками по формуле Haversine (км).
        
        Args:
            lat1, lon1: Координаты первой точки
            lat2, lon2: Координаты второй точки
        
        Returns:
            Расстояние в километрах
        """
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371  # Радиус Земли в км
        
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        delta_lat = radians(lat2 - lat1)
        delta_lon = radians(lon2 - lon1)
        
        a = sin(delta_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))
        
        return R * c
    
    def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]]
    ) -> GeoScore:
        """
        Анализирует географическое распределение IP.
        
        Args:
            connections: Активные подключения
            connection_history: История подключений
        
        Returns:
            GeoScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        countries: Set[str] = set()
        cities: Set[str] = set()
        impossible_travel = False
        
        # Собираем уникальные IP из активных подключений и истории
        all_ips = set()
        for conn in connections:
            all_ips.add(str(conn.ip_address))
        for conn in connection_history:
            ip = str(conn.get("ip_address", ""))
            if ip:
                all_ips.add(ip)
        
        # Получаем геолокацию для каждого IP
        ip_locations: Dict[str, Dict[str, str]] = {}
        for ip in all_ips:
            location = self._get_ip_location(ip)
            if location:
                ip_locations[ip] = location
                countries.add(location.get("country", ""))
                cities.add(location.get("city", ""))
        
        # Если нет данных о геолокации, возвращаем нулевой скор
        if not ip_locations:
            return GeoScore(
                score=0.0,
                reasons=["Нет данных о геолокации IP адресов"],
                countries=countries,
                cities=cities,
                impossible_travel_detected=False
            )
        
        # Анализ одновременных подключений с разных стран
        active_countries = set()
        for conn in connections:
            ip = str(conn.ip_address)
            if ip in ip_locations:
                country = ip_locations[ip].get("country", "")
                if country:
                    active_countries.add(country)
        
        if len(active_countries) > 1:
            score = 90.0
            reasons.append(f"Одновременные подключения из разных стран: {', '.join(active_countries)}")
            impossible_travel = True
        
        # Анализ последовательных подключений
        if len(connection_history) > 1 and not impossible_travel:
            sorted_history = sorted(
                connection_history,
                key=lambda x: x.get("connected_at") or datetime.min
            )
            
            for i in range(1, len(sorted_history)):
                prev_conn = sorted_history[i - 1]
                curr_conn = sorted_history[i]
                
                prev_ip = str(prev_conn.get("ip_address", ""))
                curr_ip = str(curr_conn.get("ip_address", ""))
                
                if prev_ip not in ip_locations or curr_ip not in ip_locations:
                    continue
                
                prev_loc = ip_locations[prev_ip]
                curr_loc = ip_locations[curr_ip]
                
                prev_country = prev_loc.get("country", "")
                curr_country = curr_loc.get("country", "")
                prev_city = prev_loc.get("city", "")
                curr_city = curr_loc.get("city", "")
                
                # Разные страны
                if prev_country != curr_country and prev_country and curr_country:
                    prev_time = prev_conn.get("connected_at")
                    curr_time = curr_conn.get("connected_at")
                    
                    if prev_time and curr_time:
                        # Преобразуем в datetime
                        if isinstance(prev_time, str):
                            try:
                                prev_time = datetime.fromisoformat(prev_time.replace('Z', '+00:00'))
                            except ValueError:
                                continue
                        if isinstance(curr_time, str):
                            try:
                                curr_time = datetime.fromisoformat(curr_time.replace('Z', '+00:00'))
                            except ValueError:
                                continue
                        
                        if isinstance(prev_time, datetime) and isinstance(curr_time, datetime):
                            if prev_time.tzinfo:
                                prev_time = prev_time.replace(tzinfo=None)
                            if curr_time.tzinfo:
                                curr_time = curr_time.replace(tzinfo=None)
                            
                            time_diff_hours = (curr_time - prev_time).total_seconds() / 3600
                            
                            # Проверяем реалистичность перемещения
                            # TODO: Использовать реальные координаты для вычисления расстояния
                            # Пока используем эвристику: международное перемещение должно занимать минимум 1 час
                            if time_diff_hours < 1:
                                score = max(score, 50.0)
                                reasons.append(
                                    f"Нереалистичное перемещение: {prev_country} → {curr_country} за {time_diff_hours:.1f} ч"
                                )
                                impossible_travel = True
                            else:
                                score = max(score, 15.0)
                                reasons.append(f"Перемещение между странами: {prev_country} → {curr_country}")
                
                # Разные города одной страны
                elif prev_country == curr_country and prev_city != curr_city and prev_city and curr_city:
                    score = max(score, 5.0)
                    if not reasons:
                        reasons.append(f"Разные города одной страны: {prev_city} → {curr_city}")
        
        return GeoScore(
            score=min(score, 100.0),
            reasons=reasons,
            countries=countries,
            cities=cities,
            impossible_travel_detected=impossible_travel
        )


class IntelligentViolationDetector:
    """
    Система многофакторного анализа для детектирования нарушений.
    
    Объединяет результаты всех анализаторов и вычисляет итоговый скор нарушения.
    """
    
    # Веса факторов
    WEIGHTS = {
        'temporal': 0.25,      # Временной паттерн
        'geo': 0.25,           # География
        'asn': 0.15,           # Тип провайдера
        'profile': 0.20,        # Отклонение от профиля
        'device': 0.15,        # Fingerprint устройств
    }
    
    # Пороги для действий
    THRESHOLDS = {
        'no_action': 30,       # < 30: ничего не делаем
        'monitor': 50,         # 30-50: усиленный мониторинг
        'warn': 65,            # 50-65: предупреждение пользователю
        'soft_block': 80,      # 65-80: мягкая блокировка (ограничение скорости)
        'temp_block': 90,      # 80-90: временная блокировка
        'hard_block': 95,      # > 95: блокировка + ручная проверка
    }
    
    def __init__(self, db_service: DatabaseService, connection_monitor: ConnectionMonitor):
        self.db = db_service
        self.connection_monitor = connection_monitor
        self.temporal_analyzer = TemporalAnalyzer()
        self.geo_analyzer = GeoAnalyzer()
    
    async def check_user(self, user_uuid: str, window_minutes: int = 60) -> Optional[ViolationScore]:
        """
        Проверить пользователя на нарушения.
        
        Args:
            user_uuid: UUID пользователя
            window_minutes: Временное окно для анализа (по умолчанию 60 минут)
        
        Returns:
            ViolationScore или None при ошибке
        """
        if not self.db.is_connected:
            logger.warning("Database not connected, cannot check user violations")
            return None
        
        try:
            # Получаем активные подключения
            active_connections = await self.connection_monitor.get_user_active_connections(user_uuid)
            
            # Получаем историю подключений
            history_days = max(1, window_minutes // (24 * 60) + 1)
            connection_history = await self.db.get_connection_history(user_uuid, days=history_days)
            
            # Анализируем временные паттерны
            temporal_score = self.temporal_analyzer.analyze(active_connections, connection_history)
            
            # Анализируем геолокацию
            geo_score = self.geo_analyzer.analyze(active_connections, connection_history)
            
            # TODO: Добавить ASN анализ, профильный анализ и анализ устройств
            asn_score = ASNScore(score=0.0, reasons=[], asn_types=set())
            profile_score = ProfileScore(score=0.0, reasons=[], deviation_from_baseline=0.0)
            device_score = DeviceScore(score=0.0, reasons=[], unique_fingerprints_count=0, different_os_count=0)
            
            # Вычисляем взвешенный скор
            raw_score = (
                temporal_score.score * self.WEIGHTS['temporal'] +
                geo_score.score * self.WEIGHTS['geo'] +
                asn_score.score * self.WEIGHTS['asn'] +
                profile_score.score * self.WEIGHTS['profile'] +
                device_score.score * self.WEIGHTS['device']
            )
            
            # Модификаторы
            if asn_score.is_mobile_carrier:
                raw_score *= 0.7  # Снижаем для мобильных операторов
            
            # Если есть одновременные подключения, минимум 85
            if temporal_score.simultaneous_connections_count > 1:
                raw_score = max(raw_score, 85.0)
            
            # Определяем рекомендуемое действие
            recommended_action = self._get_action(raw_score)
            
            # Вычисляем уверенность (пока упрощённо)
            confidence = min(1.0, raw_score / 100.0)
            
            # Собираем все причины
            all_reasons = []
            all_reasons.extend(temporal_score.reasons)
            all_reasons.extend(geo_score.reasons)
            all_reasons.extend(asn_score.reasons)
            all_reasons.extend(profile_score.reasons)
            all_reasons.extend(device_score.reasons)
            
            return ViolationScore(
                total=min(raw_score, 100.0),
                breakdown={
                    'temporal': temporal_score,
                    'geo': geo_score,
                    'asn': asn_score,
                    'profile': profile_score,
                    'device': device_score,
                },
                recommended_action=recommended_action,
                confidence=confidence,
                reasons=all_reasons
            )
            
        except Exception as e:
            logger.error(
                "Error checking user violations for %s: %s",
                user_uuid,
                e,
                exc_info=True
            )
            return None
    
    def _get_action(self, score: float) -> ViolationAction:
        """Определить рекомендуемое действие на основе скора."""
        if score < self.THRESHOLDS['no_action']:
            return ViolationAction.NO_ACTION
        elif score < self.THRESHOLDS['monitor']:
            return ViolationAction.MONITOR
        elif score < self.THRESHOLDS['warn']:
            return ViolationAction.WARN
        elif score < self.THRESHOLDS['soft_block']:
            return ViolationAction.SOFT_BLOCK
        elif score < self.THRESHOLDS['temp_block']:
            return ViolationAction.TEMP_BLOCK
        else:
            return ViolationAction.HARD_BLOCK
