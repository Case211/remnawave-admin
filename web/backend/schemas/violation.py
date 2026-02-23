"""Violation schemas for web panel API."""
import re
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class ViolationAction(str, Enum):
    """Рекомендуемое действие."""
    NO_ACTION = "no_action"
    MONITOR = "monitor"
    WARN = "warn"
    SOFT_BLOCK = "soft_block"
    TEMP_BLOCK = "temp_block"
    HARD_BLOCK = "hard_block"


class ViolationSeverity(str, Enum):
    """Уровень серьёзности нарушения."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ViolationBase(BaseModel):
    """Базовая модель нарушения."""
    id: int
    user_uuid: str
    username: Optional[str] = None
    email: Optional[str] = None
    telegram_id: Optional[int] = None
    score: float
    recommended_action: str
    confidence: float
    detected_at: datetime


class ViolationListItem(ViolationBase):
    """Элемент списка нарушений."""
    severity: ViolationSeverity = ViolationSeverity.LOW
    action_taken: Optional[str] = None
    notified: bool = False

    @staticmethod
    def get_severity(score: float) -> ViolationSeverity:
        if score >= 80:
            return ViolationSeverity.CRITICAL
        elif score >= 60:
            return ViolationSeverity.HIGH
        elif score >= 40:
            return ViolationSeverity.MEDIUM
        return ViolationSeverity.LOW


class ViolationDetail(ViolationBase):
    """Детальная информация о нарушении."""
    temporal_score: float = 0.0
    geo_score: float = 0.0
    asn_score: float = 0.0
    profile_score: float = 0.0
    device_score: float = 0.0
    hwid_score: float = 0.0
    reasons: List[str] = []
    countries: List[str] = []
    asn_types: List[str] = []
    ips: List[str] = []
    action_taken: Optional[str] = None
    action_taken_at: Optional[datetime] = None
    action_taken_by: Optional[int] = None
    notified_at: Optional[datetime] = None
    raw_data: Optional[Dict[str, Any]] = None


class ViolationListResponse(BaseModel):
    """Ответ списка нарушений."""
    items: List[ViolationListItem]
    total: int
    page: int
    per_page: int
    pages: int


class ViolationStats(BaseModel):
    """Статистика нарушений."""
    total: int
    critical: int
    high: int
    medium: int
    low: int
    unique_users: int
    avg_score: float
    max_score: float
    by_action: Dict[str, int] = {}
    by_country: Dict[str, int] = {}


class ResolveViolationRequest(BaseModel):
    """Запрос на разрешение нарушения."""
    action: str  # ignore, warn, block, etc.
    comment: Optional[str] = None


class ViolationUserSummary(BaseModel):
    """Сводка нарушений пользователя."""
    user_uuid: str
    username: Optional[str] = None
    violations_count: int
    max_score: float
    avg_score: float
    last_violation_at: datetime
    actions: List[str] = []


class IPLookupRequest(BaseModel):
    """Запрос на поиск информации по IP."""
    ips: List[str]


class IPInfo(BaseModel):
    """Информация об IP адресе."""
    ip: str
    asn_org: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    connection_type: Optional[str] = None
    is_vpn: bool = False
    is_proxy: bool = False
    is_hosting: bool = False
    is_mobile: bool = False


class IPLookupResponse(BaseModel):
    """Ответ с информацией по IP адресам."""
    results: Dict[str, IPInfo]


# ── Whitelist ─────────────────────────────────────────────────

VALID_ANALYZERS = {"temporal", "geo", "asn", "profile", "device", "hwid"}


class WhitelistAddRequest(BaseModel):
    """Запрос на добавление пользователя в whitelist."""
    user_uuid: str
    reason: Optional[str] = Field(None, max_length=1000)
    expires_in_days: Optional[int] = Field(None, ge=1, le=3650)  # None = бессрочно
    excluded_analyzers: Optional[List[str]] = Field(
        None,
        description="Список анализаторов для исключения. None = полный whitelist.",
    )

    @field_validator('user_uuid')
    @classmethod
    def validate_uuid(cls, v: str) -> str:
        uuid_re = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)
        if not uuid_re.match(v.strip()):
            raise ValueError('Invalid UUID format')
        return v.strip()

    @field_validator('excluded_analyzers')
    @classmethod
    def validate_analyzers(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            invalid = set(v) - VALID_ANALYZERS
            if invalid:
                raise ValueError(f'Invalid analyzer names: {", ".join(sorted(invalid))}')
            v = sorted(set(v))
        return v


class WhitelistUpdateRequest(BaseModel):
    """Запрос на обновление исключений whitelist."""
    excluded_analyzers: Optional[List[str]] = Field(
        None,
        description="Список анализаторов для исключения. None = полный whitelist.",
    )

    @field_validator('excluded_analyzers')
    @classmethod
    def validate_analyzers(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        if v is not None:
            invalid = set(v) - VALID_ANALYZERS
            if invalid:
                raise ValueError(f'Invalid analyzer names: {", ".join(sorted(invalid))}')
            v = sorted(set(v))
        return v


class WhitelistItem(BaseModel):
    """Элемент whitelist."""
    id: int
    user_uuid: str
    username: Optional[str] = None
    email: Optional[str] = None
    reason: Optional[str] = None
    added_by_username: Optional[str] = None
    added_at: datetime
    expires_at: Optional[datetime] = None
    excluded_analyzers: Optional[List[str]] = None


class WhitelistListResponse(BaseModel):
    """Ответ списка whitelist."""
    items: List[WhitelistItem]
    total: int
