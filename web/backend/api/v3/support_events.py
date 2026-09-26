"""Обращения клиентов во внешнюю поддержку — для перепроверки отложенных шагов.

Клиент может писать не в тикеты Bedolaga, а в отдельный бот или helpdesk.
Интеграция сообщает сюда факт обращения, и отложенная мера по его нарушению
(шаг автоматизации с проверкой поддержки) не применится — решит оператор.
Текст переписки не нужен: достаточно, кто и когда.
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from web.backend.api.v3.deps import ApiKeyUser, require_scope

router = APIRouter()

# metadata хранится как есть и ничем не читается — большой объём только раздул бы таблицу
_MAX_METADATA_BYTES = 4096


class SupportIdentity(BaseModel):
    user_uuid: Optional[UUID] = None
    telegram_id: Optional[int] = Field(None, gt=0)
    email: Optional[str] = Field(None, max_length=320)
    username: Optional[str] = Field(None, max_length=200)

    @model_validator(mode="after")
    def require_identity(self):
        if not any((self.user_uuid, self.telegram_id, self.email, self.username)):
            raise ValueError("At least one user identifier is required")
        return self


class SupportEvent(BaseModel):
    source: str = Field(..., min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    kind: str = Field("message", min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    occurred_at: Optional[datetime] = None
    user: SupportIdentity
    ticket_id: Optional[str] = Field(None, max_length=200)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def limit_metadata(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        if len(json.dumps(value, default=str).encode()) > _MAX_METADATA_BYTES:
            raise ValueError(f"metadata is limited to {_MAX_METADATA_BYTES} bytes")
        return value


class SupportEventResult(BaseModel):
    accepted: bool = True
    duplicate: bool = False


@router.post("/support-events", response_model=SupportEventResult, status_code=202)
async def create_support_event(
    body: SupportEvent,
    api_key: ApiKeyUser = Depends(require_scope("enforcement:support")),
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=1, max_length=200),
):
    """Записать обращение клиента — его учтёт перепроверка отложенного шага."""
    occurred_at = body.occurred_at or datetime.now(timezone.utc)
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=timezone.utc)
    if occurred_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise HTTPException(status_code=422, detail="occurred_at cannot be in the future")

    identity = body.user
    conditions, args = [], []

    def add(condition: str, value: Any) -> None:
        args.append(value)
        conditions.append(condition.replace("?", f"${len(args)}"))

    if identity.user_uuid:
        add("uuid = ?::uuid", str(identity.user_uuid))
    if identity.telegram_id:
        add("telegram_id = ?", identity.telegram_id)
    if identity.email:
        add("LOWER(email) = LOWER(?)", identity.email.strip())
    if identity.username:
        add("LOWER(username) = LOWER(?)", identity.username.strip().lstrip("@"))

    from shared.database import db_service
    async with db_service.acquire() as conn:
        async with conn.transaction():
            duplicate = await conn.fetchval(
                "SELECT 1 FROM external_support_events WHERE api_key_id=$1 AND idempotency_key=$2",
                api_key.key_id, idempotency_key,
            )
            if duplicate:
                return SupportEventResult(duplicate=True)

            rows = await conn.fetch(
                "SELECT uuid::text AS uuid, telegram_id FROM users WHERE "
                + " AND ".join(conditions) + " LIMIT 2",
                *args,
            )
            if not rows:
                raise HTTPException(status_code=404, detail="User not found")
            if len(rows) != 1:
                raise HTTPException(status_code=409, detail="User identity is ambiguous")

            row = rows[0]
            payload = {"ticket_id": body.ticket_id, "metadata": body.metadata}
            inserted = await conn.fetchval(
                "INSERT INTO external_support_events "
                "(api_key_id,idempotency_key,source,kind,user_uuid,telegram_id,occurred_at,payload) "
                "VALUES ($1,$2,$3,$4,$5::uuid,$6,$7,$8::jsonb) "
                "ON CONFLICT (api_key_id,idempotency_key) DO NOTHING RETURNING id",
                api_key.key_id, idempotency_key, body.source, body.kind,
                row["uuid"], row["telegram_id"], occurred_at,
                json.dumps(payload, default=str),
            )
            return SupportEventResult(duplicate=inserted is None)
