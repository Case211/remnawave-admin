"""Common schemas for web panel API."""
from typing import Generic, List, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""

    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int


class ErrorResponse(BaseModel):
    """Error response."""

    detail: str
    code: Optional[str] = None


class SuccessResponse(BaseModel):
    """Success response."""

    status: str = "ok"
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    services: Optional[dict] = None
