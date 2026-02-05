"""Violation schemas for web panel API."""
from pydantic import BaseModel
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
