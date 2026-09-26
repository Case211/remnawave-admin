"""API key management endpoints."""
import ipaddress
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from web.backend.api.deps import AdminUser, require_permission
from web.backend.core.errors import api_error, E

logger = logging.getLogger(__name__)
router = APIRouter()

# Область ключа → право, которое должно быть у создателя. Ключ не может
# дать больше, чем есть у админа: иначе право «создавать ключи» превращалось
# в полный доступ ко всем юзерам и нодам.
SCOPE_PERMISSION = {
    "users:read": ("users", "view"),
    "users:write": ("users", "edit"),
    "users:delete": ("users", "delete"),
    "nodes:read": ("nodes", "view"),
    "nodes:write": ("nodes", "edit"),
    "nodes:token": ("nodes", "edit"),
    "hosts:read": ("hosts", "view"),
    "bulk:write": ("users", "bulk_operations"),
    "stats:read": ("analytics", "view"),
    "violations:read": ("violations", "view"),
    # Обращение клиента останавливает отложенную меру — то же право, что решать по нарушениям
    "enforcement:support": ("violations", "resolve"),
}
# Ключ работает по всем юзерам — такие области только админу без ограничения видимости
_ALL_USERS_SCOPES = {
    "users:read", "users:write", "users:delete", "bulk:write",
    "violations:read", "enforcement:support",
}

AVAILABLE_SCOPES = [
    "users:read",
    "users:write",
    "users:delete",
    "nodes:read",
    "nodes:write",
    "nodes:token",
    "hosts:read",
    "bulk:write",
    "stats:read",
    "violations:read",
    "enforcement:support",
]


