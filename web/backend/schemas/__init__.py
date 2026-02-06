"""Schemas for web panel API."""
from web.backend.schemas.common import (
    PaginatedResponse,
    ErrorResponse,
    SuccessResponse,
    HealthResponse,
)
from web.backend.schemas.auth import (
    TelegramAuthData,
    TokenResponse,
    RefreshRequest,
    AdminInfo,
)
from web.backend.schemas.user import (
    UserBase,
    UserListItem,
    UserDetail,
    UserCreate,
    UserUpdate,
    UserConnection,
)
from web.backend.schemas.node import (
    NodeBase,
    NodeListItem,
    NodeDetail,
    NodeCreate,
    NodeUpdate,
    NodeStats,
)
from web.backend.schemas.host import (
    HostBase,
    HostListItem,
    HostDetail,
    HostCreate,
    HostUpdate,
    HostListResponse,
)
from web.backend.schemas.violation import (
    ViolationAction,
    ViolationSeverity,
    ViolationBase,
    ViolationListItem,
    ViolationDetail,
    ViolationListResponse,
    ViolationStats,
    ViolationUserSummary,
    ResolveViolationRequest,
)

__all__ = [
    # Common
    "PaginatedResponse",
    "ErrorResponse",
    "SuccessResponse",
    "HealthResponse",
    # Auth
    "TelegramAuthData",
    "TokenResponse",
    "RefreshRequest",
    "AdminInfo",
    # User
    "UserBase",
    "UserListItem",
    "UserDetail",
    "UserCreate",
    "UserUpdate",
    "UserConnection",
    # Node
    "NodeBase",
    "NodeListItem",
    "NodeDetail",
    "NodeCreate",
    "NodeUpdate",
    "NodeStats",
    # Host
    "HostBase",
    "HostListItem",
    "HostDetail",
    "HostCreate",
    "HostUpdate",
    "HostListResponse",
    # Violation
    "ViolationAction",
    "ViolationSeverity",
    "ViolationBase",
    "ViolationListItem",
    "ViolationDetail",
    "ViolationListResponse",
    "ViolationStats",
    "ViolationUserSummary",
    "ResolveViolationRequest",
]
