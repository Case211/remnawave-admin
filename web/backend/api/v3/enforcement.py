"""Vendor-neutral support events for delayed enforcement."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, model_validator

from shared.database import db_service
from web.backend.api.v3.deps import ApiKeyUser, require_scope
from web.backend.core.enforcement_workflow import ACTIVE_STATUSES


router = APIRouter()


class UserIdentity(BaseModel):
    uuid: UUID | None = None
    telegram_id: int | None = None
    email: str | None = Field(default=None, max_length=320)
    username: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def require_identity(self):
        if not any((self.uuid, self.telegram_id, self.email, self.username)):
            raise ValueError("At least one user identity is required")
        return self


class TicketReference(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    external_id: str = Field(min_length=1, max_length=200)
    url: str | None = Field(default=None, max_length=2000)


class SupportEvent(BaseModel):
    event: Literal["customer_contacted"] = "customer_contacted"
    user: UserIdentity
    ticket: TicketReference
    occurred_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


@router.post("/support-events")
async def support_event(
    body: SupportEvent,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _: ApiKeyUser = Depends(require_scope("enforcement:support")),
) -> dict[str, Any]:
    """Pause pending cases. Duplicate provider events are side-effect free."""
    if not db_service.is_connected:
        raise HTTPException(status_code=503, detail="Database is unavailable")
    external_id = (idempotency_key or body.ticket.external_id).strip()
    if not external_id or len(external_id) > 200:
        raise HTTPException(status_code=400, detail="Invalid Idempotency-Key")

    event = {
        "event": body.event,
        "user": body.user.model_dump(mode="json"),
        "ticket": body.ticket.model_dump(mode="json"),
        "occurred_at": (body.occurred_at or datetime.now(timezone.utc)).isoformat(),
        "metadata": body.metadata,
    }
    conditions: list[str] = []
    args: list[Any] = []
    for sql, value in (
        ("uuid::text=${i}", body.user.uuid),
        ("telegram_id::text=${i}", body.user.telegram_id),
        ("LOWER(COALESCE(email,''))=LOWER(${i})", body.user.email),
        ("LOWER(username)=LOWER(${i})", body.user.username),
    ):
        if value is not None and str(value).strip():
            args.append(str(value).strip())
            conditions.append(sql.format(i=len(args)))

    async with db_service.acquire() as conn:
        async with conn.transaction():
            stored = await conn.fetchrow(
                "INSERT INTO enforcement_support_events "
                "(provider, external_id, event_type, payload) VALUES ($1,$2,$3,$4::jsonb) "
                "ON CONFLICT (provider, external_id) DO NOTHING RETURNING id",
                body.ticket.provider, external_id, body.event, json.dumps(event),
            )
            if not stored:
                previous = await conn.fetchrow(
                    "SELECT matched_users, paused_cases FROM enforcement_support_events "
                    "WHERE provider=$1 AND external_id=$2", body.ticket.provider, external_id,
                )
                return {"accepted": True, "duplicate": True,
                        "matched_users": int(previous["matched_users"] or 0),
                        "paused_cases": int(previous["paused_cases"] or 0)}

            users = await conn.fetch(
                "SELECT DISTINCT uuid::text AS uuid FROM users WHERE " + " OR ".join(conditions), *args,
            )
            user_uuids = {str(row["uuid"]) for row in users}
            paused: list[Any] = []
            if len(user_uuids) == 1:
                paused = await conn.fetch(
                    "UPDATE enforcement_cases SET status='paused_for_support', "
                    "resolution='support_contacted', metadata=metadata || "
                    "jsonb_build_object('support_event',$2::jsonb), updated_at=NOW() "
                    "WHERE user_uuid=$1::uuid AND status=ANY($3::text[]) "
                    "AND COALESCE((policy_snapshot->>'pause_for_support')::boolean,true) RETURNING id",
                    next(iter(user_uuids)), json.dumps(event), list(ACTIVE_STATUSES),
                )
            await conn.execute(
                "UPDATE enforcement_support_events SET matched_users=$2, paused_cases=$3 WHERE id=$1",
                stored["id"], len(user_uuids), len(paused),
            )
    return {"accepted": True, "duplicate": False, "matched_users": len(user_uuids),
            "paused_cases": len(paused), "case_ids": [int(row["id"]) for row in paused]}
