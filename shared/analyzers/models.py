"""Violation detection data models — scores, actions, classifications."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class ViolationAction(Enum):
    NO_ACTION = "no_action"
    MONITOR = "monitor"
    WARN = "warn"
    SOFT_BLOCK = "soft_block"
    TEMP_BLOCK = "temp_block"
    HARD_BLOCK = "hard_block"


# Как называть действие человеку. Глаголами и от лица администратора:
# детектор ничего не исполняет, он советует — сам он трогает пользователя
# только на hard_block и только при включённой автоблокировке.
#
# SOFT_BLOCK исторически звался «мягкой блокировкой (ограничение скорости)»,
# хотя ограничивать скорость проект не умеет: название обещало механизм,
# которого нет, и читалось как уже наложенное ограничение.
ACTION_LABELS = {
    "no_action": "ничего не требуется",
    "monitor": "наблюдать",
    "warn": "предупредить",
    "soft_block": "разобраться вручную",
    "temp_block": "заблокировать временно",
    "hard_block": "заблокировать",
}

# Ключи анализаторов в breakdown ViolationScore. Совпадают с тем, что
# понимает excluded_analyzers в violation_whitelist, — на этом держится
# кнопка частичного исключения под уведомлением.
VIOLATION_ANALYZERS = ("temporal", "geo", "asn", "profile", "device", "hwid", "user_agent")


def _analyzer_score(entry: Any) -> float:
    """Вклад анализатора. Breakdown приходит и датаклассами, и словарями."""
    if isinstance(entry, dict):
        value = entry.get("score", 0)
    else:
        value = getattr(entry, "score", 0)
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def dominant_analyzer(breakdown: Optional[Dict[str, Any]]) -> Optional[str]:
    """Анализатор, давший наибольший вклад в скор, — по нему и предлагаем исключение.

    Нужен, чтобы кнопка под уведомлением вела в тот же разрез, что и само
    нарушение: сработал HWID — предлагаем не проверять по HWID, а не
    отключать человеку всю защиту разом. Ничего не набрало — None, тогда
    останется только полный белый список.
    """
    if not breakdown:
        return None
    scored = [(key, _analyzer_score(breakdown.get(key))) for key in VIOLATION_ANALYZERS if key in breakdown]
    if not scored:
        return None
    key, top = max(scored, key=lambda pair: pair[1])
    return key if top > 0 else None


@dataclass
class TemporalScore:
    score: float
    reasons: List[str]
    simultaneous_connections_count: int = 0
    rapid_switches_count: int = 0
    overlap_duration_minutes: float = 0.0
    # Явный массовый шаринг: источников сильно больше порога, в который уже
    # заложены буферы на смену сети и CGNAT. Детектор не гасит такой сигнал
    # мобильными объяснениями.
    strong_sharing: bool = False


@dataclass
class GeoScore:
    score: float
    reasons: List[str]
    countries: Set[str]
    cities: Set[str]
    impossible_travel_detected: bool = False


@dataclass
class ASNScore:
    score: float
    reasons: List[str]
    asn_types: Set[str]
    is_mobile_carrier: bool = False
    is_datacenter: bool = False
    is_vpn: bool = False


@dataclass
class ProfileScore:
    score: float
    reasons: List[str]
    deviation_from_baseline: float = 0.0


@dataclass
class DeviceScore:
    score: float
    reasons: List[str]
    unique_fingerprints_count: int = 0
    different_os_count: int = 0
    os_list: List[str] = None
    client_list: List[str] = None


@dataclass
class HwidScore:
    score: float
    reasons: List[str]
    shared_hwids_count: int = 0
    other_accounts_count: int = 0
    other_accounts: List[str] = None
    matched_details: List[Dict[str, Any]] = None
    per_account_abuse: bool = False  # абуз мультитарифа (один telegram_id, N подписок на HWID)
    max_accounts_per_hwid: int = 1  # макс. разных аккаунтов на одном HWID (включая самого юзера)
    max_active_trials_per_hwid: int = 0  # макс. РАЗНЫХ аккаунтов с живым триалом на одном HWID
    # Макс. пробных подписок одного аккаунта на одном HWID, считая истёкшие —
    # единственный срез, который не обойти привязкой своего telegram_id к новой
    # подписке (после неё аккаунт снова «один», и остальные проверки слепнут)
    max_trial_subs_per_hwid: int = 0
    # UUID'ы чужих подписок с живым триалом на тех HWID, где порог превышен —
    # соучастники накрутки, блокировать их надо вместе с проверяемым
    active_trial_accomplices: List[str] = None


class UserAgentClassification(Enum):
    VALID = "valid"
    LINK_IN_UA = "link_in_ua"
    BOT_LIBRARY = "bot_library"
    STUB = "stub"
    EMPTY = "empty"
    UNKNOWN = "unknown"


@dataclass
class SuspiciousAgent:
    request_id: Optional[int]
    user_agent: str
    request_ip: Optional[str]
    request_at: Optional[str]
    classification: str


@dataclass
class UserAgentScore:
    score: float
    reasons: List[str]
    suspicious_agents: List[SuspiciousAgent] = field(default_factory=list)
    has_link_in_ua: bool = False
    has_bot_library: bool = False
    valid_count: int = 0
    total_analyzed: int = 0


@dataclass
class ViolationScore:
    total: float
    breakdown: Dict[str, Any]
    recommended_action: ViolationAction
    confidence: float
    reasons: List[str]
