"""
Violations mixin — detection, whitelist, reports, batch methods.
"""
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from shared.db._base import _db_row_to_api_format

from shared.logger import logger
from shared.metrics import VIOLATIONS_DETECTED


class ViolationsMixin:
    # ==================== Violations ====================

    async def save_violation(
        self,
        user_uuid: str,
        score: float,
        recommended_action: str,
        username: Optional[str] = None,
        email: Optional[str] = None,
        telegram_id: Optional[int] = None,
        confidence: Optional[float] = None,
        temporal_score: Optional[float] = None,
        geo_score: Optional[float] = None,
        asn_score: Optional[float] = None,
        profile_score: Optional[float] = None,
        device_score: Optional[float] = None,
        ip_addresses: Optional[List[str]] = None,
        countries: Optional[List[str]] = None,
        cities: Optional[List[str]] = None,
        asn_types: Optional[List[str]] = None,
        os_list: Optional[List[str]] = None,
        client_list: Optional[List[str]] = None,
        reasons: Optional[List[str]] = None,
        simultaneous_connections: Optional[int] = None,
        unique_ips_count: Optional[int] = None,
        device_limit: Optional[int] = None,
        impossible_travel: bool = False,
        is_mobile: bool = False,
        is_datacenter: bool = False,
        is_vpn: bool = False,
        raw_breakdown: Optional[str] = None,
        hwid_score: Optional[float] = None,
        hwid_matched_users: Optional[str] = None,
        user_agent_score: Optional[float] = None,
        suspicious_user_agents: Optional[str] = None,
    ) -> Optional[int]:
        """
        Сохранить нарушение в базу данных.

        Returns:
            ID созданной записи или None при ошибке
        """
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                async with conn.transaction():
                    # Deduplication: skip if user already has an unresolved violation
                    existing = await conn.fetchval(
                        "SELECT id FROM violations WHERE user_uuid = $1 "
                        "AND action_taken IS NULL "
                        "ORDER BY detected_at DESC LIMIT 1",
                        user_uuid,
                    )
                    if existing:
                        logger.debug("Skipping duplicate violation for user %s (pending id=%d)", user_uuid, existing)
                        return existing

                    result = await conn.fetchval(
                        """
                        INSERT INTO violations (
                            user_uuid, username, email, telegram_id,
                            score, recommended_action, confidence,
                            temporal_score, geo_score, asn_score, profile_score, device_score,
                            hwid_score, user_agent_score,
                            ip_addresses, countries, cities, asn_types, os_list, client_list, reasons,
                            simultaneous_connections, unique_ips_count, device_limit,
                            impossible_travel, is_mobile, is_datacenter, is_vpn,
                            raw_breakdown, hwid_matched_users, suspicious_user_agents, detected_at
                        )
                        VALUES (
                            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
                            $15, $16, $17, $18, $19, $20, $21, $22, $23, $24,
                            $25, $26, $27, $28, $29, $30, $31, NOW()
                        )
                        RETURNING id
                        """,
                        user_uuid, username, email, telegram_id,
                        score, recommended_action, confidence,
                        temporal_score, geo_score, asn_score, profile_score, device_score,
                        hwid_score, user_agent_score,
                        ip_addresses, countries, cities, asn_types, os_list, client_list, reasons,
                        simultaneous_connections, unique_ips_count, device_limit,
                        impossible_travel, is_mobile, is_datacenter, is_vpn,
                        raw_breakdown, hwid_matched_users, suspicious_user_agents
                    )
                    if result is not None:
                        VIOLATIONS_DETECTED.labels(
                            action=(recommended_action or "unknown").lower()
                        ).inc()
                    return result

        except Exception as e:
            logger.error("Error saving violation for user %s: %s", user_uuid, e, exc_info=True)
            return None

    async def get_violations_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 0.0,
        limit: int = 1000,
        offset: int = 0,
        user_uuid: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
        ip: Optional[str] = None,
        country: Optional[str] = None,
        sort_by: str = 'detected_at',
        order: str = 'desc',
        recommended_action: Optional[str] = None,
        username: Optional[str] = None,
        user_uuid_whitelist: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Получить нарушения за указанный период с фильтрацией на стороне БД.

        Args:
            start_date: Начало периода
            end_date: Конец периода
            min_score: Минимальный скор (по умолчанию 0)
            limit: Максимальное количество записей
            offset: Смещение для пагинации
            user_uuid: Фильтр по UUID пользователя
            severity: Фильтр по серьёзности (low, medium, high, critical)
            resolved: Фильтр по статусу разрешения
            ip: Фильтр по IP адресу
            country: Фильтр по коду страны

        Returns:
            Список нарушений
        """
        if not self.is_connected:
            return []

        # Access-policy short-circuit: empty whitelist means no access
        if user_uuid_whitelist is not None and not user_uuid_whitelist:
            return []

        try:
            async with self.acquire() as conn:
                conditions = [
                    "detected_at >= $1",
                    "detected_at < $2",
                    "score >= $3",
                ]
                params: list = [start_date, end_date, min_score]
                idx = 4

                if user_uuid_whitelist is not None:
                    conditions.append(f"user_uuid::text = ANY(${idx})")
                    params.append(user_uuid_whitelist)
                    idx += 1

                if user_uuid:
                    conditions.append(f"user_uuid::text = ${idx}")
                    params.append(user_uuid)
                    idx += 1

                if severity:
                    severity_ranges = {
                        'low': (0, 40),
                        'medium': (40, 60),
                        'high': (60, 80),
                        'critical': (80, 101),
                    }
                    if severity in severity_ranges:
                        min_s, max_s = severity_ranges[severity]
                        conditions.append(f"score >= {min_s} AND score < {max_s}")

                if resolved is not None:
                    if resolved:
                        conditions.append("action_taken IS NOT NULL")
                    else:
                        conditions.append("action_taken IS NULL")

                if ip:
                    conditions.append(f"${idx} = ANY(ip_addresses)")
                    params.append(ip)
                    idx += 1

                if country:
                    conditions.append(f"UPPER(${idx}) = ANY(SELECT UPPER(x) FROM UNNEST(countries) AS x)")
                    params.append(country)
                    idx += 1

                if recommended_action:
                    conditions.append(f"recommended_action = ${idx}")
                    params.append(recommended_action)
                    idx += 1

                if username:
                    conditions.append(f"LOWER(username) LIKE LOWER(${idx})")
                    params.append(f"%{username}%")
                    idx += 1

                where = " AND ".join(conditions)
                params.extend([limit, offset])

                # Validate sort params (whitelist to prevent SQL injection)
                valid_sort = sort_by if sort_by in ('detected_at', 'score', 'user_count') else 'detected_at'
                valid_order = order if order in ('asc', 'desc') else 'desc'

                if valid_sort == 'user_count':
                    # Sort by number of violations per user using window function
                    rows = await conn.fetch(
                        f"""
                        SELECT *, COUNT(*) OVER (PARTITION BY user_uuid) AS _user_violation_count
                        FROM violations
                        WHERE {where}
                        ORDER BY _user_violation_count {valid_order}, id ASC
                        LIMIT ${idx} OFFSET ${idx + 1}
                        """,
                        *params
                    )
                else:
                    rows = await conn.fetch(
                        f"""
                        SELECT * FROM violations
                        WHERE {where}
                        ORDER BY {valid_sort} {valid_order}, id ASC
                        LIMIT ${idx} OFFSET ${idx + 1}
                        """,
                        *params
                    )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting violations for period: %s", e, exc_info=True)
            return []

    async def count_violations_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 0.0,
        user_uuid: Optional[str] = None,
        severity: Optional[str] = None,
        resolved: Optional[bool] = None,
        ip: Optional[str] = None,
        country: Optional[str] = None,
        recommended_action: Optional[str] = None,
        username: Optional[str] = None,
        user_uuid_whitelist: Optional[List[str]] = None,
    ) -> int:
        """Подсчитать количество нарушений за период с фильтрами (для пагинации)."""
        if not self.is_connected:
            return 0

        # Access-policy short-circuit
        if user_uuid_whitelist is not None and not user_uuid_whitelist:
            return 0

        try:
            async with self.acquire() as conn:
                conditions = [
                    "detected_at >= $1",
                    "detected_at < $2",
                    "score >= $3",
                ]
                params: list = [start_date, end_date, min_score]
                idx = 4

                if user_uuid_whitelist is not None:
                    conditions.append(f"user_uuid::text = ANY(${idx})")
                    params.append(user_uuid_whitelist)
                    idx += 1

                if user_uuid:
                    conditions.append(f"user_uuid::text = ${idx}")
                    params.append(user_uuid)
                    idx += 1

                if severity:
                    severity_ranges = {
                        'low': (0, 40),
                        'medium': (40, 60),
                        'high': (60, 80),
                        'critical': (80, 101),
                    }
                    if severity in severity_ranges:
                        min_s, max_s = severity_ranges[severity]
                        conditions.append(f"score >= {min_s} AND score < {max_s}")

                if resolved is not None:
                    if resolved:
                        conditions.append("action_taken IS NOT NULL")
                    else:
                        conditions.append("action_taken IS NULL")

                if ip:
                    conditions.append(f"${idx} = ANY(ip_addresses)")
                    params.append(ip)
                    idx += 1

                if country:
                    conditions.append(f"UPPER(${idx}) = ANY(SELECT UPPER(x) FROM UNNEST(countries) AS x)")
                    params.append(country)
                    idx += 1

                if recommended_action:
                    conditions.append(f"recommended_action = ${idx}")
                    params.append(recommended_action)
                    idx += 1

                if username:
                    conditions.append(f"LOWER(username) LIKE LOWER(${idx})")
                    params.append(f"%{username}%")
                    idx += 1

                where = " AND ".join(conditions)
                row = await conn.fetchval(
                    f"SELECT COUNT(*) FROM violations WHERE {where}",
                    *params
                )
                return row or 0

        except Exception as e:
            logger.error("Error counting violations for period: %s", e, exc_info=True)
            return 0

    async def get_violation_by_id(self, violation_id: int) -> Optional[Dict[str, Any]]:
        """Получить нарушение по ID."""
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT * FROM violations WHERE id = $1",
                    violation_id
                )
                return dict(row) if row else None

        except Exception as e:
            logger.error("Error getting violation by id %s: %s", violation_id, e, exc_info=True)
            return None

    async def get_violations_stats_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 0.0
    ) -> Dict[str, Any]:
        """
        Получить статистику нарушений за период.

        Returns:
            Словарь со статистикой
        """
        if not self.is_connected:
            return {
                'total': 0,
                'critical': 0,
                'high': 0,
                'medium': 0,
                'unique_users': 0,
                'avg_score': 0.0,
                'max_score': 0.0
            }

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE score >= 80) as critical,
                        COUNT(*) FILTER (WHERE score >= 60 AND score < 80) as high,
                        COUNT(*) FILTER (WHERE score >= 40 AND score < 60) as medium,
                        COUNT(DISTINCT user_uuid) as unique_users,
                        COALESCE(AVG(score), 0) as avg_score,
                        COALESCE(MAX(score), 0) as max_score
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    AND action_taken IS DISTINCT FROM 'annulled'
                    """,
                    start_date, end_date, min_score
                )
                return dict(row) if row else {
                    'total': 0,
                    'critical': 0,
                    'warning': 0,
                    'monitor': 0,
                    'unique_users': 0,
                    'avg_score': 0.0,
                    'max_score': 0.0
                }

        except Exception as e:
            logger.error("Error getting violations stats: %s", e, exc_info=True)
            return {
                'total': 0,
                'critical': 0,
                'high': 0,
                'medium': 0,
                'unique_users': 0,
                'avg_score': 0.0,
                'max_score': 0.0
            }

    async def get_top_violators_for_period(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Получить топ нарушителей за период.

        Returns:
            Список пользователей с количеством и максимальным скором нарушений
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        user_uuid,
                        MAX(username) as username,
                        MAX(email) as email,
                        MAX(telegram_id) as telegram_id,
                        COUNT(*) as violations_count,
                        MAX(score) as max_score,
                        AVG(score) as avg_score,
                        MAX(detected_at) as last_violation_at,
                        ARRAY_AGG(DISTINCT recommended_action) as actions
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    AND action_taken IS DISTINCT FROM 'annulled'
                    GROUP BY user_uuid
                    ORDER BY violations_count DESC, max_score DESC
                    LIMIT $4
                    """,
                    start_date, end_date, min_score, limit
                )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting top violators: %s", e, exc_info=True)
            return []

    async def get_top_violator_reasons(
        self,
        user_uuids: List[str],
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0,
        max_reasons: int = 5,
    ) -> Dict[str, List[str]]:
        """Получить топ причин нарушений для списка пользователей."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_uuid::text, array_agg(DISTINCT reason) as reasons
                    FROM (
                        SELECT user_uuid, unnest(reasons) as reason
                        FROM violations
                        WHERE user_uuid::text = ANY($1)
                        AND detected_at >= $2
                        AND detected_at < $3
                        AND score >= $4
                        AND action_taken IS DISTINCT FROM 'annulled'
                    ) sub
                    GROUP BY user_uuid
                    """,
                    user_uuids, start_date, end_date, min_score
                )
                return {
                    str(row['user_uuid']): (row['reasons'] or [])[:max_reasons]
                    for row in rows
                }

        except Exception as e:
            logger.error("Error getting top violator reasons: %s", e, exc_info=True)
            return {}

    async def get_violations_by_country(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0
    ) -> Dict[str, int]:
        """
        Получить распределение нарушений по странам.

        Returns:
            Словарь {страна: количество}
        """
        if not self.is_connected:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        UNNEST(countries) as country,
                        COUNT(*) as count
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    AND countries IS NOT NULL
                    AND action_taken IS DISTINCT FROM 'annulled'
                    GROUP BY country
                    ORDER BY count DESC
                    """,
                    start_date, end_date, min_score
                )
                return {row['country']: row['count'] for row in rows}

        except Exception as e:
            logger.error("Error getting violations by country: %s", e, exc_info=True)
            return {}

    async def get_violations_by_action(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 0.0
    ) -> Dict[str, int]:
        """
        Получить распределение нарушений по рекомендуемым действиям.

        Returns:
            Словарь {действие: количество}
        """
        if not self.is_connected:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        recommended_action,
                        COUNT(*) as count
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    AND action_taken IS DISTINCT FROM 'annulled'
                    GROUP BY recommended_action
                    ORDER BY count DESC
                    """,
                    start_date, end_date, min_score
                )
                return {row['recommended_action']: row['count'] for row in rows}

        except Exception as e:
            logger.error("Error getting violations by action: %s", e, exc_info=True)
            return {}

    async def get_violations_by_asn_type(
        self,
        start_date: datetime,
        end_date: datetime,
        min_score: float = 30.0
    ) -> Dict[str, int]:
        """
        Получить распределение нарушений по типам провайдеров.

        Returns:
            Словарь {тип: количество}
        """
        if not self.is_connected:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        UNNEST(asn_types) as asn_type,
                        COUNT(*) as count
                    FROM violations
                    WHERE detected_at >= $1
                    AND detected_at < $2
                    AND score >= $3
                    AND asn_types IS NOT NULL
                    AND action_taken IS DISTINCT FROM 'annulled'
                    GROUP BY asn_type
                    ORDER BY count DESC
                    """,
                    start_date, end_date, min_score
                )
                return {row['asn_type']: row['count'] for row in rows}

        except Exception as e:
            logger.error("Error getting violations by ASN type: %s", e, exc_info=True)
            return {}

    async def get_recent_violations_count(
        self,
        user_uuid: str,
        hours: int = 2
    ) -> int:
        """
        Подсчитать количество нарушений пользователя за последние N часов.

        Используется для проверки повторяемости нарушений:
        одиночное срабатывание может быть ложным, а повторяющиеся — устойчивый паттерн.

        Args:
            user_uuid: UUID пользователя
            hours: Временное окно в часах

        Returns:
            Количество нарушений за указанный период
        """
        if not self.is_connected:
            return 0

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT COUNT(*) as cnt FROM violations
                    WHERE user_uuid = $1
                    AND detected_at > NOW() - make_interval(hours => $2)
                    """,
                    user_uuid, int(hours)
                )
                return row['cnt'] if row else 0

        except Exception as e:
            logger.error("Error counting recent violations: %s", e, exc_info=True)
            return 0

    async def get_user_violations(
        self,
        user_uuid: str,
        days: int = 30,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Получить историю нарушений пользователя.

        Args:
            user_uuid: UUID пользователя
            days: Количество дней истории
            limit: Максимальное количество записей

        Returns:
            Список нарушений
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM violations
                    WHERE user_uuid = $1
                    AND detected_at > NOW() - make_interval(days => $2)
                    ORDER BY detected_at DESC, id ASC
                    LIMIT $3
                    """,
                    user_uuid, int(days), limit
                )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting user violations: %s", e, exc_info=True)
            return []

    async def update_violation_action(
        self,
        violation_id: int,
        action_taken: str,
        admin_telegram_id: int,
        admin_comment: Optional[str] = None,
    ) -> bool:
        """
        Обновить принятое действие по нарушению.

        Args:
            violation_id: ID нарушения
            action_taken: Принятое действие
            admin_telegram_id: Telegram ID администратора
            admin_comment: Примечание администратора

        Returns:
            True если успешно
        """
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                if action_taken == "annulled":
                    # При аннулировании обнуляем скор — ложное срабатывание
                    result = await conn.execute(
                        """
                        UPDATE violations
                        SET action_taken = $1,
                            action_taken_at = NOW(),
                            action_taken_by = $2,
                            admin_comment = $3,
                            score = 0,
                            temporal_score = 0,
                            geo_score = 0,
                            asn_score = 0,
                            profile_score = 0,
                            device_score = 0,
                            hwid_score = 0
                        WHERE id = $4
                        """,
                        action_taken, admin_telegram_id, admin_comment, violation_id
                    )
                else:
                    result = await conn.execute(
                        """
                        UPDATE violations
                        SET action_taken = $1,
                            action_taken_at = NOW(),
                            action_taken_by = $2,
                            admin_comment = $3
                        WHERE id = $4
                        """,
                        action_taken, admin_telegram_id, admin_comment, violation_id
                    )
                return result == "UPDATE 1"

        except Exception as e:
            logger.error("Error updating violation action: %s", e, exc_info=True)
            return False

    async def annul_pending_violations(
        self,
        user_uuid: str,
        admin_telegram_id: int,
        admin_comment: Optional[str] = None,
    ) -> int:
        """
        Аннулировать все нерассмотренные нарушения пользователя.

        Returns:
            Количество аннулированных записей
        """
        if not self.is_connected:
            return 0

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violations
                    SET action_taken = 'annulled',
                        action_taken_at = NOW(),
                        action_taken_by = $1,
                        admin_comment = $2,
                        score = 0,
                        temporal_score = 0,
                        geo_score = 0,
                        asn_score = 0,
                        profile_score = 0,
                        device_score = 0,
                        hwid_score = 0
                    WHERE user_uuid = $3
                      AND action_taken IS NULL
                    """,
                    admin_telegram_id, admin_comment, user_uuid,
                )
                # result format: "UPDATE N"
                count = int(result.split()[-1]) if result else 0
                return count

        except Exception as e:
            logger.error("Error annulling violations for user %s: %s", user_uuid, e, exc_info=True)
            return 0

    async def annul_all_pending_violations(
        self,
        admin_telegram_id: int,
        admin_comment: Optional[str] = None,
    ) -> int:
        """
        Аннулировать все нерассмотренные нарушения (глобально).

        Returns:
            Количество аннулированных записей
        """
        if not self.is_connected:
            return 0

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violations
                    SET action_taken = 'annulled',
                        action_taken_at = NOW(),
                        action_taken_by = $1,
                        admin_comment = $2,
                        score = 0,
                        temporal_score = 0,
                        geo_score = 0,
                        asn_score = 0,
                        profile_score = 0,
                        device_score = 0,
                        hwid_score = 0
                    WHERE action_taken IS NULL
                    """,
                    admin_telegram_id, admin_comment,
                )
                count = int(result.split()[-1]) if result else 0
                return count

        except Exception as e:
            logger.error("Error annulling all violations: %s", e, exc_info=True)
            return 0

    async def mark_violation_notified(self, violation_id: int) -> bool:
        """Отметить нарушение как отправленное в уведомлении."""
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violations
                    SET notified_at = NOW()
                    WHERE id = $1
                    """,
                    violation_id
                )
                return result == "UPDATE 1"

        except Exception as e:
            logger.error("Error marking violation as notified: %s", e, exc_info=True)
            return False

    async def get_user_last_violation_notification(self, user_uuid: str) -> Optional[datetime]:
        """Получить время последнего уведомления о нарушении для пользователя."""
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                row = await conn.fetchval(
                    "SELECT MAX(notified_at) FROM violations WHERE user_uuid = $1 AND notified_at IS NOT NULL",
                    user_uuid
                )
                return row

        except Exception as e:
            logger.error("Error getting last violation notification for %s: %s", user_uuid, e, exc_info=True)
            return None

    async def mark_user_violations_notified(self, user_uuid: str) -> None:
        """Отметить последнее не-нотифицированное нарушение пользователя."""
        if not self.is_connected:
            return

        try:
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    UPDATE violations SET notified_at = NOW()
                    WHERE user_uuid = $1 AND notified_at IS NULL AND action_taken IS NULL
                    """,
                    user_uuid
                )

        except Exception as e:
            logger.error("Error marking violations notified for %s: %s", user_uuid, e, exc_info=True)

    async def cleanup_old_violations(self, retention_days: int = 90, batch_size: int = 5000) -> int:
        """Удалить resolved/annulled violations старше N дней (батчами).

        Returns:
            Количество удалённых записей
        """
        if not self.is_connected:
            return 0

        total = 0
        max_batches = 1000
        try:
            for _ in range(max_batches):
                async with self.acquire() as conn:
                    result = await conn.execute(
                        """
                        DELETE FROM violations
                        WHERE id IN (
                            SELECT id FROM violations
                            WHERE action_taken IS NOT NULL
                              AND detected_at < NOW() - make_interval(days => $1)
                            ORDER BY detected_at
                            LIMIT $2
                        )
                        """,
                        retention_days, batch_size,
                    )
                    deleted = int(result.split()[-1]) if result and result.split() else 0
                    total += deleted
                    if deleted < batch_size:
                        break
                await asyncio.sleep(0.1)
            else:
                logger.warning("cleanup_old_violations hit max_batches limit (%d batches, %d rows)", max_batches, total)
            return total

        except Exception as e:
            logger.error("Error cleaning up old violations: %s", e, exc_info=True)
            return total

    # ==================== Violation Whitelist ====================

    _WHITELIST_CACHE_TTL = 60  # seconds
    _WHITELIST_CACHE_MAX_SIZE = 10000

    async def is_user_violation_whitelisted(self, user_uuid: str) -> tuple:
        """
        Проверить, находится ли пользователь в whitelist нарушений.
        Результат кэшируется на 60 секунд для минимизации нагрузки в collector pipeline.

        Returns:
            (is_whitelisted: bool, excluded_analyzers: Optional[List[str]])
            - (True, None) = полный whitelist (все проверки отключены)
            - (True, ["hwid", "geo"]) = частичное исключение
            - (False, None) = не в whitelist
        """
        now = time.time()
        cached = self._whitelist_cache.get(user_uuid)
        if cached and (now - cached[1]) < self._WHITELIST_CACHE_TTL:
            return cached[0]

        # Evict expired entries if cache grows too large
        if len(self._whitelist_cache) > self._WHITELIST_CACHE_MAX_SIZE:
            expired = [k for k, (_, ts) in self._whitelist_cache.items() if (now - ts) >= self._WHITELIST_CACHE_TTL]
            for k in expired:
                self._whitelist_cache.pop(k, None)

        if not self.is_connected:
            return (False, None)

        # If we already know the table doesn't exist, skip the query
        if self._whitelist_table_available is False:
            return (False, None)

        # If excluded_analyzers column not available, use legacy query
        if self._whitelist_column_available is False:
            return await self._is_user_whitelisted_legacy(user_uuid, now)

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT excluded_analyzers FROM violation_whitelist
                    WHERE user_uuid = $1
                    AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    user_uuid,
                )
                self._whitelist_table_available = True
                self._whitelist_column_available = True
                if row is None:
                    result = (False, None)
                else:
                    excluded = row["excluded_analyzers"]
                    result = (True, list(excluded) if excluded else None)
                self._whitelist_cache[user_uuid] = (result, now)
                return result
        except Exception as e:
            err_msg = str(e)
            if "violation_whitelist" in err_msg and "does not exist" in err_msg:
                if self._whitelist_table_available is not False:
                    logger.warning("violation_whitelist table does not exist yet — run 'alembic upgrade head' to create it")
                    self._whitelist_table_available = False
                return (False, None)
            if "excluded_analyzers" in err_msg and "does not exist" in err_msg:
                logger.warning("excluded_analyzers column not yet added — run 'alembic upgrade head'")
                self._whitelist_column_available = False
                return await self._is_user_whitelisted_legacy(user_uuid, now)
            logger.error("Error checking violation whitelist for %s: %s", user_uuid, e, exc_info=True)
            return (False, None)

    async def _is_user_whitelisted_legacy(self, user_uuid: str, now: float) -> tuple:
        """Fallback for old schema without excluded_analyzers column."""
        try:
            async with self.acquire() as conn:
                row = await conn.fetchval(
                    """
                    SELECT 1 FROM violation_whitelist
                    WHERE user_uuid = $1
                    AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    user_uuid,
                )
                result = (row is not None, None) if row else (False, None)
                self._whitelist_cache[user_uuid] = (result, now)
                return result
        except Exception as e:
            logger.debug("Whitelist legacy check failed for user: %s", e)
            return (False, None)

    async def add_to_violation_whitelist(
        self,
        user_uuid: str,
        reason: Optional[str] = None,
        admin_id: Optional[int] = None,
        admin_username: Optional[str] = None,
        expires_at: Optional[datetime] = None,
        excluded_analyzers: Optional[List[str]] = None,
    ) -> tuple:
        """Добавить пользователя в whitelist нарушений.

        Args:
            excluded_analyzers: None = полный whitelist. Список = частичное исключение
                из конкретных анализаторов (temporal, geo, asn, profile, device, hwid).

        Returns:
            (success: bool, error: Optional[str])
        """
        if not self.is_connected:
            return (False, "Database not connected")

        try:
            async with self.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO violation_whitelist
                        (user_uuid, reason, added_by_admin_id, added_by_username, expires_at, excluded_analyzers)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (user_uuid) DO UPDATE SET
                        reason = EXCLUDED.reason,
                        added_by_admin_id = EXCLUDED.added_by_admin_id,
                        added_by_username = EXCLUDED.added_by_username,
                        added_at = NOW(),
                        expires_at = EXCLUDED.expires_at,
                        excluded_analyzers = EXCLUDED.excluded_analyzers
                    """,
                    user_uuid, reason, admin_id, admin_username, expires_at, excluded_analyzers,
                )
                # Invalidate cache
                self._whitelist_cache.pop(user_uuid, None)
                return (True, None)
        except Exception as e:
            err_msg = str(e)

            # Fallback: excluded_analyzers column may not exist (migration 0035 not applied)
            if "excluded_analyzers" in err_msg and "does not exist" in err_msg:
                logger.warning(
                    "excluded_analyzers column missing — inserting without it. "
                    "Run 'alembic upgrade head' to apply migration 0035."
                )
                try:
                    async with self.acquire() as conn:
                        await conn.execute(
                            """
                            INSERT INTO violation_whitelist
                                (user_uuid, reason, added_by_admin_id, added_by_username, expires_at)
                            VALUES ($1, $2, $3, $4, $5)
                            ON CONFLICT (user_uuid) DO UPDATE SET
                                reason = EXCLUDED.reason,
                                added_by_admin_id = EXCLUDED.added_by_admin_id,
                                added_by_username = EXCLUDED.added_by_username,
                                added_at = NOW(),
                                expires_at = EXCLUDED.expires_at
                            """,
                            user_uuid, reason, admin_id, admin_username, expires_at,
                        )
                        self._whitelist_cache.pop(user_uuid, None)
                        return (True, None)
                except Exception as e2:
                    logger.error("Error adding user %s to whitelist (fallback): %s", user_uuid, e2, exc_info=True)
                    return (False, str(e2))

            # Fallback: table doesn't exist
            if "violation_whitelist" in err_msg and "does not exist" in err_msg:
                logger.error(
                    "violation_whitelist table does not exist. "
                    "Run 'alembic upgrade head' to apply migration 0032."
                )
                return (False, "Table violation_whitelist not found — run alembic upgrade head")

            logger.error("Error adding user %s to violation whitelist: %s", user_uuid, e, exc_info=True)
            return (False, err_msg)

    async def update_violation_whitelist_exclusions(
        self,
        user_uuid: str,
        excluded_analyzers: Optional[List[str]] = None,
    ) -> bool:
        """Обновить список исключённых анализаторов для пользователя в whitelist."""
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violation_whitelist
                    SET excluded_analyzers = $2
                    WHERE user_uuid = $1
                    """,
                    user_uuid, excluded_analyzers,
                )
                self._whitelist_cache.pop(user_uuid, None)
                return result == "UPDATE 1"
        except Exception as e:
            logger.error("Error updating exclusions for %s: %s", user_uuid, e, exc_info=True)
            return False

    async def remove_from_violation_whitelist(self, user_uuid: str) -> bool:
        """Убрать пользователя из whitelist нарушений."""
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    "DELETE FROM violation_whitelist WHERE user_uuid = $1",
                    user_uuid,
                )
                # Invalidate cache
                self._whitelist_cache.pop(user_uuid, None)
                return result == "DELETE 1"
        except Exception as e:
            logger.error("Error removing user %s from violation whitelist: %s", user_uuid, e, exc_info=True)
            return False

    async def get_violation_whitelist(
        self,
        limit: int = 20,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """Получить список пользователей в whitelist с данными из users."""
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT
                        w.id,
                        w.user_uuid,
                        w.reason,
                        w.added_by_admin_id,
                        w.added_by_username,
                        w.added_at,
                        w.expires_at,
                        w.excluded_analyzers,
                        u.username,
                        u.email
                    FROM violation_whitelist w
                    LEFT JOIN users u ON u.uuid = w.user_uuid
                    ORDER BY w.added_at DESC
                    LIMIT $1 OFFSET $2
                    """,
                    limit, offset,
                )
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error("Error getting violation whitelist: %s", e, exc_info=True)
            return []

    async def get_violation_whitelist_count(self) -> int:
        """Получить количество пользователей в whitelist."""
        if not self.is_connected:
            return 0

        try:
            async with self.acquire() as conn:
                row = await conn.fetchval("SELECT COUNT(*) FROM violation_whitelist")
                return row or 0
        except Exception as e:
            logger.error("Error getting violation whitelist count: %s", e, exc_info=True)
            return 0

    # ==================== Violation Reports ====================

    async def save_violation_report(
        self,
        report_type: str,
        period_start: datetime,
        period_end: datetime,
        total_violations: int,
        critical_count: int,
        warning_count: int,
        monitor_count: int,
        unique_users: int,
        prev_total_violations: Optional[int] = None,
        trend_percent: Optional[float] = None,
        top_violators: Optional[str] = None,
        by_country: Optional[str] = None,
        by_action: Optional[str] = None,
        by_asn_type: Optional[str] = None,
        message_text: Optional[str] = None
    ) -> Optional[int]:
        """
        Сохранить отчёт в базу данных.

        Returns:
            ID созданного отчёта или None при ошибке
        """
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                result = await conn.fetchval(
                    """
                    INSERT INTO violation_reports (
                        report_type, period_start, period_end,
                        total_violations, critical_count, warning_count, monitor_count, unique_users,
                        prev_total_violations, trend_percent,
                        top_violators, by_country, by_action, by_asn_type,
                        message_text, generated_at
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, NOW())
                    RETURNING id
                    """,
                    report_type, period_start, period_end,
                    total_violations, critical_count, warning_count, monitor_count, unique_users,
                    prev_total_violations, trend_percent,
                    top_violators, by_country, by_action, by_asn_type,
                    message_text
                )
                return result

        except Exception as e:
            logger.error("Error saving violation report: %s", e, exc_info=True)
            return None

    async def mark_report_sent(self, report_id: int) -> bool:
        """Отметить отчёт как отправленный."""
        if not self.is_connected:
            return False

        try:
            async with self.acquire() as conn:
                result = await conn.execute(
                    """
                    UPDATE violation_reports
                    SET sent_at = NOW()
                    WHERE id = $1
                    """,
                    report_id
                )
                return result == "UPDATE 1"

        except Exception as e:
            logger.error("Error marking report as sent: %s", e, exc_info=True)
            return False

    async def get_last_report(self, report_type: str) -> Optional[Dict[str, Any]]:
        """
        Получить последний отчёт указанного типа.

        Args:
            report_type: Тип отчёта (daily/weekly/monthly)

        Returns:
            Данные отчёта или None
        """
        if not self.is_connected:
            return None

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM violation_reports
                    WHERE report_type = $1
                    ORDER BY period_end DESC
                    LIMIT 1
                    """,
                    report_type
                )
                return dict(row) if row else None

        except Exception as e:
            logger.error("Error getting last report: %s", e, exc_info=True)
            return None

    async def get_reports_history(
        self,
        report_type: Optional[str] = None,
        limit: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Получить историю отчётов.

        Args:
            report_type: Тип отчёта (опционально)
            limit: Максимальное количество записей

        Returns:
            Список отчётов
        """
        if not self.is_connected:
            return []

        try:
            async with self.acquire() as conn:
                if report_type:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM violation_reports
                        WHERE report_type = $1
                        ORDER BY period_end DESC
                        LIMIT $2
                        """,
                        report_type, limit
                    )
                else:
                    rows = await conn.fetch(
                        """
                        SELECT * FROM violation_reports
                        ORDER BY period_end DESC
                        LIMIT $1
                        """,
                        limit
                    )
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error("Error getting reports history: %s", e, exc_info=True)
            return []


    # ==================== Batch methods for violation detection ====================

    async def batch_get_whitelist_status(
        self, user_uuids: List[str]
    ) -> Dict[str, tuple]:
        """Batch whitelist check. Returns {uuid: (is_whitelisted, excluded_analyzers)}."""
        if not self.is_connected or not user_uuids:
            return {}

        if self._whitelist_table_available is False:
            return {}

        now = time.time()
        result: Dict[str, tuple] = {}
        to_fetch: List[str] = []

        for uid in user_uuids:
            cached = self._whitelist_cache.get(uid)
            if cached and (now - cached[1]) < self._WHITELIST_CACHE_TTL:
                result[uid] = cached[0]
            else:
                to_fetch.append(uid)

        if len(self._whitelist_cache) > self._WHITELIST_CACHE_MAX_SIZE:
            expired = [k for k, (_, ts) in self._whitelist_cache.items()
                       if (now - ts) >= self._WHITELIST_CACHE_TTL]
            for k in expired:
                self._whitelist_cache.pop(k, None)

        if not to_fetch:
            return result

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_uuid::text, excluded_analyzers
                    FROM violation_whitelist
                    WHERE user_uuid = ANY($1::uuid[])
                      AND (expires_at IS NULL OR expires_at > NOW())
                    """,
                    to_fetch,
                )
            found = set()
            for r in rows:
                uid = r["user_uuid"]
                found.add(uid)
                excluded = r.get("excluded_analyzers")
                val = (True, list(excluded) if excluded else None)
                result[uid] = val
                self._whitelist_cache[uid] = (val, now)

            for uid in to_fetch:
                if uid not in found:
                    val = (False, None)
                    result[uid] = val
                    self._whitelist_cache[uid] = (val, now)

            self._whitelist_table_available = True
        except Exception as e:
            if "does not exist" in str(e).lower():
                self._whitelist_table_available = False
            else:
                logger.warning("batch_get_whitelist_status failed: %s", e)

        return result

    async def batch_get_user_devices_counts(
        self, user_uuids: List[str]
    ) -> Dict[str, int]:
        """Batch get device counts from users.raw_data. Returns {uuid: count}."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT uuid::text, raw_data FROM users WHERE uuid = ANY($1::uuid[])",
                    user_uuids,
                )

            result: Dict[str, int] = {}
            for row in rows:
                uid = row["uuid"]
                count = 1
                raw_data = row.get("raw_data")
                if raw_data:
                    if isinstance(raw_data, str):
                        try:
                            raw_data = json.loads(raw_data)
                        except json.JSONDecodeError:
                            raw_data = None
                    if isinstance(raw_data, dict):
                        response = raw_data.get("response", raw_data)
                        hwid_limit = response.get("hwidDeviceLimit")
                        if hwid_limit is not None:
                            limit = int(hwid_limit)
                            count = 1 if limit == 0 else max(1, limit)
                        else:
                            dc = response.get("devicesCount")
                            if dc is not None:
                                count = max(1, int(dc))
                result[uid] = count

            for uid in user_uuids:
                if uid not in result:
                    result[uid] = 1
            return result
        except Exception as e:
            logger.warning("batch_get_user_devices_counts failed: %s", e)
            return {uid: 1 for uid in user_uuids}

    async def batch_get_active_connections(
        self, user_uuids: List[str], max_age_minutes: int = 5
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Batch get active connections for multiple users."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT id, user_uuid, ip_address, node_uuid, connected_at, device_info
                    FROM user_connections
                    WHERE user_uuid = ANY($1::uuid[])
                      AND disconnected_at IS NULL
                      AND connected_at > NOW() - make_interval(mins => $2)
                    ORDER BY user_uuid, connected_at DESC
                    """,
                    user_uuids, max_age_minutes,
                )

            result: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                uid = str(row["user_uuid"])
                result.setdefault(uid, []).append(dict(row))
            return result
        except Exception as e:
            logger.warning("batch_get_active_connections failed: %s", e)
            return {}

    async def batch_get_connection_histories(
        self, user_uuids: List[str], days: int = 30, limit_per_user: int = 200
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Batch get connection history using LATERAL JOIN for per-user LIMIT."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT sub.* FROM unnest($1::text[]) AS t(uid)
                    CROSS JOIN LATERAL (
                        SELECT id, user_uuid, ip_address, node_uuid,
                               connected_at, disconnected_at, device_info
                        FROM user_connections
                        WHERE user_uuid = t.uid::uuid
                          AND connected_at > NOW() - make_interval(days => $2)
                        ORDER BY connected_at DESC
                        LIMIT $3
                    ) sub
                    """,
                    user_uuids, days, limit_per_user,
                )

            result: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                uid = str(row["user_uuid"])
                result.setdefault(uid, []).append(dict(row))
            return result
        except Exception as e:
            logger.warning("batch_get_connection_histories failed: %s", e)
            return {}

    async def batch_get_user_baselines(
        self, user_uuids: List[str], max_age_seconds: int = 3600
    ) -> Dict[str, Dict[str, Any]]:
        """Batch get cached baselines for multiple users."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_uuid::text, typical_countries, typical_cities,
                           typical_regions, typical_asns, known_ips,
                           avg_daily_unique_ips, max_daily_unique_ips,
                           typical_hours, avg_session_duration_min, data_points
                    FROM user_baselines
                    WHERE user_uuid = ANY($1::uuid[])
                      AND computed_at > NOW() - make_interval(secs => $2)
                    """,
                    user_uuids, max_age_seconds,
                )

            result: Dict[str, Dict[str, Any]] = {}
            for row in rows:
                uid = row["user_uuid"]
                result[uid] = {
                    'typical_countries': list(row['typical_countries'] or []),
                    'typical_cities': list(row['typical_cities'] or []),
                    'typical_regions': list(row['typical_regions'] or []),
                    'typical_asns': list(row['typical_asns'] or []),
                    'known_ips': list(row['known_ips'] or [])[:500],
                    'avg_daily_unique_ips': row['avg_daily_unique_ips'] or 0.0,
                    'max_daily_unique_ips': row['max_daily_unique_ips'] or 0,
                    'typical_hours': list(row['typical_hours'] or []),
                    'avg_session_duration_minutes': row['avg_session_duration_min'] or 0,
                    'data_points': row['data_points'] or 0,
                }
            return result
        except Exception as e:
            logger.warning("batch_get_user_baselines failed: %s", e)
            return {}

    async def batch_get_shared_hwids(
        self, user_uuids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Batch get shared HWIDs for multiple users."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT h1.user_uuid::text AS source_uuid,
                           h2.hwid,
                           u.uuid::text AS user_uuid,
                           u.username, u.status, u.telegram_id,
                           me.telegram_id AS self_telegram_id
                    FROM user_hwid_devices h1
                    JOIN users me ON me.uuid = h1.user_uuid
                    JOIN user_hwid_devices h2
                      ON h1.hwid = h2.hwid AND h2.user_uuid != h1.user_uuid
                    JOIN users u ON h2.user_uuid = u.uuid
                    WHERE h1.user_uuid = ANY($1::uuid[])
                    ORDER BY h1.user_uuid, h2.hwid, u.username
                    """,
                    user_uuids,
                )

            result: Dict[str, List[Dict[str, Any]]] = {}
            temp: Dict[str, Dict[str, Dict[str, Any]]] = {}
            for r in rows:
                src = r["source_uuid"]
                hwid = r["hwid"]
                if src not in temp:
                    temp[src] = {}
                if hwid not in temp[src]:
                    temp[src][hwid] = {
                        "hwid": hwid,
                        "self_telegram_id": r["self_telegram_id"],
                        "other_users": [],
                    }
                temp[src][hwid]["other_users"].append({
                    "uuid": r["user_uuid"],
                    "username": r["username"],
                    "status": r["status"],
                    "telegram_id": r["telegram_id"],
                })

            for src, hwid_groups in temp.items():
                result[src] = list(hwid_groups.values())
            return result
        except Exception as e:
            logger.warning("batch_get_shared_hwids failed: %s", e)
            return {}

    async def batch_get_user_hwid_devices(
        self, user_uuids: List[str]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Batch get HWID devices for multiple users."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT user_uuid::text, hwid, platform, os_version,
                           device_model, app_version, user_agent,
                           created_at, updated_at
                    FROM user_hwid_devices
                    WHERE user_uuid = ANY($1::uuid[])
                    ORDER BY user_uuid, created_at DESC
                    """,
                    user_uuids,
                )

            result: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                uid = row["user_uuid"]
                result.setdefault(uid, []).append(dict(row))
            return result
        except Exception as e:
            logger.warning("batch_get_user_hwid_devices failed: %s", e)
            return {}

    async def batch_get_users_info(
        self, user_uuids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Batch get user info for multiple users."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT * FROM users WHERE uuid = ANY($1::uuid[])",
                    user_uuids,
                )
            return {
                str(row["uuid"]): _db_row_to_api_format(row)
                for row in rows
            }
        except Exception as e:
            logger.warning("batch_get_users_info failed: %s", e)
            return {}

    async def batch_get_srh_records(
        self, user_uuids: List[str], limit_per_user: int = 100
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Batch get SRH records using LATERAL JOIN."""
        if not self.is_connected or not user_uuids:
            return {}

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT sub.* FROM unnest($1::text[]) AS t(uid)
                    CROSS JOIN LATERAL (
                        SELECT id, user_uuid::text, request_ip, user_agent, request_at
                        FROM subscription_request_history
                        WHERE user_uuid = t.uid::uuid
                        ORDER BY request_at DESC
                        LIMIT $2
                    ) sub
                    """,
                    user_uuids, limit_per_user,
                )

            result: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                uid = row["user_uuid"]
                result.setdefault(uid, []).append(dict(row))
            return result
        except Exception as e:
            logger.warning("batch_get_srh_records failed: %s", e)
            return {}

