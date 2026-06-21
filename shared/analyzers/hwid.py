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

class HwidCrossAccountAnalyzer:
    """
    Анализ кросс-аккаунт HWID — обнаружение одного устройства на нескольких аккаунтах.

    Группирует совпавшие UUID по ``users.telegram_id``: подписки одного
    telegram_id (мультитарифный режим Bedolaga и аналоги) считаются одним
    аккаунтом. Юзеры без telegram_id считаются как один аккаунт = одна
    подписка.

    Сравнивает результат с двумя настройками:
      • ``violations_hwid_max_accounts``  — макс. разных аккаунтов на один HWID
      • ``violations_hwid_max_per_account`` — макс. подписок одного аккаунта на HWID
    """

    def __init__(self, db_service: DatabaseService):
        self.db = db_service

    async def analyze(self, user_uuid: str, prefetched_shared: Optional[List[Dict[str, Any]]] = None) -> HwidScore:
        """Проверить, используются ли HWID пользователя на других аккаунтах."""
        try:
            shared = prefetched_shared if prefetched_shared is not None else await self.db.get_shared_hwids_for_user(user_uuid)
        except Exception as e:
            logger.warning("HWID cross-account check failed for %s: %s", user_uuid, e)
            return HwidScore(score=0.0, reasons=[])

        if not shared:
            return HwidScore(score=0.0, reasons=[])

        from shared.config_service import config_service

        max_accounts = config_service.get("violations_hwid_max_accounts", 2)
        max_per_account = config_service.get("violations_hwid_max_per_account", 10)
        try:
            max_accounts = int(max_accounts)
        except (TypeError, ValueError):
            max_accounts = 2
        try:
            max_per_account = int(max_per_account)
        except (TypeError, ValueError):
            max_per_account = 10

        self_tg_id = shared[0].get("self_telegram_id") if shared else None

        # account_key: telegram_id для известных, ('uuid', <uuid>) для NULL — каждый «безыменный» UUID = свой аккаунт.
        def _account_key(uid: str, tg_id: Optional[int]) -> Any:
            return ("tg", tg_id) if tg_id is not None else ("uuid", uid)

        # uuids_by_account_global: { account_key: set(uuid) } — собираем все UUID каждого аккаунта по всем HWID
        uuids_by_account_global: Dict[Any, set] = {}
        uuids_by_account_global.setdefault(_account_key(user_uuid, self_tg_id), set()).add(user_uuid)

        # Для каждого HWID — какие аккаунты на нём сидят и сколько UUID
        worst_hwid_info: Optional[Dict[str, Any]] = None  # для отчёта
        worst_per_account_violation: Optional[Dict[str, Any]] = None
        max_distinct_accounts_per_hwid = 1
        max_uuids_in_account_per_hwid = 1

        all_other_uuids: set = set()
        all_other_usernames: List[str] = []
        matched_details: List[Dict[str, Any]] = []
        seen_other_uuid: set = set()

        for group in shared:
            hwid_value = group.get("hwid", "")
            uuids_by_account_local: Dict[Any, set] = {}
            uuids_by_account_local.setdefault(_account_key(user_uuid, self_tg_id), set()).add(user_uuid)

            for user in group.get("other_users", []):
                uid = user["uuid"]
                tg = user.get("telegram_id")
                key = _account_key(uid, tg)
                uuids_by_account_global.setdefault(key, set()).add(uid)
                uuids_by_account_local.setdefault(key, set()).add(uid)

                if uid not in seen_other_uuid:
                    seen_other_uuid.add(uid)
                    all_other_uuids.add(uid)
                    all_other_usernames.append(user.get("username") or uid[:8])
                    matched_details.append({
                        "uuid": uid,
                        "username": user.get("username") or uid[:8],
                        "hwid": hwid_value,
                        "status": user.get("status", "unknown"),
                        "telegram_id": tg,
                    })

            distinct_accounts = len(uuids_by_account_local)
            if distinct_accounts > max_distinct_accounts_per_hwid:
                max_distinct_accounts_per_hwid = distinct_accounts
                worst_hwid_info = {
                    "hwid": hwid_value,
                    "distinct_accounts": distinct_accounts,
                }

            for key, uids in uuids_by_account_local.items():
                if len(uids) > max_uuids_in_account_per_hwid:
                    max_uuids_in_account_per_hwid = len(uids)
                    worst_per_account_violation = {
                        "hwid": hwid_value,
                        "account_key": key,
                        "uuid_count": len(uids),
                    }

        distinct_accounts_global = len(uuids_by_account_global)
        other_count = len(all_other_uuids)
        shared_hwid_count = len(shared)

        # Проверка порогов
        accounts_threshold_hit = max_distinct_accounts_per_hwid > max_accounts
        per_account_threshold_hit = (
            max_per_account > 0 and max_uuids_in_account_per_hwid > max_per_account
        )

        if not accounts_threshold_hit and not per_account_threshold_hit:
            return HwidScore(
                score=0.0,
                reasons=[],
                shared_hwids_count=shared_hwid_count,
                other_accounts_count=other_count,
                other_accounts=all_other_usernames[:10],
                matched_details=matched_details[:20],
            )

        # Скоринг — чем сильнее превышение порога, тем выше
        score = 0.0
        reasons: List[str] = []

        if accounts_threshold_hit:
            overflow = max_distinct_accounts_per_hwid - max_accounts
            if overflow >= 3:
                score = max(score, 100.0)
            elif overflow >= 1:
                score = max(score, 85.0)
            else:
                score = max(score, 75.0)
            usernames_str = ", ".join(all_other_usernames[:5])
            if len(all_other_usernames) > 5:
                usernames_str += f" (+{len(all_other_usernames) - 5})"
            reasons.append(
                f"HWID делят {max_distinct_accounts_per_hwid} разных аккаунтов "
                f"(порог: {max_accounts}): {usernames_str}"
            )

        if per_account_threshold_hit:
            score = max(score, 85.0)
            reasons.append(
                f"У одного аккаунта {max_uuids_in_account_per_hwid} подписок на одном HWID "
                f"(порог: {max_per_account}) — возможный абуз мультитарифа"
            )

        if shared_hwid_count > 1:
            reasons.append(f"{shared_hwid_count} HWID используются совместно")

        return HwidScore(
            score=min(score, 100.0),
            reasons=reasons,
            shared_hwids_count=shared_hwid_count,
            other_accounts_count=distinct_accounts_global - 1,  # «другие» аккаунты, не подписки
            other_accounts=all_other_usernames[:10],
            matched_details=matched_details[:20],
            per_account_abuse=per_account_threshold_hit,
        )


