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
from shared.database import DatabaseService

class UserProfileAnalyzer:
    """
    Анализ отклонений от исторического профиля пользователя.
    
    Строит baseline на основе истории подключений и сравнивает текущее поведение.
    """
    
    _BASELINE_CACHE_TTL = 21600  # 6 hours
    _BASELINE_CACHE_MAX_SIZE = 25000

    def __init__(self, db_service: DatabaseService, geoip_service=None):
        """
        Инициализирует UserProfileAnalyzer.

        Args:
            db_service: Сервис для работы с БД
            geoip_service: GeoIP для резолва гео-baseline по known_ips (опционально)
        """
        self.db = db_service
        self.geoip = geoip_service
        self._baseline_cache: Dict[str, tuple] = {}  # {user_uuid: (baseline_dict, timestamp)}
        self._baseline_lock = asyncio.Lock()  # single lock for baseline builds (prevents stampede)
    
    async def build_baseline(self, user_uuid: str, days: int = 30, connection_history: Optional[List] = None) -> Dict[str, Any]:
        """
        Строит baseline профиль пользователя на основе истории.
        Сначала проверяет materialized baseline в БД, затем вычисляет и сохраняет.

        Args:
            user_uuid: UUID пользователя
            days: Количество дней истории для анализа
            connection_history: Опциональная предзагруженная история подключений

        Returns:
            Словарь с baseline данными
        """
        try:
            # Try materialized baseline from DB first (survives restarts)
            db_baseline = await self.db.get_user_baseline(user_uuid, max_age_seconds=self._BASELINE_CACHE_TTL)
            if db_baseline and db_baseline.get('data_points', 0) > 0:
                return db_baseline
            history = connection_history if connection_history is not None else await self.db.get_connection_history(user_uuid, days=days)
            
            if not history:
                return {
                    'typical_countries': [],
                    'typical_cities': [],
                    'typical_regions': [],
                    'typical_asns': [],
                    'known_ips': [],
                    'avg_daily_unique_ips': 0.0,
                    'max_daily_unique_ips': 0,
                    'typical_hours': [],
                    'avg_session_duration_minutes': 0,
                    'data_points': 0
                }
            
            # Группируем по дням
            daily_ips: Dict[str, Set[str]] = defaultdict(set)
            all_known_ips: Set[str] = set()  # Все IP, которые пользователь использовал
            countries: Set[str] = set()
            cities: Set[str] = set()
            regions: Set[str] = set()  # Регионы (области)
            asns: Set[str] = set()
            hours: List[int] = []
            session_durations: List[float] = []

            for conn in history:
                ip = str(conn.get("ip_address", ""))
                connected_at = conn.get("connected_at")
                disconnected_at = conn.get("disconnected_at")

                # Собираем известные IP
                if ip:
                    all_known_ips.add(ip)

                # Собираем гео-данные если есть в истории
                country = conn.get("country") or conn.get("country_code")
                city = conn.get("city")
                region = conn.get("region")
                asn = conn.get("asn") or conn.get("asn_org")

                if country:
                    countries.add(str(country))
                if city:
                    cities.add(str(city))
                if region:
                    regions.add(str(region))
                if asn:
                    asns.add(str(asn))

                if connected_at:
                    if isinstance(connected_at, str):
                        try:
                            connected_at = datetime.fromisoformat(connected_at.replace('Z', '+00:00'))
                        except ValueError:
                            continue

                    if isinstance(connected_at, datetime):
                        day_key = connected_at.strftime('%Y-%m-%d')
                        daily_ips[day_key].add(ip)

                        hour = connected_at.hour
                        hours.append(hour)

                        # Вычисляем длительность сессии
                        if disconnected_at:
                            if isinstance(disconnected_at, str):
                                try:
                                    disconnected_at = datetime.fromisoformat(disconnected_at.replace('Z', '+00:00'))
                                except ValueError:
                                    disconnected_at = None

                            if isinstance(disconnected_at, datetime):
                                duration_minutes = (disconnected_at - connected_at).total_seconds() / 60
                                if duration_minutes > 0:
                                    session_durations.append(duration_minutes)
            
            # Гео-baseline: история подключений не содержит country/asn (только ip), поэтому
            # резолвим типичные страны/ASN по known_ips через GeoIP — оживляет детект «новой
            # страны» в analyze() (без этого typical_countries всегда пуст и проверка мертва).
            if self.geoip and all_known_ips and not countries:
                try:
                    geo_meta = await self.geoip.lookup_batch(list(all_known_ips)[:200])
                    for _m in geo_meta.values():
                        if getattr(_m, "country_code", None):
                            countries.add(_m.country_code)
                        if getattr(_m, "asn_org", None):
                            asns.add(_m.asn_org)
                except Exception:
                    pass

            # Вычисляем средние значения
            daily_unique_ips = [len(ips) for ips in daily_ips.values()]
            avg_daily_unique_ips = sum(daily_unique_ips) / len(daily_unique_ips) if daily_unique_ips else 0.0
            max_daily_unique_ips = max(daily_unique_ips) if daily_unique_ips else 0
            
            # Типичные часы (часы с наибольшей активностью)
            from collections import Counter
            hour_counts = Counter(hours)
            typical_hours = [hour for hour, _ in hour_counts.most_common(8)]  # Топ-8 часов
            
            avg_session_duration = sum(session_durations) / len(session_durations) if session_durations else 0

            result = {
                'typical_countries': list(countries),
                'typical_cities': list(cities),
                'typical_regions': list(regions),
                'typical_asns': list(asns),
                'known_ips': list(all_known_ips),
                'avg_daily_unique_ips': avg_daily_unique_ips,
                'max_daily_unique_ips': max_daily_unique_ips,
                'typical_hours': typical_hours,
                'avg_session_duration_minutes': avg_session_duration,
                'data_points': len(daily_ips)
            }

            # Cache the baseline (in-memory + DB)
            if len(self._baseline_cache) >= self._BASELINE_CACHE_MAX_SIZE:
                sorted_keys = sorted(self._baseline_cache, key=lambda k: self._baseline_cache[k][1])
                for k in sorted_keys[:len(sorted_keys) // 5]:
                    self._baseline_cache.pop(k, None)
            self._baseline_cache[user_uuid] = (result, time.time())

            # Persist to DB (fire-and-forget, non-blocking)
            try:
                await self.db.save_user_baseline(user_uuid, result)
            except Exception:
                pass  # DB save is best-effort

            return result

        except Exception as e:
            logger.error("Error building baseline for user %s: %s", user_uuid, e, exc_info=True)
            return {
                'typical_countries': [],
                'typical_cities': [],
                'typical_regions': [],
                'typical_asns': [],
                'known_ips': [],
                'avg_daily_unique_ips': 0.0,
                'max_daily_unique_ips': 0,
                'typical_hours': [],
                'avg_session_duration_minutes': 0,
                'data_points': 0
            }
    
    async def analyze(
        self,
        user_uuid: str,
        current_ips: Set[str],
        current_countries: Set[str],
        baseline: Optional[Dict[str, Any]] = None,
        connection_history_30d: Optional[List] = None,
    ) -> ProfileScore:
        """
        Анализирует отклонения от baseline профиля.
        
        Args:
            user_uuid: UUID пользователя
            current_ips: Текущие уникальные IP
            current_countries: Текущие страны
            baseline: Baseline профиль (если None, будет построен автоматически)
        
        Returns:
            ProfileScore с оценкой и причинами
        """
        score = 0.0
        reasons = []
        deviation = 0.0
        
        if baseline is None:
            cached = self._baseline_cache.get(user_uuid)
            if cached:
                cached_baseline, cached_ts = cached
                if (time.time() - cached_ts) < self._BASELINE_CACHE_TTL:
                    baseline = cached_baseline

            if baseline is None:
                db_baseline = await self.db.get_user_baseline(user_uuid, max_age_seconds=self._BASELINE_CACHE_TTL)
                if db_baseline and db_baseline.get('data_points', 0) > 0:
                    baseline = db_baseline
                    self._baseline_cache[user_uuid] = (baseline, time.time())

            if baseline is None and connection_history_30d:
                baseline = await self.build_baseline(user_uuid, days=30, connection_history=connection_history_30d)

            if baseline is None:
                return ProfileScore(score=0.0, reasons=[], deviation_from_baseline=0.0)
        
        # Проверяем, сколько текущих IP уже известны пользователю
        known_ips = set(baseline.get('known_ips', []))
        known_ratio = 0.0
        if current_ips and known_ips:
            known_current_ips = current_ips & known_ips
            known_ratio = len(known_current_ips) / len(current_ips) if current_ips else 0

            # Если все или большинство IP известны, это очень хороший знак
            if known_ratio >= 0.8:
                # Почти все IP известны - минимальный скор
                # Это означает, что пользователь использует те же IP, что и раньше
                return ProfileScore(
                    score=0.0,
                    reasons=[],
                    deviation_from_baseline=0.0
                )
            elif known_ratio >= 0.5:
                # Половина IP известны - снижаем потенциальный скор
                # Будем применять модификатор 0.5 к итоговому скору
                pass  # Продолжаем анализ, но учтём это позже

        # Сравниваем количество уникальных IP
        current_unique_ips = len(current_ips)
        avg_daily_ips = baseline['avg_daily_unique_ips']
        max_daily_ips = baseline['max_daily_unique_ips']

        if avg_daily_ips > 0:
            deviation_ratio = current_unique_ips / avg_daily_ips

            if deviation_ratio > 2.0:
                score = 45.0
                reasons.append(f"Аномалия: обычно {avg_daily_ips:.1f} IP/день, сейчас {current_unique_ips}")
                deviation = deviation_ratio
            elif deviation_ratio > 1.5:
                score = 30.0
                reasons.append(f"Отклонение: обычно {avg_daily_ips:.1f} IP/день, сейчас {current_unique_ips}")
                deviation = deviation_ratio
            elif current_unique_ips > max_daily_ips:
                score = 15.0
                reasons.append(f"Превышен максимум: обычно макс {max_daily_ips} IP/день, сейчас {current_unique_ips}")
                deviation = current_unique_ips / max_daily_ips if max_daily_ips > 0 else 0

        # Проверяем новые страны (только если baseline содержит страны)
        typical_countries = set(baseline.get('typical_countries', []))
        if typical_countries:  # Только если есть данные о типичных странах
            new_countries = current_countries - typical_countries
            if new_countries:
                score += 20.0
                reasons.append(f"Новая страна (первый раз): {', '.join(new_countries)}")

        # Проверяем подключение в нетипичное время
        typical_hours = set(baseline.get('typical_hours', []))
        if typical_hours and len(typical_hours) >= 3:  # Нужен минимум данных
            current_hour = datetime.utcnow().hour
            if current_hour not in typical_hours:
                score += 10.0
                reasons.append(f"Подключение в нетипичное время ({current_hour}:00 UTC, обычно: {sorted(typical_hours)[:6]})")

        # Если половина IP известны, снижаем скор (known_ratio уже вычислен выше)
        if current_ips and known_ips and known_ratio >= 0.5:
            score *= 0.5  # Снижаем на 50% если половина IP известны

        return ProfileScore(
            score=min(score, 100.0),
            reasons=reasons,
            deviation_from_baseline=deviation
        )


