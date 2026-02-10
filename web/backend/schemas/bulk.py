"""Schemas for bulk operations."""
from pydantic import BaseModel, Field
from typing import List, Optional


class BulkUserRequest(BaseModel):
    """Request to perform a bulk operation on multiple users."""
    uuids: List[str] = Field(..., min_length=1, max_length=100)


class BulkOperationError(BaseModel):
    """Details about a single failed operation within a bulk request."""
    uuid: str
    error: str


class BulkOperationResult(BaseModel):
    """Result of a bulk operation."""
    success: int
    failed: int
    errors: List[BulkOperationError] = []
