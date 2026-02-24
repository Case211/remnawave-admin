"""Pydantic schemas for Bedolaga integration endpoints."""

from datetime import datetime
from typing import Any, Optional, List

from pydantic import BaseModel, Field


# ── Sync & Health ─────────────────────────────────────────────────

class BedolagaStatusResponse(BaseModel):
    enabled: bool
    connected: bool
    base_url: Optional[str] = None
    bot_version: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    sync_status: Optional[str] = None


class BedolagaSyncStatusResponse(BaseModel):
    entity: str
    last_sync_at: Optional[datetime] = None
    status: str = "never"
    records_synced: int = 0
    error_message: Optional[str] = None


class BedolagaSyncResult(BaseModel):
    entities: List[BedolagaSyncStatusResponse]
    triggered_at: datetime


# ── Stats Snapshot ────────────────────────────────────────────────

class BedolagaOverviewResponse(BaseModel):
    total_users: int = 0
    active_subscriptions: int = 0
    total_revenue: float = 0.0
    total_transactions: int = 0
    open_tickets: int = 0
    snapshot_at: Optional[datetime] = None
    raw_data: Optional[dict] = None


# ── Users (synced) ────────────────────────────────────────────────

class BedolagaUserResponse(BaseModel):
    id: int
    telegram_id: Optional[int] = None
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    status: Optional[str] = None
    balance_rubles: float = 0.0
    referral_code: Optional[str] = None
    has_had_paid_subscription: bool = False
    created_at: Optional[datetime] = None
    last_activity: Optional[datetime] = None
    synced_at: Optional[datetime] = None


class BedolagaUserListResponse(BaseModel):
    items: List[BedolagaUserResponse]
    total: int
    limit: int
    offset: int


# ── Subscriptions (synced) ────────────────────────────────────────

class BedolagaSubscriptionResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_telegram_id: Optional[int] = None
    plan_name: Optional[str] = None
    status: Optional[str] = None
    is_trial: bool = False
    started_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    traffic_limit_bytes: Optional[int] = None
    traffic_used_bytes: Optional[int] = None
    payment_amount: Optional[float] = None
    payment_provider: Optional[str] = None
    synced_at: Optional[datetime] = None


class BedolagaSubscriptionListResponse(BaseModel):
    items: List[BedolagaSubscriptionResponse]
    total: int
    limit: int
    offset: int


# ── Transactions (synced) ─────────────────────────────────────────

class BedolagaTransactionResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_telegram_id: Optional[int] = None
    amount: float = 0.0
    currency: Optional[str] = None
    provider: Optional[str] = None
    status: Optional[str] = None
    type: Optional[str] = None
    created_at: Optional[datetime] = None
    synced_at: Optional[datetime] = None


class BedolagaTransactionListResponse(BaseModel):
    items: List[BedolagaTransactionResponse]
    total: int
    limit: int
    offset: int


class BedolagaTransactionStatsResponse(BaseModel):
    total_amount: float = 0.0
    total_count: int = 0
    by_provider: Optional[dict] = None
    by_day: Optional[List[dict]] = None
    period_from: Optional[datetime] = None
    period_to: Optional[datetime] = None


# ── Tickets (real-time) ──────────────────────────────────────────

class BedolagaTicketResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    user_telegram_id: Optional[int] = None
    username: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    subject: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    messages: Optional[List[dict]] = None


class BedolagaTicketListResponse(BaseModel):
    items: List[BedolagaTicketResponse]
    total: int
    limit: int
    offset: int


class BedolagaTicketStatusUpdate(BaseModel):
    status: str = Field(..., description="New ticket status")


class BedolagaTicketPriorityUpdate(BaseModel):
    priority: str = Field(..., description="New ticket priority")


class BedolagaTicketReply(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)


# ── Promo Groups (real-time) ─────────────────────────────────────

class BedolagaPromoGroupResponse(BaseModel):
    id: int
    name: Optional[str] = None
    description: Optional[str] = None
    member_count: int = 0
    created_at: Optional[datetime] = None
    raw_data: Optional[dict] = None


class BedolagaPromoGroupListResponse(BaseModel):
    items: List[BedolagaPromoGroupResponse]
    total: int
    limit: int
    offset: int


class BedolagaPromoGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class BedolagaPromoGroupUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None


# ── Promo Codes (real-time) ──────────────────────────────────────

class BedolagaPromoCodeResponse(BaseModel):
    id: int
    code: Optional[str] = None
    is_active: bool = True
    discount_percent: Optional[float] = None
    discount_amount: Optional[float] = None
    max_uses: Optional[int] = None
    used_count: int = 0
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    raw_data: Optional[dict] = None


class BedolagaPromoCodeListResponse(BaseModel):
    items: List[BedolagaPromoCodeResponse]
    total: int
    limit: int
    offset: int


class BedolagaPromoCodeCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=50)
    discount_percent: Optional[float] = Field(None, ge=0, le=100)
    discount_amount: Optional[float] = Field(None, ge=0)
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[datetime] = None


class BedolagaPromoCodeUpdate(BaseModel):
    is_active: Optional[bool] = None
    discount_percent: Optional[float] = Field(None, ge=0, le=100)
    discount_amount: Optional[float] = Field(None, ge=0)
    max_uses: Optional[int] = Field(None, ge=1)
    expires_at: Optional[datetime] = None


# ── Polls (real-time) ────────────────────────────────────────────

class BedolagaPollResponse(BaseModel):
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    is_active: bool = False
    questions: Optional[List[dict]] = None
    created_at: Optional[datetime] = None
    raw_data: Optional[dict] = None


class BedolagaPollListResponse(BaseModel):
    items: List[BedolagaPollResponse]
    total: int
    limit: int
    offset: int


# ── Partners (real-time) ─────────────────────────────────────────

class BedolagaPartnerResponse(BaseModel):
    user_id: int
    username: Optional[str] = None
    telegram_id: Optional[int] = None
    referral_count: int = 0
    total_earned: float = 0.0
    commission_rate: Optional[float] = None
    raw_data: Optional[dict] = None


class BedolagaPartnerListResponse(BaseModel):
    items: List[BedolagaPartnerResponse]
    total: int
    limit: int
    offset: int


class BedolagaPartnerStatsResponse(BaseModel):
    total_referrers: int = 0
    total_referrals: int = 0
    total_earned: float = 0.0
    daily_stats: Optional[List[dict]] = None
    raw_data: Optional[dict] = None


# ── Revenue Analytics (computed from synced data) ─────────────────

class BedolagaRevenueResponse(BaseModel):
    total_revenue: float = 0.0
    revenue_today: float = 0.0
    revenue_week: float = 0.0
    revenue_month: float = 0.0
    by_provider: Optional[dict] = None
    daily_chart: Optional[List[dict]] = None


# ── Generic passthrough ──────────────────────────────────────────

class BedolagaProxyResponse(BaseModel):
    """Generic response for passthrough proxy endpoints."""
    data: Any = None
    status: str = "ok"
