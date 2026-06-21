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
from shared.geoip import GeoIPService, IPMetadata, get_geoip_service
from shared.analyzers.temporal import TemporalAnalyzer
from shared.analyzers.geo import GeoAnalyzer
from shared.analyzers.asn import ASNAnalyzer
from shared.analyzers.profile import UserProfileAnalyzer
from shared.analyzers.device import DeviceFingerprintAnalyzer
from shared.analyzers.hwid import HwidCrossAccountAnalyzer
from shared.analyzers.user_agent import UserAgentAnalyzer


# Веса факторов (module-level for access from _validate_weights)
WEIGHTS = {
    'temporal': 0.20,      # Временной паттерн (было 0.25)
    'geo': 0.20,           # География (было 0.25)
    'asn': 0.10,           # Тип провайдера (было 0.15)
    'profile': 0.15,       # Отклонение от профиля (было 0.20)
    'device': 0.10,        # ⚠️ ФИКТИВЕН: коллектор не пишет per-connection User-Agent
                           # (node-agent парсит Xray access.log — там только IP+email),
                           # поэтому device-score всегда 0. Вес сохранён на случай источника UA.
    'hwid': 0.25,          # Кросс-аккаунт HWID (сильный сигнал)
}

def _validate_weights(weights):
    """Проверяет, что сумма весов равна 1.0."""
    total = sum(weights.values())
    if abs(total - 1.0) > 0.001:
        raise ValueError(
            f"Веса факторов должны суммироваться в 1.0, но их сумма равна {total}. "
            f"Веса: {weights}"
        )

_validate_weights(WEIGHTS)


