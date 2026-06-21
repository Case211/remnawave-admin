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


@dataclass
class TemporalScore:
    score: float
    reasons: List[str]
    simultaneous_connections_count: int = 0
    rapid_switches_count: int = 0
    overlap_duration_minutes: float = 0.0


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
