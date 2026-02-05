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
]