class IntelligentViolationDetector:
    """
    Система многофакторного анализа для детектирования нарушений.

    Объединяет результаты всех анализаторов и вычисляет итоговый скор нарушения.
    """

    WEIGHTS = WEIGHTS
    
    # Пороги для действий
    THRESHOLDS = {
        'no_action': 30,       # < 30: ничего не делаем
        'monitor': 50,         # 30-50: усиленный мониторинг
        'warn': 65,            # 50-65: предупреждение пользователю
        'soft_block': 80,      # 65-80: мягкая блокировка (ограничение скорости)
        'temp_block': 90,      # 80-90: временная блокировка
        'hard_block': 95,      # > 95: блокировка + ручная проверка
    }
    
    def __init__(self, db_service: DatabaseService, connection_monitor: ConnectionMonitor, geoip_service: Optional[GeoIPService] = None):
        """
        Инициализирует IntelligentViolationDetector.
        
        Args:
            db_service: Сервис для работы с БД
            connection_monitor: Сервис для мониторинга подключений
            geoip_service: Сервис для получения геолокации (по умолчанию используется глобальный)
        """
        self.db = db_service
        self.connection_monitor = connection_monitor
        geoip = geoip_service or get_geoip_service()
        self.temporal_analyzer = TemporalAnalyzer()
        self.geo_analyzer = GeoAnalyzer(geoip_service=geoip)
        self.asn_analyzer = ASNAnalyzer(geoip_service=geoip)
        self.profile_analyzer = UserProfileAnalyzer(db_service, geoip_service=geoip)
        self.device_analyzer = DeviceFingerprintAnalyzer()
        self.hwid_analyzer = HwidCrossAccountAnalyzer(db_service)
        self.user_agent_analyzer = UserAgentAnalyzer()
        # Per-user SRH кэш: {user_uuid: (fetched_at, records)}
        self._srh_cache: Dict[str, tuple] = {}
        self._srh_cache_ttl_seconds = 300  # 5 минут
    
    async def check_user(
        self,
        user_uuid: str,
        window_minutes: int = 60,
        excluded_analyzers: Optional[List[str]] = None,
        *,
        prefetched_device_count: Optional[int] = None,
        prefetched_active_connections: Optional[List['ActiveConnection']] = None,
        prefetched_history_30d: Optional[List[Dict[str, Any]]] = None,
        prefetched_baseline: Optional[Dict[str, Any]] = None,
        prefetched_shared_hwids: Optional[List[Dict[str, Any]]] = None,
        prefetched_srh_records: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[ViolationScore]:
        """
        Проверить пользователя на нарушения.

        Args:
            user_uuid: UUID пользователя
            window_minutes: Временное окно для анализа (по умолчанию 60 минут)
            excluded_analyzers: Список анализаторов для пропуска (per-user exclusions)
            prefetched_*: Предзагруженные данные из batch-запросов (bypass per-user DB queries)

        Returns:
            ViolationScore или None при ошибке
        """
        if not self.db.is_connected:
            logger.warning("Database not connected, cannot check user violations")
            return None

        # Проверка глобального включения через конфиг
        from shared.config_service import config_service
        if not config_service.get("violations_enabled", True):
            logger.debug("Violation detection disabled via config, skipping user %s", user_uuid)
            return None

        try:
            user_device_count = prefetched_device_count if prefetched_device_count is not None else await self.db.get_user_devices_count(user_uuid)

            if prefetched_active_connections is not None:
                active_connections = prefetched_active_connections
            else:
                active_connections = await self.connection_monitor.get_user_active_connections(user_uuid, max_age_minutes=5)

            connection_history_30d = prefetched_history_30d if prefetched_history_30d is not None else await self.db.get_connection_history(user_uuid, days=30)

            # Нарезаем 7-дневную историю для анализаторов temporal/geo/asn/device
            history_days = max(1, min(7, window_minutes // 60 + 1))
            if history_days < 30 and connection_history_30d:
                from datetime import datetime, timedelta, timezone
                cutoff = datetime.now(timezone.utc) - timedelta(days=history_days)
                connection_history = [
                    c for c in connection_history_30d
                    if (ca := c.get("connected_at")) and (
                        ca >= cutoff if isinstance(ca, datetime) else True
                    )
                ]
            else:
                connection_history = connection_history_30d

            # Добавляем debug-логирование для диагностики
            logger.debug(
                "Violation check for user %s: device_count=%d, active_connections=%d, history_records=%d",
                user_uuid, user_device_count, len(active_connections), len(connection_history)
            )
            for i, conn in enumerate(active_connections):
                logger.debug(
                    "  Active connection %d: ip=%s, connected_at=%s",
                    i + 1, conn.ip_address, conn.connected_at
                )

            # Единый GeoIP batch lookup для всех анализаторов (оптимизация)
            all_ips_for_geo = set()
            for conn in active_connections:
                all_ips_for_geo.add(str(conn.ip_address))
            for conn in connection_history:
                ip = str(conn.get("ip_address", ""))
                if ip:
                    all_ips_for_geo.add(ip)

            ip_metadata_cache = {}
            if all_ips_for_geo:
                try:
                    ip_metadata_cache = await self.geo_analyzer.geoip.lookup_batch(list(all_ips_for_geo))
                except Exception as geo_err:
                    logger.warning("Failed pre-fetching GeoIP data for %d IPs: %s", len(all_ips_for_geo), geo_err)

            # Determine if user is on a mobile carrier (for CGNAT buffer)
            _has_mobile = any(
                ip_metadata_cache.get(str(c.ip_address), None) and
                getattr(ip_metadata_cache[str(c.ip_address)], 'connection_type', '') in ('mobile', 'mobile_isp')
                for c in active_connections
            ) if ip_metadata_cache else False

            temporal_score = self.temporal_analyzer.analyze(active_connections, connection_history, user_device_count, is_mobile=_has_mobile)

            # Анализируем геолокацию (используем общий кэш)
            geo_score = await self.geo_analyzer.analyze(active_connections, connection_history, ip_metadata_cache)

            # Debug-логирование гео-данных для диагностики проблем с городами
            logger.debug(
                "Geo analysis for user %s: countries=%s, cities=%s, score=%.1f",
                user_uuid, geo_score.countries, geo_score.cities, geo_score.score
            )
            if geo_score.reasons:
                for reason in geo_score.reasons:
                    logger.debug("  Geo reason: %s", reason)

            # Анализируем тип провайдера (ASN) (используем общий кэш)
            asn_score = await self.asn_analyzer.analyze(active_connections, connection_history, ip_metadata_cache)
            
            # Анализируем отклонения от профиля (async)
            current_ips = {str(conn.ip_address) for conn in active_connections}
            current_countries = geo_score.countries
            profile_score = await self.profile_analyzer.analyze(
                user_uuid, current_ips, current_countries,
                baseline=prefetched_baseline,
                connection_history_30d=connection_history_30d,
            )

            # Анализируем fingerprint устройств (с учётом лимита устройств)
            device_score = self.device_analyzer.analyze(active_connections, connection_history, user_device_count)

            # Анализируем кросс-аккаунт HWID
            hwid_score = await self.hwid_analyzer.analyze(user_uuid, prefetched_shared=prefetched_shared_hwids)

            # Анализируем User-Agent подписочных запросов через Panel SRH (детекция двойных туннелей и скриптов)
            ua_score = UserAgentScore(score=0.0, reasons=[])
            if config_service.get("violations_analyzer_user_agent", True) and "user_agent" not in (excluded_analyzers or []):
                try:
                    srh_records = prefetched_srh_records if prefetched_srh_records is not None else await self._fetch_srh_records(user_uuid)
                    if srh_records is not None:
                        ua_whitelist_extra = config_service.get("violation_ua_whitelist_extra", []) or []
                        ua_blacklist_extra = config_service.get("violation_ua_blacklist_extra", []) or []
                        self.user_agent_analyzer.set_extra_patterns(ua_whitelist_extra, ua_blacklist_extra)
                        max_age = int(config_service.get("violation_ua_max_age_days", 0) or 0)
                        ua_score = self.user_agent_analyzer.analyze(srh_records, max_age_days=max_age)
                except Exception as ua_err:
                    logger.warning("UserAgent analysis failed for %s: %s", user_uuid, ua_err)

            # Обнуляем скоры отключённых анализаторов (глобально через конфиг + per-user exclusions)
            _excluded = set(excluded_analyzers) if excluded_analyzers else set()

            if not config_service.get("violations_analyzer_temporal", True) or "temporal" in _excluded:
                temporal_score = TemporalScore(score=0.0, reasons=[])
            if not config_service.get("violations_analyzer_geo", True) or "geo" in _excluded:
                geo_score = GeoScore(score=0.0, reasons=[], countries=set(), cities=set())
            if not config_service.get("violations_analyzer_asn", True) or "asn" in _excluded:
                asn_score = ASNScore(score=0.0, reasons=[], asn_types=set())
            if not config_service.get("violations_analyzer_profile", True) or "profile" in _excluded:
                profile_score = ProfileScore(score=0.0, reasons=[])
            if not config_service.get("violations_analyzer_device", True) or "device" in _excluded:
                device_score = DeviceScore(score=0.0, reasons=[], unique_fingerprints_count=0, different_os_count=0)
            if not config_service.get("violations_analyzer_hwid", True) or "hwid" in _excluded:
                hwid_score = HwidScore(score=0.0, reasons=[])

            # Вычисляем взвешенный скор
            raw_score = (
                temporal_score.score * self.WEIGHTS['temporal'] +
                geo_score.score * self.WEIGHTS['geo'] +
                asn_score.score * self.WEIGHTS['asn'] +
                profile_score.score * self.WEIGHTS['profile'] +
                device_score.score * self.WEIGHTS['device'] +
                hwid_score.score * self.WEIGHTS['hwid']
            )
            
            # Применяем модификаторы на основе типов провайдеров
            # Используем средний модификатор для всех типов провайдеров в подключениях
            if asn_score.asn_types:
                modifiers = []
                for provider_type in asn_score.asn_types:
                    modifier = self.asn_analyzer.PROVIDER_TYPE_MODIFIERS.get(
                        provider_type,
                        self.asn_analyzer.PROVIDER_TYPE_MODIFIERS['unknown']
                    )
                    modifiers.append(modifier)
                
                # Используем средний модификатор (взвешенный по количеству подключений)
                avg_modifier = sum(modifiers) / len(modifiers) if modifiers else 1.0
                score_before_modifier = raw_score
                raw_score *= avg_modifier
                
                logger.debug(
                    "Applied ASN modifier %.2f for provider types: %s (score: %.2f -> %.2f)",
                    avg_modifier, ', '.join(asn_score.asn_types), score_before_modifier, raw_score
                )
            else:
                # Fallback для обратной совместимости
                if asn_score.is_mobile_carrier:
                    raw_score *= 0.5  # Снижаем для мобильных операторов
                elif asn_score.is_datacenter:
                    raw_score *= 1.5  # Повышаем для датацентров
                elif asn_score.is_vpn:
                    raw_score *= 1.8  # Сильно повышаем для VPN
            
            # Детекция паттерна переключения сетей (Mobile <-> WiFi)
            # Если обнаружен такой паттерн, значительно снижаем скор,
            # т.к. это нормальное поведение пользователя
            is_network_switch = self._detect_network_switch_pattern(asn_score.asn_types)
            if is_network_switch:
                # Применяем снижение только если количество IP правдоподобно для переключения сети
                sim_count = temporal_score.simultaneous_connections_count if hasattr(temporal_score, 'simultaneous_connections_count') else 0
                if sim_count <= user_device_count + 2:
                    score_before_switch = raw_score
                    raw_score *= 0.5
                    logger.debug(
                        "Network switch pattern detected, IPs (%d) within device limit + buffer (%d+2), reducing: %.2f -> %.2f",
                        sim_count, user_device_count, score_before_switch, raw_score
                    )
                else:
                    logger.debug(
                        "Network switch pattern detected but IPs (%d) exceed device limit + buffer (%d+2), NOT reducing score",
                        sim_count, user_device_count,
                    )

            # Проверяем, от одного ли провайдера (ASN) все IP
            # Если да, это снижает вероятность шаринга
            is_same_asn, asn_ratio = await self._check_same_asn_pattern(active_connections, connection_history, ip_metadata_cache)
            if is_same_asn and asn_ratio >= 0.8:
                # Все IP от одного провайдера - снижаем скор
                score_before_asn = raw_score
                raw_score *= 0.7  # 30% снижение
                logger.debug(
                    "Same ASN pattern detected (%.0f%% from same provider), reducing score: %.2f -> %.2f",
                    asn_ratio * 100, score_before_asn, raw_score
                )

            # --- Дополнительные проверки для снижения ложных срабатываний ---

            # Проверка 1: Близость подсетей (CGNAT/NAT)
            # IP в одной /24 подсети — почти наверняка один NAT, не шаринг
            is_same_subnet, subnet_modifier = self._check_subnet_proximity(
                active_connections, connection_history
            )
            if is_same_subnet:
                score_before_subnet = raw_score
                raw_score *= subnet_modifier
                logger.debug(
                    "Subnet proximity detected (modifier=%.2f), reducing score: %.2f -> %.2f",
                    subnet_modifier, score_before_subnet, raw_score
                )

            # Проверка 2: Повторяемость нарушений
            # Одиночное срабатывание может быть случайным, повторяющиеся — паттерн
            consistency_modifier = await self._check_violation_consistency(user_uuid)
            if consistency_modifier < 1.0:
                score_before_consistency = raw_score
                raw_score *= consistency_modifier
                logger.debug(
                    "Violation consistency modifier=%.2f, reducing score: %.2f -> %.2f",
                    consistency_modifier, score_before_consistency, raw_score
                )

            # Проверка 3: Известные пары IP
            # Пары IP, которые пользователь регулярно использует (дом+работа) — не шаринг
            known_pairs_modifier = await self._check_known_ip_pairs(user_uuid, current_ips, connection_history_30d=connection_history_30d)
            if known_pairs_modifier < 1.0:
                score_before_pairs = raw_score
                raw_score *= known_pairs_modifier
                logger.debug(
                    "Known IP pairs modifier=%.2f, reducing score: %.2f -> %.2f",
                    known_pairs_modifier, score_before_pairs, raw_score
                )

            # Strong-signal bypass: один мощный одиночный сигнал (>=85) не должен полностью
            # гаситься consistency/dampening на ПЕРВОМ срабатывании. Иначе явный шаринг
            # (impossible-travel гео, кросс-аккаунт HWID, ссылка-в-UA) не доходит до порога
            # нарушения — это и есть причина, по которой детектор почти не создаёт нарушений
            # через взвешенный путь (consistency ×0.3 на первом срабатывании съедает всё, а
            # чтобы consistency стал 1.0, нужны уже записанные нарушения, которых неоткуда взять).
            # temporal НЕ считаем «сильным сигналом» для bypass, если это мобильный / один ASN /
            # переключение сетей: CGNAT там штатно даёт пачку одновременных IP (temporal может
            # дойти до 100 при >5 IP), но это не явный шаринг. geo/hwid/ua остаются сильными всегда.
            _temporal_suppressed = is_network_switch or _has_mobile or (is_same_asn and asn_ratio >= 0.8)
            _strongest_signal = max(
                geo_score.score, hwid_score.score, ua_score.score,
                (0.0 if _temporal_suppressed else temporal_score.score),
                profile_score.score, asn_score.score, device_score.score,
            )
            if _strongest_signal >= 85.0:
                raw_score = max(raw_score, 50.0)

            # Если есть серьёзные одновременные подключения (высокий скор), устанавливаем минимум
            # Применяем только для очевидных нарушений (temporal >= 80), чтобы не создавать
            # ложных срабатываний при обычном переключении сетей
            #
            # НЕ применяем жёсткий floor, если:
            #  - это паттерн переключения сетей (WiFi <-> Mobile), ИЛИ
            #  - есть мобильные подключения (CGNAT даёт пачку IP с одного устройства), ИЛИ
            #  - все/почти все IP от одного провайдера (один ASN = один NAT, а не разные люди).
            # Иначе мобильные юзеры, чей connection_type GeoIP не распознал как mobile,
            # ловят ложное нарушение (temporal 80 → floor 70), перебивающее ASN/consistency-снижения.
            # Реальный шаринг через одного провайдера всё равно ловится subnet-/HWID-проверками.
            floor_suppressed = is_network_switch or _has_mobile or (is_same_asn and asn_ratio >= 0.8)
            if not floor_suppressed:
                if temporal_score.score >= 80.0 and temporal_score.simultaneous_connections_count > 1:
                    raw_score = max(raw_score, 70.0)

            # HWID-нарушение квалифицируется ИЛИ кросс-аккаунтом (другие аккаунты делят HWID),
            # ИЛИ абузом мультитарифа (один telegram_id с N подписками на одном HWID — там
            # other_accounts_count=0, поэтому отдельный флаг, иначе мультитариф не детектится).
            _hwid_qualifies = hwid_score.other_accounts_count >= 1 or getattr(hwid_score, "per_account_abuse", False)
            # Кросс-аккаунт / мультитариф — сильное нарушение, минимум 80 (soft_block).
            # Порог 85 (а не 100): hwid_score=100 требует overflow>=3 = 6+ аккаунтов на HWID,
            # а классические «3-5 аккаунтов на телефоне» дают 85 и раньше проваливались в floor 50.
            if hwid_score.score >= 85.0 and _hwid_qualifies:
                raw_score = max(raw_score, 80.0)
            # Промежуточные HWID скоры (65+) — минимум 50 (monitor)
            elif hwid_score.score >= 65.0 and _hwid_qualifies:
                raw_score = max(raw_score, 50.0)

            # User-Agent hard floors — явные сигналы переопределяют взвешенный скор
            # Ссылка подписки в UA = 100% двойной туннель → warn+
            if ua_score.has_link_in_ua:
                ua_link_floor = float(config_service.get("violation_ua_link_floor", 70.0) or 70.0)
                raw_score = max(raw_score, ua_link_floor)
            elif ua_score.has_bot_library:
                ua_bot_floor = float(config_service.get("violation_ua_bot_floor", 55.0) or 55.0)
                raw_score = max(raw_score, ua_bot_floor)

            # --- Проверка экстремального абьюза (жёсткая блокировка) ---
            extreme_abuse_reasons = []
            hb_ips = config_service.get("violations_hard_block_ips", 50)
            hb_sim = config_service.get("violations_hard_block_simultaneous", 20)
            hb_dev = config_service.get("violations_hard_block_devices", 80)
            hb_hwid = config_service.get("violations_hard_block_hwid_matches", 10)

            # 1) Аномально много уникальных IP
            if hb_ips > 0 and len(current_ips) >= hb_ips:
                extreme_abuse_reasons.append(
                    f"Экстремальное количество IP: {len(current_ips)} уникальных адресов (порог: {hb_ips})"
                )

            # 2) Много одновременных активных подключений
            sim_count = getattr(temporal_score, 'simultaneous_connections_count', 0)
            if hb_sim > 0 and sim_count >= hb_sim:
                extreme_abuse_reasons.append(
                    f"Экстремальное количество одновременных подключений: {sim_count} (порог: {hb_sim})"
                )

            # 3) Много устройств по fingerprint
            if hb_dev > 0 and hasattr(device_score, 'unique_fingerprints_count') and device_score.unique_fingerprints_count >= hb_dev:
                extreme_abuse_reasons.append(
                    f"Экстремальное количество устройств: {device_score.unique_fingerprints_count} fingerprints (порог: {hb_dev})"
                )

            # 4) Много одинаковых устройств по HWID
            if hb_hwid > 0 and hasattr(hwid_score, 'shared_hwids_count') and hwid_score.shared_hwids_count >= hb_hwid:
                extreme_abuse_reasons.append(
                    f"Массовый HWID абьюз: {hwid_score.shared_hwids_count} совпадающих HWID (порог: {hb_hwid})"
                )

            if extreme_abuse_reasons:
                raw_score = 100.0
                all_reasons_extra = extreme_abuse_reasons  # Will be added below
                logger.warning(
                    "Extreme abuse detected for %s: %s",
                    user_uuid, "; ".join(extreme_abuse_reasons)
                )
            else:
                all_reasons_extra = []

            # Определяем рекомендуемое действие
            recommended_action = self._get_action(raw_score)
            
            # Вычисляем уверенность на основе количества сработавших факторов и силы сигналов
            active_factors = sum(1 for s in [
                temporal_score.score, geo_score.score, asn_score.score,
                profile_score.score, device_score.score, hwid_score.score,
                ua_score.score,
            ] if s > 0)
            data_quality = min(1.0, len(connection_history) / 10.0)  # Больше данных = выше уверенность
            score_factor = min(1.0, raw_score / 100.0)
            confidence = min(1.0, score_factor * (0.4 + 0.1 * active_factors) * (0.5 + 0.5 * data_quality))
            
            # Собираем все причины (с дедупликацией)
            all_reasons = []
            seen_reasons: set = set()
            for reason in (
                all_reasons_extra +
                temporal_score.reasons +
                geo_score.reasons +
                asn_score.reasons +
                profile_score.reasons +
                device_score.reasons +
                hwid_score.reasons +
                ua_score.reasons
            ):
                if reason not in seen_reasons:
                    seen_reasons.add(reason)
                    all_reasons.append(reason)

            return ViolationScore(
                total=min(raw_score, 100.0),
                breakdown={
                    'temporal': temporal_score,
                    'geo': geo_score,
                    'asn': asn_score,
                    'profile': profile_score,
                    'device': device_score,
                    'hwid': hwid_score,
                    'user_agent': ua_score,
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
    
    async def _fetch_srh_records(self, user_uuid: str) -> Optional[List[Dict[str, Any]]]:
        """
        Получить Subscription Request History для юзера.

        Основной источник — локальная БД (синкается через sync.py).
        Fallback — прямой вызов Panel API если локальных записей нет (например первый запуск).

        Возвращает нормализованный список: [{user_agent, request_id, request_ip, request_at}, ...]
        """
        now = time.monotonic()
        cached = self._srh_cache.get(user_uuid)
        if cached and (now - cached[0]) < self._srh_cache_ttl_seconds:
            return cached[1]

        if len(self._srh_cache) > 5000:
            expired = [k for k, (t, _) in self._srh_cache.items() if (now - t) > self._srh_cache_ttl_seconds]
            for k in expired:
                self._srh_cache.pop(k, None)

        # 1. Пробуем локальную БД
        local_rows = await self.db.get_user_srh_records(user_uuid, limit=100)
        if local_rows:
            normalized = [
                {
                    "request_id": r.get("id"),
                    "user_agent": r.get("user_agent"),
                    "request_ip": r.get("request_ip"),
                    "request_at": r.get("request_at"),
                }
                for r in local_rows
            ]
            self._srh_cache[user_uuid] = (now, normalized)
            return normalized

        # 2. Fallback — Panel API (первый запуск до полного sync)
        try:
            from shared.api_client import api_client
            result = await api_client.get_user_subscription_request_history(user_uuid)
        except Exception as e:
            logger.debug("Failed to fetch SRH for user %s: %s", user_uuid, e)
            return None

        response = result.get("response", result) if isinstance(result, dict) else result
        raw_records = response.get("records", []) if isinstance(response, dict) else []

        normalized: List[Dict[str, Any]] = []
        for r in raw_records:
            if not isinstance(r, dict):
                continue
            request_at_raw = r.get("requestAt")
            request_at: Any = None
            if isinstance(request_at_raw, str):
                try:
                    request_at = datetime.fromisoformat(request_at_raw.replace("Z", "+00:00"))
                except ValueError:
                    request_at = request_at_raw
            elif isinstance(request_at_raw, datetime):
                request_at = request_at_raw

            normalized.append({
                "request_id": r.get("id"),
                "user_agent": r.get("userAgent"),
                "request_ip": r.get("requestIp"),
                "request_at": request_at,
            })

        self._srh_cache[user_uuid] = (now, normalized)
        return normalized

    def _detect_network_switch_pattern(self, asn_types: Set[str]) -> bool:
        """
        Определить, выглядит ли паттерн подключений как переключение сетей (WiFi <-> Mobile).

        Паттерн переключения сетей:
        - Есть мобильный провайдер (mobile, mobile_isp) И
        - Есть домашний/проводной провайдер (fixed, isp, residential, regional_isp)

        Это типичная ситуация когда пользователь переключается между WiFi дома и мобильным интернетом.

        Args:
            asn_types: Множество типов провайдеров в подключениях

        Returns:
            True если паттерн похож на переключение сетей
        """
        mobile_types = {'mobile', 'mobile_isp'}
        home_types = {'fixed', 'isp', 'residential', 'regional_isp'}

        has_mobile = bool(asn_types & mobile_types)
        has_home = bool(asn_types & home_types)

        return has_mobile and has_home

    async def _check_same_asn_pattern(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]],
        ip_metadata_cache: Optional[Dict] = None
    ) -> tuple[bool, float]:
        """
        Проверить, принадлежат ли IP одному провайдеру (ASN).

        Если все или большинство IP от одного провайдера, это снижает вероятность шаринга,
        т.к. один пользователь обычно использует одного провайдера (особенно мобильного).

        Returns:
            Tuple (is_same_asn, ratio) где:
            - is_same_asn: True если большинство IP от одного провайдера
            - ratio: доля IP от основного провайдера (0.0 - 1.0)
        """
        # Собираем все уникальные IP
        all_ips = set()
        for conn in connections:
            all_ips.add(str(conn.ip_address))
        for conn in connection_history[-10:]:  # Последние 10 записей
            ip = str(conn.get("ip_address", ""))
            if ip:
                all_ips.add(ip)

        if len(all_ips) <= 1:
            return True, 1.0

        # Получаем ASN для каждого IP (используем кэш если передан)
        if ip_metadata_cache is not None:
            ip_metadata = {ip: ip_metadata_cache[ip] for ip in all_ips if ip in ip_metadata_cache}
            # Дозагружаем IP которых нет в кэше
            missing_ips = all_ips - set(ip_metadata.keys())
            if missing_ips:
                extra = await self.geo_analyzer.geoip.lookup_batch(list(missing_ips))
                ip_metadata.update(extra)
        else:
            ip_metadata = await self.geo_analyzer.geoip.lookup_batch(list(all_ips))

        asn_counts: Dict[Optional[int], int] = {}
        for ip, meta in ip_metadata.items():
            asn = meta.asn
            asn_counts[asn] = asn_counts.get(asn, 0) + 1

        if not asn_counts:
            return False, 0.0

        # Находим самый частый ASN
        max_asn_count = max(asn_counts.values())
        total_ips = len(ip_metadata)

        ratio = max_asn_count / total_ips if total_ips > 0 else 0.0

        # Считаем "один провайдер" если >= 70% IP от него
        is_same_asn = ratio >= 0.7

        return is_same_asn, ratio

    @staticmethod
    def _is_private_ip(ip_str: str) -> bool:
        """Проверка приватного IP-адреса (RFC 1918 + loopback)."""
        if ip_str.startswith(('127.', '192.168.', '10.')):
            return True
        if ip_str.startswith('172.'):
            parts = ip_str.split('.')
            if len(parts) >= 2:
                try:
                    second_octet = int(parts[1])
                    return 16 <= second_octet <= 31
                except ValueError:
                    pass
        return False

    def _check_subnet_proximity(
        self,
        connections: List[ActiveConnection],
        connection_history: List[Dict[str, Any]]
    ) -> tuple[bool, float]:
        """
        Проверить, находятся ли IP в одной подсети (/24 или /16).

        IP в одной /24 подсети (напр. 185.26.120.X) почти наверняка принадлежат одному
        NAT/CGNAT/корпоративной сети, а не разным пользователям.

        Returns:
            Tuple (is_same_subnet, modifier) где:
            - is_same_subnet: True если большинство IP в одной подсети
            - modifier: множитель для скора (0.2 = сильное снижение, 1.0 = без снижения)
        """
        all_ips = set()
        for conn in connections:
            ip_str = str(conn.ip_address)
            if not self._is_private_ip(ip_str):
                all_ips.add(ip_str)
        for conn in connection_history[-10:]:
            ip_str = str(conn.get("ip_address", ""))
            if ip_str and not self._is_private_ip(ip_str):
                all_ips.add(ip_str)

        if len(all_ips) <= 1:
            return False, 1.0

        # Группируем по /24 и /16 подсетям
        subnets_24: Dict[str, List[str]] = {}
        subnets_16: Dict[str, List[str]] = {}
        for ip in all_ips:
            parts = ip.split('.')
            if len(parts) == 4:
                subnet_24 = '.'.join(parts[:3])
                subnet_16 = '.'.join(parts[:2])
                subnets_24.setdefault(subnet_24, []).append(ip)
                subnets_16.setdefault(subnet_16, []).append(ip)

        total = len(all_ips)
        if total == 0:
            return False, 1.0

        # Находим самую большую группу в /24
        max_same_24 = max((len(ips) for ips in subnets_24.values()), default=0)
        max_same_16 = max((len(ips) for ips in subnets_16.values()), default=0)

        ratio_24 = max_same_24 / total
        ratio_16 = max_same_16 / total

        # Если >= 70% IP в одной /24 подсети — очень вероятно один NAT
        if ratio_24 >= 0.7:
            logger.debug(
                "Subnet proximity: %.0f%% IPs in same /24 subnet (%d/%d)",
                ratio_24 * 100, max_same_24, total
            )
            return True, 0.2  # Сильное снижение — почти наверняка один NAT

        # Если >= 70% IP в одной /16 подсети — вероятно один провайдер/регион
        if ratio_16 >= 0.7:
            logger.debug(
                "Subnet proximity: %.0f%% IPs in same /16 subnet (%d/%d)",
                ratio_16 * 100, max_same_16, total
            )
            return True, 0.5  # Умеренное снижение — один провайдер

        return False, 1.0

    async def _check_violation_consistency(self, user_uuid: str) -> float:
        """
        Проверить повторяемость нарушений для пользователя.

        Одиночное срабатывание может быть случайным (переключение сети, глитч).
        Повторяющиеся срабатывания — более надёжный сигнал.

        Returns:
            Множитель для скора:
            - 0.3 — первое нарушение за 2 часа (вероятно ложное)
            - 0.6 — второе нарушение (неоднозначно)
            - 1.0 — 3+ нарушений (устойчивый паттерн)
        """
        try:
            recent_count = await self.db.get_recent_violations_count(user_uuid, hours=2)
            if recent_count == 0:
                logger.debug("Violation consistency: first violation in 2h for %s — dampening", user_uuid)
                return 0.3  # Первое срабатывание — сильный dampening
            elif recent_count == 1:
                logger.debug("Violation consistency: 2nd violation in 2h for %s — moderate dampening", user_uuid)
                return 0.6  # Второе — умеренный dampening
            else:
                logger.debug("Violation consistency: %d violations in 2h for %s — consistent pattern", recent_count, user_uuid)
                return 1.0  # 3+ — устойчивый паттерн, без снижения
        except Exception as e:
            logger.debug("Error checking violation consistency: %s", e)
            return 1.0  # При ошибке не снижаем

    async def _check_known_ip_pairs(self, user_uuid: str, current_ips: Set[str], connection_history_30d: Optional[List] = None) -> float:
        """
        Проверить, являются ли текущие пары IP «знакомыми» для пользователя.

        Если пользователь регулярно использует одни и те же IP-адреса (дом + работа, WiFi + mobile),
        это его нормальный паттерн, а не шаринг.

        Args:
            user_uuid: UUID пользователя
            current_ips: Текущие IP адреса пользователя
            connection_history_30d: Опциональная предзагруженная 30-дневная история

        Returns:
            Множитель для скора:
            - 0.3 — все пары IP знакомые (регулярный паттерн)
            - 0.6 — большинство знакомые
            - 1.0 — все пары новые (подозрительно)
        """
        if len(current_ips) <= 1:
            return 1.0

        try:
            from collections import Counter

            # Используем переданную историю или загружаем
            history = connection_history_30d if connection_history_30d is not None else await self.db.get_connection_history(user_uuid, days=30)
            if not history or len(history) < 5:
                return 1.0  # Недостаточно данных для оценки

            # Группируем IP по дням
            daily_ips: Dict[str, Set[str]] = {}
            for conn in history:
                ip = str(conn.get("ip_address", ""))
                connected_at = conn.get("connected_at")
                if not ip or not connected_at:
                    continue
                if isinstance(connected_at, datetime):
                    day = connected_at.strftime('%Y-%m-%d')
                elif isinstance(connected_at, str):
                    day = connected_at[:10]
                else:
                    continue
                daily_ips.setdefault(day, set()).add(ip)

            # Считаем как часто каждая пара IP встречается в один день
            pair_counts: Counter = Counter()
            for day, ips in daily_ips.items():
                if len(ips) >= 2:
                    for pair in combinations(sorted(ips), 2):
                        pair_counts[pair] += 1

            # Проверяем текущие пары IP
            current_pairs = list(combinations(sorted(current_ips), 2))
            if not current_pairs:
                return 1.0

            # Пара считается «знакомой» если встречалась 5+ раз за месяц
            known_count = sum(1 for pair in current_pairs if pair_counts.get(pair, 0) >= 5)
            known_ratio = known_count / len(current_pairs)

            if known_ratio >= 0.8:
                logger.debug(
                    "Known IP pairs: %.0f%% pairs are familiar for %s",
                    known_ratio * 100, user_uuid
                )
                return 0.3  # Почти все пары знакомые — нормальный паттерн
            elif known_ratio >= 0.5:
                logger.debug(
                    "Known IP pairs: %.0f%% pairs are familiar for %s",
                    known_ratio * 100, user_uuid
                )
                return 0.6  # Половина знакомые
            else:
                return 1.0  # Большинство новые

        except Exception as e:
            logger.debug("Error checking known IP pairs: %s", e)
            return 1.0

    async def check_users_batch(
        self,
        user_uuids: List[str],
        window_minutes: int = 60,
        excluded_analyzers_map: Optional[Dict[str, Optional[List[str]]]] = None,
    ) -> Dict[str, Optional['ViolationScore']]:
        """Batch violation check: prefetch all data, then analyze per-user in memory."""
        if not self.db.is_connected or not user_uuids:
            return {}

        from shared.config_service import config_service
        if not config_service.get("violations_enabled", True):
            return {}

        device_counts, active_conns_map, histories_30d, baselines, shared_hwids_map = await asyncio.gather(
            self.db.batch_get_user_devices_counts(user_uuids),
            self.db.batch_get_active_connections(user_uuids, max_age_minutes=5),
            self.db.batch_get_connection_histories(user_uuids, days=30, limit_per_user=200),
            self.db.batch_get_user_baselines(user_uuids, max_age_seconds=self.profile_analyzer._BASELINE_CACHE_TTL),
            self.db.batch_get_shared_hwids(user_uuids),
        )

        ua_enabled = config_service.get("violations_analyzer_user_agent", True)
        srh_map: Dict[str, List[Dict[str, Any]]] = {}
        if ua_enabled:
            srh_map = await self.db.batch_get_srh_records(user_uuids, limit_per_user=100)

        # Convert raw active_conns rows to ActiveConnection dataclasses
        active_connections_map: Dict[str, List[ActiveConnection]] = {}
        for uid, rows in active_conns_map.items():
            active_connections_map[uid] = [
                ActiveConnection(
                    connection_id=r.get("id"),
                    user_uuid=r.get("user_uuid"),
                    ip_address=str(r.get("ip_address", "")),
                    node_uuid=r.get("node_uuid"),
                    connected_at=r.get("connected_at"),
                    device_info=r.get("device_info"),
                )
                for r in rows
            ]

        # Normalize SRH records
        srh_normalized: Dict[str, List[Dict[str, Any]]] = {}
        for uid, rows in srh_map.items():
            srh_normalized[uid] = [
                {"request_id": r.get("id"), "user_agent": r.get("user_agent"),
                 "request_ip": r.get("request_ip"), "request_at": r.get("request_at")}
                for r in rows
            ]

        results: Dict[str, Optional[ViolationScore]] = {}
        excluded_map = excluded_analyzers_map or {}
        needs_baseline_build: List[str] = []

        for uid in user_uuids:
            try:
                result = await self.check_user(
                    uid,
                    window_minutes=window_minutes,
                    excluded_analyzers=excluded_map.get(uid),
                    prefetched_device_count=device_counts.get(uid, 1),
                    prefetched_active_connections=active_connections_map.get(uid, []),
                    prefetched_history_30d=histories_30d.get(uid, []),
                    prefetched_baseline=baselines.get(uid),
                    prefetched_shared_hwids=shared_hwids_map.get(uid, []),
                    prefetched_srh_records=srh_normalized.get(uid),
                )
                results[uid] = result
                if uid not in baselines and histories_30d.get(uid):
                    needs_baseline_build.append(uid)
            except Exception as e:
                logger.warning("Batch check_user failed for %s: %s", uid, e)
                results[uid] = None

        # Fire-and-forget: build baselines for users without one (non-blocking)
        if needs_baseline_build:
            async def _build_baselines_bg():
                for uid in needs_baseline_build[:50]:
                    try:
                        await self.profile_analyzer.build_baseline(
                            uid, days=30, connection_history=histories_30d.get(uid)
                        )
                    except Exception:
                        pass
            asyncio.create_task(_build_baselines_bg())

        return results

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
        elif score < self.THRESHOLDS['hard_block']:
            return ViolationAction.TEMP_BLOCK
        else:
            return ViolationAction.HARD_BLOCK
