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
    UserAgentScore, ViolationScore,
)
from shared.connection_monitor import ConnectionMonitor, ActiveConnection, ConnectionStats
from shared.logger import logger
from shared.geoip import GeoIPService, IPMetadata, get_geoip_service

class GeoAnalyzer:
    """
    Анализ географического распределения IP.

    Правила:
    - Все IP из одного города = 0
    - IP из одной агломерации (пригороды) = 0 (нормально)
    - IP из разных городов одной страны (далеко) = +5
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

    # Маппинг русских названий городов в английские (канонические)
    # Используется для нормализации: GeoIP API возвращает английские названия,
    # а локальная база ASN — русские. Без маппинга "Moscow" и "Москва" считаются разными городами.
    CITY_NAME_ALIASES = {
        'москва': 'moscow',
        'санкт-петербург': 'saint petersburg',
        'петербург': 'saint petersburg',
        'спб': 'saint petersburg',
        'новосибирск': 'novosibirsk',
        'екатеринбург': 'yekaterinburg',
        'казань': 'kazan',
        'нижний новгород': 'nizhny novgorod',
        'челябинск': 'chelyabinsk',
        'самара': 'samara',
        'омск': 'omsk',
        'ростов-на-дону': 'rostov-on-don',
        'уфа': 'ufa',
        'красноярск': 'krasnoyarsk',
        'воронеж': 'voronezh',
        'пермь': 'perm',
        'волгоград': 'volgograd',
        'краснодар': 'krasnodar',
        'саратов': 'saratov',
        'тюмень': 'tyumen',
        'тольятти': 'tolyatti',
        'ижевск': 'izhevsk',
        'барнаул': 'barnaul',
        'ульяновск': 'ulyanovsk',
        'иркутск': 'irkutsk',
        'хабаровск': 'khabarovsk',
        'ярославль': 'yaroslavl',
        'владивосток': 'vladivostok',
        'махачкала': 'makhachkala',
        'томск': 'tomsk',
        'оренбург': 'orenburg',
        'кемерово': 'kemerovo',
        'новокузнецк': 'novokuznetsk',
        'рязань': 'ryazan',
        'астрахань': 'astrakhan',
        'набережные челны': 'naberezhnye chelny',
        'пенза': 'penza',
        'липецк': 'lipetsk',
        'тула': 'tula',
        'киров': 'kirov',
        'чебоксары': 'cheboksary',
        'калининград': 'kaliningrad',
        'курск': 'kursk',
        'ставрополь': 'stavropol',
        'сочи': 'sochi',
        'тверь': 'tver',
        'брянск': 'bryansk',
        'иваново': 'ivanovo',
        'белгород': 'belgorod',
        'сургут': 'surgut',
        'владимир': 'vladimir',
        'архангельск': 'arkhangelsk',
        'чита': 'chita',
        'калуга': 'kaluga',
        'смоленск': 'smolensk',
        'вологда': 'vologda',
        'орёл': 'oryol',
        'орел': 'oryol',
        'мурманск': 'murmansk',
        'химки': 'khimki',
        'мытищи': 'mytishchi',
        'балашиха': 'balashikha',
        'подольск': 'podolsk',
        'королёв': 'korolev',
        'королев': 'korolev',
        'люберцы': 'lyubertsy',
        'красногорск': 'krasnogorsk',
        'одинцово': 'odintsovo',
        'домодедово': 'domodedovo',
        'зеленоград': 'zelenograd',
    }

    # Агломерации и пригороды - города, которые считаются одной локацией
    # Ключ - название агломерации, значение - список городов (включая центр)
    # Содержит как английские, так и русские названия для корректного сравнения
    METROPOLITAN_AREAS = {
        # Свердловская область
        'yekaterinburg': [
            'yekaterinburg', 'ekaterinburg', 'sredneuralsk', 'verkhnyaya pyshma',
            'aramil', 'berezovsky', 'pervouralsk', 'revda', 'polevskoy',
            'verkhniaya pyshma', 'koltsovo', 'sysert'
        ],
        # Московская область
        'moscow': [
            'moscow', 'moskva', 'zelenograd', 'khimki', 'mytishchi', 'korolev',
            'lyubertsy', 'krasnogorsk', 'balashikha', 'podolsk', 'odintsovo',
            'shchyolkovo', 'dolgoprudny', 'reutov', 'lobnya', 'zhukovsky',
            'elektrostal', 'pushkino', 'sergiev posad', 'noginsk', 'orekhovo-zuyevo',
            'fryazino', 'ivanteevka', 'vidnoye', 'domodedovo', 'vnukovo'
        ],
        # Санкт-Петербург
        'saint_petersburg': [
            'saint petersburg', 'st. petersburg', 'st petersburg', 'petersburg',
            'sankt-peterburg', 'pushkin', 'kolpino', 'petrodvorets', 'lomonosov',
            'zelenogorsk', 'sestroretsk', 'kronstadt', 'gatchina', 'vsevolozhsk',
            'tosno', 'kirishi', 'kirovsk', 'murino', 'kudrovo'
        ],
        # Казань
        'kazan': [
            'kazan', 'vysokaya gora', 'zelenodolsk', 'laishevo', 'pestretsy'
        ],
        # Новосибирск
        'novosibirsk': [
            'novosibirsk', 'berdsk', 'akademgorodok', 'ob', 'koltsovo'
        ],
        # Нижний Новгород
        'nizhny_novgorod': [
            'nizhny novgorod', 'nizhnij novgorod', 'bor', 'dzerzhinsk', 'kstovo'
        ],
        # Самара
        'samara': [
            'samara', 'togliatti', 'tolyatti', 'syzran', 'novokuybyshevsk', 'chapayevsk'
        ],
        # Ростов-на-Дону
        'rostov': [
            'rostov-on-don', 'rostov-na-donu', 'bataysk', 'aksay', 'novocherkassk', 'taganrog'
        ],
        # Красноярск
        'krasnoyarsk': [
            'krasnoyarsk', 'divnogorsk', 'sosnovoborsk', 'zheleznogorsk'
        ],
        # Челябинск
        'chelyabinsk': [
            'chelyabinsk', 'kopeysk', 'kopeisk', 'zlatoust', 'miass'
        ],
        # Уфа
        'ufa': [
            'ufa', 'sterlitamak', 'salavat', 'neftekamsk'
        ],
        # Пермь
        'perm': [
            'perm', 'krasnokamsk', 'chusovoy', 'lysva', 'berezniki'
        ],
        # Волгоград
        'volgograd': [
            'volgograd', 'volzhsky', 'volzhskiy', 'kamyshin'
        ],
        # Воронеж
        'voronezh': [
            'voronezh', 'novovoronezh', 'semiluki'
        ],
        # Краснодар
        'krasnodar': [
            'krasnodar', 'goryachy klyuch', 'dinskaya', 'korenovsk'
        ],
        # Сочи
        'sochi': [
            'sochi', 'adler', 'lazarevskoye', 'krasnaya polyana', 'dagomys', 'khosta'
        ],
    }

    # Минимальное расстояние (км), при котором города считаются "далеко" друг от друга (по умолчанию)
    MIN_DISTANCE_FOR_DIFFERENT_CITIES_DEFAULT = 50

    def __init__(self, geoip_service: Optional[GeoIPService] = None):
        """
        Инициализирует GeoAnalyzer.

        Args:
            geoip_service: Сервис для получения геолокации (по умолчанию используется глобальный)
        """
        self.geoip = geoip_service or get_geoip_service()
        # Строим обратный индекс: город -> агломерация
        self._city_to_metro: Dict[str, str] = {}
        for metro_name, cities in self.METROPOLITAN_AREAS.items():
            for city in cities:
                self._city_to_metro[city.lower()] = metro_name

    def _normalize_city_name(self, city: str) -> str:
        """
        Нормализует название города для сравнения.

        Приводит к нижнему регистру, убирает лишние символы,
        переводит русские названия в английские через маппинг алиасов.
        """
        if not city:
            return ""
        # Приводим к нижнему регистру и убираем лишние пробелы
        normalized = city.lower().strip()
        # Убираем распространённые суффиксы
        for suffix in [' city', ' gorod', ' oblast', ' region']:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
        # Переводим русские названия в английские через маппинг алиасов
        if normalized in self.CITY_NAME_ALIASES:
            normalized = self.CITY_NAME_ALIASES[normalized]
        return normalized

    def _get_metro_area(self, city: str) -> Optional[str]:
        """
        Возвращает название агломерации для города или None, если город не в агломерации.
        """
        if not city:
            return None
        normalized = self._normalize_city_name(city)
        return self._city_to_metro.get(normalized)

    def _are_cities_in_same_metro(self, city1: str, city2: str) -> bool:
        """
        Проверяет, находятся ли два города в одной агломерации.

        Args:
            city1: Первый город
            city2: Второй город

        Returns:
            True если города в одной агломерации или это один и тот же город
        """
        if not city1 or not city2:
            return False

        normalized1 = self._normalize_city_name(city1)
        normalized2 = self._normalize_city_name(city2)

        # Если названия идентичны после нормализации
        if normalized1 == normalized2:
            return True

        # Проверяем агломерации
        metro1 = self._city_to_metro.get(normalized1)
        metro2 = self._city_to_metro.get(normalized2)

        # Если оба города в одной агломерации
        if metro1 and metro2 and metro1 == metro2:
            return True

        return False
    
    async def _get_ip_metadata(self, ip_address: str) -> Optional[IPMetadata]:
        """
        Получить метаданные IP адреса.
        
        Args:
            ip_address: IP адрес
        
        Returns:
            IPMetadata или None
        """
        return await self.geoip.lookup(ip_address)
    
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
    
    async def analyze(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]],
        ip_metadata_cache: Optional[Dict[str, 'IPMetadata']] = None,
    ) -> GeoScore:
        """
        Анализирует географическое распределение IP.

        Args:
            connections: Активные подключения
            connection_history: История подключений
            ip_metadata_cache: Предзагруженный кэш GeoIP данных (для оптимизации)

        Returns:
            GeoScore с оценкой и причинами
        """
        from shared.config_service import config_service
        score = 0.0
        reasons = []
        countries: Set[str] = set()
        cities: Set[str] = set()
        impossible_travel = False
        # Configurable city distance threshold
        min_city_distance = config_service.get("violations_geo_max_city_distance_km", self.MIN_DISTANCE_FOR_DIFFERENT_CITIES_DEFAULT)

        # Собираем уникальные IP из активных подключений и истории
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

        for ip, metadata in ip_metadata.items():
            # Debug: логируем данные для каждого IP
            logger.debug(
                "GeoIP for %s: country=%s, city=%s, region=%s, asn=%s (%s), connection_type=%s, coords=(%s, %s)",
                ip, metadata.country_code, metadata.city, metadata.region,
                metadata.asn, metadata.asn_org, metadata.connection_type,
                metadata.latitude, metadata.longitude
            )
            if metadata.country_code:
                countries.add(metadata.country_code)
            if metadata.city:
                # Нормализуем название города для корректного сравнения
                # (избегаем дубликатов вроде "Moscow" и "Москва")
                normalized_city = self._normalize_city_name(metadata.city)
                cities.add(normalized_city or metadata.city)
        
        # Если нет данных о геолокации, возвращаем нулевой скор
        # Не добавляем это в причины, так как отсутствие данных не является нарушением
        if not ip_metadata:
            return GeoScore(
                score=0.0,
                reasons=[],
                countries=countries,
                cities=cities,
                impossible_travel_detected=False
            )
        
        # Анализ одновременных подключений с разных стран
        active_countries = set()
        for conn in connections:
            ip = str(conn.ip_address)
            if ip in ip_metadata:
                country = ip_metadata[ip].country_code
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

            # Трекинг уже добавленных пар городов для дедупликации (A→B == B→A)
            seen_city_pairs: set = set()

            for i in range(1, len(sorted_history)):
                prev_conn = sorted_history[i - 1]
                curr_conn = sorted_history[i]
                
                prev_ip = str(prev_conn.get("ip_address", ""))
                curr_ip = str(curr_conn.get("ip_address", ""))
                
                if prev_ip not in ip_metadata or curr_ip not in ip_metadata:
                    continue
                
                prev_meta = ip_metadata[prev_ip]
                curr_meta = ip_metadata[curr_ip]
                
                prev_country = prev_meta.country_code or ""
                curr_country = curr_meta.country_code or ""
                prev_city = prev_meta.city or ""
                curr_city = curr_meta.city or ""
                prev_lat = prev_meta.latitude
                prev_lon = prev_meta.longitude
                curr_lat = curr_meta.latitude
                curr_lon = curr_meta.longitude
                
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
                            
                            # Проверяем реалистичность перемещения используя реальные координаты
                            if prev_lat and prev_lon and curr_lat and curr_lon:
                                distance_km = self._haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                                max_distance_km = self.TRAVEL_SPEEDS['international'] * time_diff_hours
                                
                                if distance_km > max_distance_km:
                                    score = max(score, 50.0)
                                    reasons.append(
                                        f"Нереалистичное перемещение: {prev_country} → {curr_country} "
                                        f"({distance_km:.0f} км за {time_diff_hours:.1f} ч, макс: {max_distance_km:.0f} км)"
                                    )
                                    impossible_travel = True
                                else:
                                    score = max(score, 15.0)
                                    reasons.append(f"Перемещение между странами: {prev_country} → {curr_country}")
                            else:
                                # Если нет координат, используем эвристику
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
                # Нормализуем названия перед сравнением (Moscow == Москва и т.д.)
                elif prev_country == curr_country and prev_city and curr_city and \
                        self._normalize_city_name(prev_city) != self._normalize_city_name(curr_city):
                    # Проверяем, находятся ли города в одной агломерации (пригороды)
                    # Если да, это нормальное поведение - не добавляем скор
                    if self._are_cities_in_same_metro(prev_city, curr_city):
                        # Города в одной агломерации - это нормально (пригороды, районы города)
                        # Не добавляем скор и не добавляем причину
                        pass
                    else:
                        # Дедупликация пар городов: A→B и B→A считаются одной парой
                        norm_prev = self._normalize_city_name(prev_city)
                        norm_curr = self._normalize_city_name(curr_city)
                        city_pair = frozenset((norm_prev, norm_curr))
                        if city_pair in seen_city_pairs:
                            continue
                        seen_city_pairs.add(city_pair)

                        # Города в разных регионах - проверяем расстояние
                        # Если есть координаты, проверяем реальное расстояние
                        if prev_lat and prev_lon and curr_lat and curr_lon:
                            distance_km = self._haversine_distance(prev_lat, prev_lon, curr_lat, curr_lon)
                            # Градуированная оценка по расстоянию:
                            # < 50 км: 0 (очень близко, вероятно погрешность GeoIP или пригород)
                            # 50-100 км: 2 (умеренно близко)
                            # > 100 км: 5 (разные регионы)
                            if distance_km <= 50:
                                # Очень близко - игнорируем (возможно погрешность GeoIP)
                                pass
                            elif distance_km <= min_city_distance:
                                # Умеренно близко - минимальный скор
                                score = max(score, 2.0)
                                reasons.append(f"Близкие города: {prev_city} → {curr_city} ({distance_km:.0f} км)")
                            else:
                                # Далеко - стандартный скор
                                score = max(score, 5.0)
                                reasons.append(f"Разные города одной страны: {prev_city} → {curr_city} ({distance_km:.0f} км)")
                        else:
                            # Нет координат - добавляем минимальный скор на всякий случай
                            score = max(score, 3.0)
                            reasons.append(f"Разные города одной страны: {prev_city} → {curr_city}")
        
        return GeoScore(
            score=min(score, 100.0),
            reasons=reasons,
            countries=countries,
            cities=cities,
            impossible_travel_detected=impossible_travel
        )