@router.get("/status")
async def api_status(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """Check if external API v3 is enabled."""
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    return {
        "external_api_enabled": settings.external_api_enabled,
        "external_api_docs": settings.external_api_docs,
    }


# ── Schemas ──────────────────────────────────────────────────────

async def _check_scopes_allowed(admin: AdminUser, scopes: List[str]) -> None:
    """Каждую область ключа админ должен иметь сам."""
    from web.backend.core.rbac import get_visible_user_uuids
    full_access = admin.account_id is None or admin.role == "superadmin"
    for scope in scopes:
        if scope not in AVAILABLE_SCOPES:
            raise api_error(400, E.INVALID_ACTION, f"Unknown scope: {scope}")
        resource, action = SCOPE_PERMISSION[scope]
        if not full_access and not admin.has_permission(resource, action):
            raise api_error(403, E.SCOPE_NOT_ALLOWED, f"Scope {scope} needs {resource}:{action}")
    if _ALL_USERS_SCOPES.intersection(scopes) and await get_visible_user_uuids(admin) is not None:
        raise api_error(403, E.SCOPE_NOT_ALLOWED, "User scopes need unrestricted user access")


def _parse_expiry(value: Optional[str]) -> Optional[datetime]:
    """Срок ключа: дата «до» — до конца дня по часам панели; в прошлом — отказ."""
    if not value:
        return None
    from shared import timefmt
    try:
        expires = timefmt.parse_filter(value, end=True)
    except ValueError:
        raise api_error(400, E.INVALID_INPUT, "Invalid expires_at format")
    if expires is None or expires <= datetime.now(timezone.utc):
        raise api_error(400, E.INVALID_INPUT, "expires_at must be in the future")
    return expires


class ApiKeyCreate(BaseModel):
    name: str
    scopes: List[str] = []
    expires_at: Optional[str] = None
    description: Optional[str] = None
    allowed_ips: Optional[List[str]] = None
    user_squads: Optional[List[str]] = None
    user_tag: Optional[str] = Field(None, max_length=64)


_KEY_COLUMNS = (
    "id, name, key_prefix, scopes, is_active, expires_at, last_used_at, created_by_username, "
    "description, created_at, allowed_ips, user_squads, user_tag, prev_valid_until"
)


def _serialize(row) -> dict:
    d = dict(row)
    for arr in ("scopes", "allowed_ips", "user_squads"):
        d[arr] = list(d[arr]) if d.get(arr) else []
    for dt in ("expires_at", "last_used_at", "created_at", "prev_valid_until"):
        if hasattr(d.get(dt), "isoformat"):
            d[dt] = d[dt].isoformat()
    # Старый ключ после ротации уже не действует — не показываем срок
    if d.get("prev_valid_until") and d["prev_valid_until"] < datetime.now(timezone.utc).isoformat():
        d["prev_valid_until"] = None
    return d


def _normalize_ips(ips: Optional[List[str]]) -> Optional[List[str]]:
    """Адреса и подсети ключа: проверка формата; пустой список — любой адрес."""
    if not ips:
        return None
    result = []
    for raw in ips:
        value = raw.strip()
        if not value:
            continue
        try:
            result.append(str(ipaddress.ip_network(value, strict=False)))
        except ValueError:
            raise api_error(400, E.INVALID_INPUT, f"Invalid IP or subnet: {value}")
    return result or None


class ApiKeyResponse(BaseModel):
    id: int
    name: str
    key_prefix: str
    scopes: List[str]
    is_active: bool
    expires_at: Optional[str] = None
    last_used_at: Optional[str] = None
    created_by_username: Optional[str] = None
    description: Optional[str] = None
    created_at: str
    allowed_ips: List[str] = []
    user_squads: List[str] = []
    user_tag: Optional[str] = None
    # До какого момента ещё принимается прошлый ключ после ротации
    prev_valid_until: Optional[str] = None


class ApiKeyCreated(ApiKeyResponse):
    raw_key: str


class ApiKeyUpdate(BaseModel):
    name: Optional[str] = None
    scopes: Optional[List[str]] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None
    # Пустой список / пустая строка — снять ограничение
    allowed_ips: Optional[List[str]] = None
    user_squads: Optional[List[str]] = None
    user_tag: Optional[str] = Field(None, max_length=64)


class ApiKeyRotate(BaseModel):
    # Сколько часов ещё принимать старый ключ; 0 — сразу недействителен
    grace_hours: int = Field(0, ge=0, le=72)


# ── Endpoints ────────────────────────────────────────────────────

@router.get("/", response_model=List[ApiKeyResponse])
async def list_api_keys(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """List all API keys (without hashes)."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []

    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {_KEY_COLUMNS} "
            "FROM api_keys ORDER BY created_at DESC"
        )

    return [ApiKeyResponse(**_serialize(r)) for r in rows]


@router.get("/scopes")
async def list_available_scopes(
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """List all available API scopes."""
    return {"scopes": AVAILABLE_SCOPES}


@router.post("/", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    body: ApiKeyCreate,
    admin: AdminUser = Depends(require_permission("api_keys", "create")),
):
    """Create a new API key. The raw key is returned only once."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    await _check_scopes_allowed(admin, body.scopes)
    expires_at = _parse_expiry(body.expires_at)

    admin_id = admin.account_id
    admin_username = admin.username or str(admin.telegram_id)

    from web.backend.core.api_key_auth import create_api_key_record
    raw_key, record = await create_api_key_record(
        name=body.name,
        scopes=body.scopes,
        admin_id=admin_id,
        admin_username=admin_username,
        expires_at=expires_at,
        description=body.description,
        allowed_ips=_normalize_ips(body.allowed_ips),
        user_squads=[s for s in (body.user_squads or []) if s] or None,
        user_tag=(body.user_tag or "").strip() or None,
    )

    return ApiKeyCreated(raw_key=raw_key, **{
        k: v for k, v in _serialize(record).items()
        if k in ApiKeyResponse.model_fields
    })


@router.patch("/{key_id}", response_model=ApiKeyResponse)
async def update_api_key(
    key_id: int,
    body: ApiKeyUpdate,
    admin: AdminUser = Depends(require_permission("api_keys", "edit")),
):
    """Update API key name, scopes, or active status."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    updates = body.model_dump(exclude_unset=True)
    for key in ("name", "scopes", "is_active"):
        if key in updates and updates[key] is None:
            del updates[key]
    if not updates:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    if "scopes" in updates:
        await _check_scopes_allowed(admin, updates["scopes"])
    if "allowed_ips" in updates:
        updates["allowed_ips"] = _normalize_ips(updates["allowed_ips"])
    if "user_squads" in updates:
        updates["user_squads"] = [s for s in (updates["user_squads"] or []) if s] or None
    if "user_tag" in updates:
        updates["user_tag"] = (updates["user_tag"] or "").strip() or None

    set_clauses = []
    params = []
    idx = 1
    for key, val in updates.items():
        set_clauses.append(f"{key} = ${idx}")
        params.append(val)
        idx += 1
    params.append(key_id)

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE api_keys SET {', '.join(set_clauses)}, updated_at = NOW() "
            f"WHERE id = ${idx} RETURNING {_KEY_COLUMNS}",
            *params,
        )

    if not row:
        raise api_error(404, E.API_KEY_NOT_FOUND)

    return ApiKeyResponse(**_serialize(row))


@router.delete("/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    admin: AdminUser = Depends(require_permission("api_keys", "delete")),
):
    """Delete an API key."""
    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    async with db_service.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM api_keys WHERE id = $1", key_id,
        )
    if result == "DELETE 0":
        raise api_error(404, E.API_KEY_NOT_FOUND)


@router.post("/{key_id}/rotate", response_model=ApiKeyCreated)
async def rotate_api_key(
    key_id: int,
    body: Optional[ApiKeyRotate] = None,
    admin: AdminUser = Depends(require_permission("api_keys", "edit")),
):
    """Generate a new secret for an existing key while preserving id/name/scopes.

    grace_hours = 0 — старый ключ перестаёт работать сразу (утечка). Больше
    нуля — старый ключ принимается ещё столько часов, чтобы интеграция успела
    переключиться без простоя.
    """
    grace_hours = body.grace_hours if body else 0
    import hashlib
    import secrets
    from web.backend.core.api_key_auth import API_KEY_PREFIX

    from shared.database import db_service
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    random_part = secrets.token_urlsafe(32)
    raw_key = f"{API_KEY_PREFIX}{random_part}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    key_prefix = raw_key[:12]

    async with db_service.acquire() as conn:
        row = await conn.fetchrow(
            "UPDATE api_keys SET "
            "prev_key_hash = CASE WHEN $4 > 0 THEN key_hash END, "
            "prev_valid_until = CASE WHEN $4 > 0 THEN NOW() + ($4 || ' hours')::interval END, "
            "key_hash = $1, key_prefix = $2, "
            "last_used_at = NULL, updated_at = NOW() "
            "WHERE id = $3 "
            f"RETURNING {_KEY_COLUMNS}",
            key_hash, key_prefix, key_id, grace_hours,
        )
    if not row:
        raise api_error(404, E.API_KEY_NOT_FOUND)
    return ApiKeyCreated(raw_key=raw_key, **_serialize(row))


@router.get("/{key_id}/requests")
async def list_key_requests(
    key_id: int,
    limit: int = Query(50, ge=1, le=200),
    admin: AdminUser = Depends(require_permission("api_keys", "view")),
):
    """Последние запросы ключа: метод, путь, код ответа, адрес, время."""
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, method, path, status_code, ip_address, duration_ms, created_at "
            "FROM api_key_requests WHERE key_id = $1 ORDER BY id DESC LIMIT $2",
            key_id, limit,
        )
    return [{**dict(r), "created_at": r["created_at"].isoformat()} for r in rows]
