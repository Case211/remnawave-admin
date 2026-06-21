"""Users API endpoints."""
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Set

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from pydantic import BaseModel, Field

from web.backend.core.errors import api_error, E, ErrorCode
from shared.db_schema import USERS_TABLE
from shared.db_query import select_sql, update_sql
from shared.admin_quota import (
    apply_user_delete_quotas,
    apply_user_reassign_quotas,
    apply_user_reset_traffic_quotas,
    apply_users_delete_quotas_batch,
    apply_users_reassign_quotas_batch,
    apply_users_reset_traffic_quotas_batch,
    fetch_user_quota_data,
    fetch_users_quota_data_batch,
)

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, require_permission, require_quota, AdminUser, get_client_ip
from web.backend.core.api_helper import fetch_users_from_api
from web.backend.core.audit import write_audit_log
from web.backend.core.admin_accounts import get_admin_account_by_id
from web.backend.core.rbac import get_visible_user_uuids, get_scope
from web.backend.core.webhook_security import fire_event
from web.backend.schemas.user import UserListItem, UserDetail, UserCreate, UserUpdate, HwidDevice
from web.backend.schemas.common import PaginatedResponse, SuccessResponse
from web.backend.schemas.bulk import BulkUserRequest, BulkOperationResult, BulkOperationError, BulkReassignRequest
from web.backend.core.rate_limit import limiter, RATE_BULK

logger = logging.getLogger(__name__)

router = APIRouter()


async def _ensure_user_visible(admin: AdminUser, user_uuid: str) -> None:
    """Raise 403 if the admin's access-policy scope hides this user."""
    visible = await get_visible_user_uuids(admin)
    if visible is not None and user_uuid.lower() not in visible:
        raise api_error(403, E.FORBIDDEN)


def _extract_panel_error(exc: Exception) -> Optional[str]:
    """
    Достаёт человекочитаемое описание ошибки из ответа Panel API.
    httpx.HTTPStatusError содержит response.text — Panel пишет туда JSON
    вида `{"message": "...", "errorCode": "..."}`. Парсим аккуратно, иначе
    юзер видит «Internal server error» и нечего смотреть.
    """
    try:
        import httpx
        import json as _json
        if isinstance(exc, httpx.HTTPStatusError):
            body = exc.response.text or ""
            try:
                parsed = _json.loads(body)
                if isinstance(parsed, dict):
                    msg = parsed.get("message") or parsed.get("detail") or parsed.get("error")
                    if isinstance(msg, str) and msg.strip():
                        return msg
            except (ValueError, TypeError):
                pass
            if body:
                return body[:300]
    except Exception:
        return None
    return None


# Known Panel API errorCode → our ErrorCode mapping. Panel returns
# `{"errorCode": "A019", "message": "..."}` for typed errors. We translate
# the typed code into a code the frontend can localize. Anything not in
# this map falls back to the panel's free-text message.
_PANEL_ERROR_CODE_MAP: dict[str, ErrorCode] = {
    # User / username
    "A014": E.USERNAME_ALREADY_EXISTS,            # create user — duplicate
    "A015": E.USERNAME_ALREADY_EXISTS,            # update user — duplicate
    "A019": E.PANEL_REJECTED_USERNAME,
    "A020": E.PANEL_REJECTED_USERNAME,
    # Status
    "A021": E.PANEL_REJECTED_STATUS,
    # Traffic strategy
    "A022": E.PANEL_REJECTED_TRAFFIC_STRATEGY,
    # Squad references
    "A023": E.PANEL_REJECTED_SQUAD,
    "A024": E.PANEL_REJECTED_SQUAD,
    # Tag
    "A025": E.PANEL_REJECTED_TAG,
}


def _classify_panel_error(exc: Exception) -> tuple[ErrorCode, str]:
    """Map a Panel API exception to (our error code, human message).

    Uses the Panel's `errorCode` field when present, falls back to message
    heuristics, and finally to PANEL_REJECTED_GENERIC.
    """
    msg = _extract_panel_error(exc) or "Panel rejected the request"
    try:
        import httpx
        import json as _json
        if isinstance(exc, httpx.HTTPStatusError):
            body = exc.response.text or ""
            try:
                parsed = _json.loads(body)
                if isinstance(parsed, dict):
                    code = parsed.get("errorCode")
                    if isinstance(code, str) and code in _PANEL_ERROR_CODE_MAP:
                        return _PANEL_ERROR_CODE_MAP[code], msg
                    # Heuristics on the free-text message
                    m = msg.lower()
                    if "username" in m and ("already" in m or "exists" in m or "duplicate" in m):
                        return E.PANEL_USER_ALREADY_EXISTS, msg
                    if "traffic limit strategy" in m or "trafficstrategy" in m:
                        return E.PANEL_REJECTED_TRAFFIC_STRATEGY, msg
                    if "status" in m and ("invalid" in m or "not allowed" in m):
                        return E.PANEL_REJECTED_STATUS, msg
                    if "squad" in m and ("not found" in m or "invalid" in m):
                        return E.PANEL_REJECTED_SQUAD, msg
                    if "tag" in m and ("too long" in m or "invalid" in m or "duplicate" in m):
                        return E.PANEL_REJECTED_TAG, msg
                    if "username" in m and ("invalid" in m or "format" in m):
                        return E.PANEL_REJECTED_USERNAME, msg
            except (ValueError, TypeError):
                pass
    except Exception:
        pass
    return E.PANEL_REJECTED_GENERIC, msg


# ── Input validation constants ────────────────────────────────────────
_USERNAME_RE = __import__("re").compile(r"^[A-Za-z0-9_.-]{1,100}$")
_EMAIL_RE = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_TRAFFIC_LIMIT_BYTES = 1024 * 1024  # 1 MB
_MAX_TAG_LEN = 32
_MAX_DESC_LEN = 256


def _validate_user_create_input(data) -> None:
    """Validate UserCreate fields and raise specific errors.

    Pydantic enforces type/length on declared fields, but cross-field
    validation (e.g. traffic limit, telegram id range) needs explicit checks.
    """
    if not data.username or not data.username.strip():
        raise api_error(400, E.USERNAME_REQUIRED)
    username = data.username.strip()
    if len(username) > 100:
        raise api_error(400, E.USERNAME_TOO_LONG)
    if not _USERNAME_RE.match(username):
        raise api_error(
            400, E.USERNAME_INVALID_FORMAT,
            f"Username '{username}' is invalid. Use 1-100 letters, digits, "
            f"underscores, hyphens, or dots.",
        )
    if data.traffic_limit_bytes is not None:
        if data.traffic_limit_bytes < 0:
            raise api_error(400, E.TRAFFIC_LIMIT_NEGATIVE)
        if 0 < data.traffic_limit_bytes < _MIN_TRAFFIC_LIMIT_BYTES:
            raise api_error(400, E.TRAFFIC_LIMIT_TOO_SMALL)
    if data.email is not None and data.email.strip():
        if not _EMAIL_RE.match(data.email.strip()):
            raise api_error(400, E.INVALID_EMAIL_FORMAT, f"Email '{data.email}' is not valid.")
    if data.telegram_id is not None and not (1 <= data.telegram_id <= 9_999_999_999):
        raise api_error(400, E.INVALID_TELEGRAM_ID)
    if data.hwid_device_limit is not None and data.hwid_device_limit < 0:
        raise api_error(400, E.INVALID_HWID_DEVICE_LIMIT)
    if data.expire_at is not None:
        # Naive datetimes are treated as UTC
        exp = data.expire_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc) - timedelta(minutes=1):
            raise api_error(400, E.INVALID_EXPIRE_DATE)
    if data.tag and len(data.tag) > _MAX_TAG_LEN:
        raise api_error(400, E.TAG_TOO_LONG, f"Tag is limited to {_MAX_TAG_LEN} characters.")
    if data.description and len(data.description) > _MAX_DESC_LEN:
        raise api_error(400, E.DESCRIPTION_TOO_LONG, f"Description is limited to {_MAX_DESC_LEN} characters.")


def _validate_user_update_input(data) -> None:
    """Validate UserUpdate fields. Mirrors create rules for shared fields."""
    if data.username is not None:
        if not data.username.strip():
            raise api_error(400, E.USERNAME_REQUIRED)
        username = data.username.strip()
        if len(username) > 100:
            raise api_error(400, E.USERNAME_TOO_LONG)
        if not _USERNAME_RE.match(username):
            raise api_error(400, E.USERNAME_INVALID_FORMAT)
    if data.traffic_limit_bytes is not None:
        if data.traffic_limit_bytes < 0:
            raise api_error(400, E.TRAFFIC_LIMIT_NEGATIVE)
        if 0 < data.traffic_limit_bytes < _MIN_TRAFFIC_LIMIT_BYTES:
            raise api_error(400, E.TRAFFIC_LIMIT_TOO_SMALL)
    if data.email is not None and data.email.strip():
        if not _EMAIL_RE.match(data.email.strip()):
            raise api_error(400, E.INVALID_EMAIL_FORMAT)
    if data.telegram_id is not None and not (1 <= data.telegram_id <= 9_999_999_999):
        raise api_error(400, E.INVALID_TELEGRAM_ID)
    if data.hwid_device_limit is not None and data.hwid_device_limit < 0:
        raise api_error(400, E.INVALID_HWID_DEVICE_LIMIT)
    if data.expire_at is not None:
        exp = data.expire_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc) - timedelta(minutes=1):
            raise api_error(400, E.INVALID_EXPIRE_DATE)
    if data.tag and len(data.tag) > _MAX_TAG_LEN:
        raise api_error(400, E.TAG_TOO_LONG)
    if data.description and len(data.description) > _MAX_DESC_LEN:
        raise api_error(400, E.DESCRIPTION_TOO_LONG)


def _ensure_snake_case(user: dict) -> dict:
    """Ensure user dict has snake_case keys for pydantic schemas."""
    result = dict(user)
    # Flatten nested userTraffic fields to root level
    # Remnawave API returns usedTrafficBytes, onlineAt etc. inside userTraffic object
    user_traffic = result.get('userTraffic')
    if isinstance(user_traffic, dict):
        for key in ('usedTrafficBytes', 'lifetimeUsedTrafficBytes', 'onlineAt',
                     'firstConnectedAt', 'lastConnectedNodeUuid'):
            if key in user_traffic and key not in result:
                result[key] = user_traffic[key]
    mappings = {
        'shortUuid': 'short_uuid',
        'subscriptionUuid': 'subscription_uuid',
        'subscriptionUrl': 'subscription_url',
        'telegramId': 'telegram_id',
        'expireAt': 'expire_at',
        'trafficLimitBytes': 'traffic_limit_bytes',
        'trafficLimitStrategy': 'traffic_limit_strategy',
        'usedTrafficBytes': 'used_traffic_bytes',
        'lifetimeUsedTrafficBytes': 'lifetime_used_traffic_bytes',
        'hwidDeviceLimit': 'hwid_device_limit',
        'hwidDeviceCount': 'hwid_device_count',
        'activeDeviceCount': 'active_device_count',
        'externalSquadUuid': 'external_squad_uuid',
        'activeInternalSquads': 'active_internal_squads',
        'createdAt': 'created_at',
        'updatedAt': 'updated_at',
        'onlineAt': 'online_at',
        'subRevokedAt': 'sub_revoked_at',
        'lastTrafficResetAt': 'last_traffic_reset_at',
        'trojanPassword': 'trojan_password',
        'vlessUuid': 'vless_uuid',
        'ssPassword': 'ss_password',
        'lastTriggeredThreshold': 'last_triggered_threshold',
        'firstConnectedAt': 'first_connected_at',
        'lastConnectedNodeUuid': 'last_connected_node_uuid',
        'createdByAdminId': 'created_by_admin_id',
    }
    for camel, snake in mappings.items():
        if camel in result and snake not in result:
            result[snake] = result[camel]
    # Normalize status to lowercase (Remnawave API returns ACTIVE, DISABLED, etc.)
    if isinstance(result.get('status'), str):
        result['status'] = result['status'].lower()
    return result


async def _get_users_list():
    """Get users from DB, fall back to API."""
    try:
        from shared.database import db_service
        if db_service.is_connected:
            users = await db_service.get_all_users(limit=50000)
            if users:
                logger.debug("Loaded %d users from database", len(users))
                return users
            else:
                logger.info("Database connected but no users found, trying API")
    except Exception as e:
        logger.warning("DB users fetch failed: %s", e)

    try:
        users = await fetch_users_from_api()
        logger.debug("Loaded %d users from API", len(users))
        return users
    except Exception as e:
        logger.warning("API users fetch failed: %s", e)
        return []


def _parse_dt(val) -> Optional[datetime]:
    """Parse a datetime value from various formats."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            # Try ISO format
            return datetime.fromisoformat(val.replace('Z', '+00:00'))
        except (ValueError, TypeError):
            return None
    return None


def _filter_users_in_memory(
    users: list, *, search=None, status=None, traffic_type=None,
    expire_filter=None, online_filter=None, traffic_usage=None,
    sort_by="created_at", sort_order="desc", page=1, per_page=20,
    visible_uuids: Optional[Set[str]] = None,
) -> tuple:
    """In-memory filtering/sorting/pagination fallback for API path."""
    now = datetime.now(timezone.utc)
    if visible_uuids is not None:
        users = [u for u in users if u.get("uuid") and u["uuid"].lower() in visible_uuids]

    def _get(u, *keys, default=''):
        for k in keys:
            v = u.get(k)
            if v is not None:
                return v
        return default

    if search:
        sl = search.lower()
        users = [
            u for u in users
            if sl in str(_get(u, 'username')).lower()
            or sl in str(_get(u, 'email')).lower()
            or sl in str(_get(u, 'uuid')).lower()
            or sl in str(_get(u, 'short_uuid')).lower()
            or sl in str(_get(u, 'telegram_id')).lower()
            or sl in str(_get(u, 'description')).lower()
        ]

    if status:
        status_lower = status.lower()
        users = [u for u in users if str(_get(u, 'status')).lower() == status_lower]

    if traffic_type == 'unlimited':
        users = [u for u in users if not u.get('traffic_limit_bytes')]
    elif traffic_type == 'limited':
        users = [u for u in users if u.get('traffic_limit_bytes') and u['traffic_limit_bytes'] > 0]

    if expire_filter:
        def _expire_match(u):
            expire = _parse_dt(u.get('expire_at'))
            if expire_filter == 'no_expiry':
                return expire is None
            if expire is None:
                return False
            if expire.tzinfo is None:
                expire = expire.replace(tzinfo=timezone.utc)
            if expire_filter == 'expired':
                return expire < now
            if expire_filter == 'expiring_7d':
                return now <= expire <= now + timedelta(days=7)
            if expire_filter == 'expiring_30d':
                return now <= expire <= now + timedelta(days=30)
            return True
        users = [u for u in users if _expire_match(u)]

    if online_filter:
        def _online_match(u):
            online = _parse_dt(u.get('online_at'))
            if online_filter == 'never':
                return online is None
            if online is None:
                return False
            if online.tzinfo is None:
                online = online.replace(tzinfo=timezone.utc)
            if online_filter == 'online_24h':
                return online >= now - timedelta(hours=24)
            if online_filter == 'online_7d':
                return online >= now - timedelta(days=7)
            if online_filter == 'online_30d':
                return online >= now - timedelta(days=30)
            return True
        users = [u for u in users if _online_match(u)]

    if traffic_usage:
        def _traffic_usage_match(u):
            used = u.get('used_traffic_bytes', 0) or 0
            limit_val = u.get('traffic_limit_bytes')
            if traffic_usage == 'zero':
                return used == 0
            if not limit_val or limit_val == 0:
                return False
            pct = (used / limit_val) * 100
            thresholds = {'above_90': 90, 'above_70': 70, 'above_50': 50}
            return pct >= thresholds.get(traffic_usage, 0)
        users = [u for u in users if _traffic_usage_match(u)]

    reverse = sort_order == "desc"
    if sort_by in ('used_traffic_bytes', 'raw_used_traffic_bytes', 'lifetime_used_traffic_bytes', 'hwid_device_limit'):
        users.sort(key=lambda x: x.get(sort_by, 0) or 0, reverse=reverse)
    elif sort_by == 'traffic_limit_bytes':
        def _tlk(u):
            val = u.get('traffic_limit_bytes')
            return val if val else float('inf')
        users.sort(key=_tlk, reverse=reverse)
    elif sort_by in ('online_at', 'expire_at'):
        def _dsk(u):
            val = _parse_dt(u.get(sort_by))
            return val.isoformat() if val else ('' if not reverse else 'zzzz')
        users.sort(key=_dsk, reverse=reverse)
    else:
        users.sort(key=lambda x: _get(x, sort_by) or '', reverse=reverse)

    total = len(users)
    start = (page - 1) * per_page
    return users[start:start + per_page], total


@router.get("", response_model=PaginatedResponse[UserListItem])
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, description="Search by username, email, or UUID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    traffic_type: Optional[str] = Query(None, description="Filter by traffic type: unlimited, limited"),
    expire_filter: Optional[str] = Query(None, description="Filter by expiration: expiring_7d, expiring_30d, expired, no_expiry"),
    online_filter: Optional[str] = Query(None, description="Filter by online status: online_24h, online_7d, online_30d, never"),
    traffic_usage: Optional[str] = Query(None, description="Filter by traffic usage: above_90, above_70, above_50, zero"),
    sort_by: str = Query("created_at", description="Sort field"),
    sort_order: str = Query("desc", regex="^(asc|desc)$"),
    admin_id: Optional[int] = Query(None, description="Filter by creator admin ID (superadmin only)"),
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """List users with pagination and filtering."""
    try:
        users = []
        total = 0
        db_available = False

        # Access-policy scope: only users tied to allowed nodes/squads
        visible_uuids = await get_visible_user_uuids(admin)
        uuid_whitelist = list(visible_uuids) if visible_uuids is not None else None

        # Restrict admin_id filter to superadmin and unrestricted admins
        resolved_admin_id = admin_id if (admin.role == "superadmin" or getattr(admin, "unrestricted_user_access", False)) else None

        # Primary path: SQL pagination in database
        try:
            from shared.database import db_service
            if db_service.is_connected:
                users, total = await db_service.get_users_paginated(
                    page=page, per_page=per_page,
                    search=search, status=status,
                    traffic_type=traffic_type,
                    expire_filter=expire_filter,
                    online_filter=online_filter,
                    traffic_usage=traffic_usage,
                    sort_by=sort_by, sort_order=sort_order,
                    uuid_whitelist=uuid_whitelist,
                    admin_id=resolved_admin_id,
                )
                db_available = True
        except Exception as e:
            logger.warning("DB paginated users failed, falling back to API: %s", e)

        if not db_available:
            # Fallback: API with in-memory filtering (old behavior)
            users = await _get_users_list()
            if uuid_whitelist is not None:
                wh = {u.lower() for u in uuid_whitelist}
                users = [u for u in users if u.get("uuid") and u["uuid"].lower() in wh]
            users, total = _filter_users_in_memory(
                users, search=search, status=status,
                traffic_type=traffic_type, expire_filter=expire_filter,
                online_filter=online_filter, traffic_usage=traffic_usage,
                sort_by=sort_by, sort_order=sort_order,
                page=page, per_page=per_page,
                visible_uuids=visible_uuids,
            )

        # Normalize to snake_case
        users = [_ensure_snake_case(u) for u in users]

        # Enrich ONLY current page with hwid_device_count and raw_traffic
        user_uuids = [u.get('uuid') for u in users if u.get('uuid')]
        if user_uuids:
            try:
                from shared.database import db_service
                if db_service.is_connected:
                    device_counts = await db_service.get_hwid_device_counts_for_uuids(user_uuids)
                    if device_counts:
                        for u in users:
                            uid = u.get('uuid')
                            if uid and uid in device_counts:
                                u['hwid_device_count'] = device_counts[uid]
                    raw_traffic = await db_service.get_raw_traffic_for_uuids(user_uuids)
                    if raw_traffic:
                        for u in users:
                            uid = u.get('uuid')
                            if uid and uid in raw_traffic:
                                u['raw_used_traffic_bytes'] = raw_traffic[uid]
            except Exception as e:
                logger.debug("Failed to enrich page data: %s", e)

        # Enrich with admin usernames for created_by_admin_id
        admin_ids = {u.get('created_by_admin_id') for u in users if u.get('created_by_admin_id')}
        if admin_ids:
            try:
                from web.backend.core.rbac import get_admin_usernames
                admin_names = await get_admin_usernames(list(admin_ids))
                if admin_names:
                    for u in users:
                        created_by = u.get('created_by_admin_id')
                        if created_by and created_by in admin_names:
                            u['created_by_admin_username'] = admin_names[created_by]
            except Exception as e:
                logger.debug("Failed to enrich admin usernames: %s", e)

        # Convert to schema
        user_items = []
        parse_errors = 0
        for u in users:
            try:
                user_items.append(UserListItem(**u))
            except Exception as e:
                parse_errors += 1
                if parse_errors <= 3:
                    logger.warning("Failed to parse user %s: %s (keys: %s)",
                                   u.get('uuid', '?'), e, list(u.keys())[:10])

        if parse_errors > 0:
            logger.warning("Failed to parse %d/%d users on page %d", parse_errors, len(users), page)

        return PaginatedResponse(
            items=user_items,
            total=total,
            page=page,
            per_page=per_page,
            pages=(total + per_page - 1) // per_page if total > 0 else 1,
        )

    except Exception as e:
        logger.error("Error listing users: %s", e, exc_info=True)
        return PaginatedResponse(
            items=[],
            total=0,
            page=page,
            per_page=per_page,
            pages=1,
        )


# ── Squad endpoints (must be before /{user_uuid} routes) ──────


def _normalize_squad(sq: dict) -> dict:
    """Ensure squad dict has squadTag/squadName fields for frontend compatibility.

    Remnawave API returns 'name' / 'tag', but frontend expects 'squadName' / 'squadTag'.
    """
    result = dict(sq)
    if "squadName" not in result:
        result["squadName"] = sq.get("name") or sq.get("tag") or sq.get("squadTag") or ""
    if "squadTag" not in result:
        result["squadTag"] = sq.get("tag") or sq.get("name") or sq.get("squadName") or ""
    return result


@router.get("/meta/internal-squads")
async def get_internal_squads(
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get available internal squads — reads from DB (synced), falls back to API."""
    squads = []
    try:
        from shared.data_access import get_all_internal_squads
        squads = await get_all_internal_squads()
    except ImportError:
        # Fallback: direct API call if data_access module is unavailable
        try:
            from shared.api_client import api_client
            result = await api_client.get_internal_squads()
            payload = result.get("response", result) if isinstance(result, dict) else result
            if isinstance(payload, dict):
                squads = payload.get("internalSquads", [])
            elif isinstance(payload, list):
                squads = payload
        except ImportError:
            raise api_error(503, E.API_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error("Error fetching internal squads: %s", e)
            return []

    scope = await get_scope(admin, "squad", "view")
    if scope is not None:
        squads = [sq for sq in squads if isinstance(sq, dict) and str(sq.get("uuid", "")).lower() in scope]

    return [_normalize_squad(sq) for sq in squads if isinstance(sq, dict)]


@router.get("/meta/external-squads")
async def get_external_squads(
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get available external squads — reads from DB (synced), falls back to API."""
    squads = []
    try:
        from shared.data_access import get_all_external_squads
        squads = await get_all_external_squads()
    except ImportError:
        # Fallback: direct API call if data_access module is unavailable
        try:
            from shared.api_client import api_client
            result = await api_client.get_external_squads()
            payload = result.get("response", result) if isinstance(result, dict) else result
            if isinstance(payload, dict):
                squads = payload.get("externalSquads", [])
            elif isinstance(payload, list):
                squads = payload
        except ImportError:
            raise api_error(503, E.API_SERVICE_UNAVAILABLE)
        except Exception as e:
            logger.error("Error fetching external squads: %s", e)
            return []

    return [_normalize_squad(sq) for sq in squads if isinstance(sq, dict)]


@router.post("/resolve")
@limiter.limit(RATE_BULK)
async def resolve_user(
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Универсальный поиск пользователя по uuid/id/shortUuid/username."""
    from shared.api_client import api_client

    body = await request.json()
    query = body.get("query", "").strip()

    # Also accept individual fields for backward compat
    if not query:
        query = body.get("uuid") or body.get("shortUuid") or body.get("username") or ""
        if body.get("id") is not None:
            query = str(body["id"])

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    import re

    # Build ordered list of lookup methods to try
    lookups = []
    if re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-', query, re.IGNORECASE):
        lookups.append(("uuid", lambda: api_client.get_user_by_uuid(query)))
    elif query.isdigit():
        lookups.append(("id", lambda: api_client.get_user_by_id(int(query))))
    else:
        # Could be username or short_uuid — try both
        lookups.append(("username", lambda: api_client.get_user_by_username(query)))
        lookups.append(("short_uuid", lambda: api_client.get_user_by_short_uuid(query)))
        if "@" in query:
            lookups.insert(0, ("email", lambda: api_client.get_users_by_email(query)))

    last_error = None
    for method_name, lookup_fn in lookups:
        try:
            result = await lookup_fn()
            payload = result.get("response", result) if isinstance(result, dict) else result
            if payload:
                resolved_uuid = payload.get("uuid") if isinstance(payload, dict) else None
                if resolved_uuid:
                    await _ensure_user_visible(admin, resolved_uuid)
                return _ensure_snake_case(payload) if isinstance(payload, dict) else payload
        except Exception as e:
            last_error = e
            logger.debug("Resolve by %s failed for '%s': %s", method_name, query, e)

    # Fallback: search local DB (description, notes, etc.)
    try:
        from shared.database import db_service
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT uuid, username FROM users
                    WHERE LOWER(raw_data->>'description') LIKE $1
                       OR LOWER(raw_data->>'note') LIKE $1
                    LIMIT 1
                    """,
                    f"%{query.lower()}%",
                )
                if row:
                    await _ensure_user_visible(admin, str(row["uuid"]))
                    # Found in local DB — fetch full data from Panel
                    try:
                        result = await api_client.get_user_by_uuid(str(row["uuid"]))
                        payload = result.get("response", result) if isinstance(result, dict) else result
                        if payload:
                            return payload
                    except Exception:
                        return {"uuid": str(row["uuid"]), "username": row["username"]}
    except Exception as e:
        logger.debug("Resolve local DB search failed for '%s': %s", query, e)

    raise api_error(404, E.USER_NOT_FOUND, "User not found")


@router.get("/{user_uuid}", response_model=UserDetail)
async def get_user(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get detailed user information with anti-abuse data from DB."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        # Try to get user from DB first, then API
        user_data = None
        try:
            from shared.database import db_service
            if db_service.is_connected:
                user_data = await db_service.get_user_by_uuid(user_uuid)
        except Exception:
            pass

        if not user_data:
            try:
                from shared.api_client import api_client
                resp = await api_client.get_user_by_uuid(user_uuid)
                user_data = resp.get('response', resp) if isinstance(resp, dict) else resp
            except ImportError:
                raise api_error(503, E.API_SERVICE_UNAVAILABLE)

        if not user_data:
            raise api_error(404, E.USER_NOT_FOUND)

        # Normalize to snake_case
        user_data = _ensure_snake_case(user_data)

        # Enrich with anti-abuse data from DB
        try:
            from shared.database import db_service
            if db_service.is_connected:
                # Violation count for last 30 days
                violations = await db_service.get_user_violations(
                    user_uuid=user_uuid, days=30, limit=1000
                )
                user_data['violation_count_30d'] = len(violations)

                # Active connections
                active_conns = await db_service.get_user_active_connections(user_uuid)
                user_data['active_connections'] = len(active_conns)

                # Unique IPs in last 24 hours
                unique_ips = await db_service.get_user_unique_ips_count(user_uuid, since_hours=24)
                user_data['unique_ips_24h'] = unique_ips

                # Trust score: 100 minus avg violation score (if any recent violations)
                if violations:
                    avg_score = sum(v.get('score', 0) for v in violations) / len(violations)
                    user_data['trust_score'] = max(0, int(100 - avg_score))
                else:
                    user_data['trust_score'] = 100
        except Exception as e:
            logger.debug("Failed to enrich user with anti-abuse data: %s", e)

        # Enrich with admin username
        try:
            from web.backend.core.rbac import get_admin_usernames
            created_by_id = user_data.get('created_by_admin_id')
            if created_by_id:
                admin_names = await get_admin_usernames([created_by_id])
                if admin_names and created_by_id in admin_names:
                    user_data['created_by_admin_username'] = admin_names[created_by_id]
        except Exception as e:
            logger.debug("Failed to enrich admin username: %s", e)

        return UserDetail(**user_data)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting user %s: %s", user_uuid, e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("", response_model=UserDetail)
async def create_user(
    request: Request,
    data: UserCreate,
    admin: AdminUser = Depends(require_permission("users", "create")),
    _quota: None = Depends(require_quota("users")),
):
    """Create a new user."""
    # Input validation (raises specific 400 errors via api_error)
    _validate_user_create_input(data)

    try:
        from shared.api_client import api_client

        # Compute expire_at ISO string
        if data.expire_at:
            expire_at_str = data.expire_at.isoformat()
        else:
            # Default: 30 days from now
            expire_at_str = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

        # Panel API хочет enum-поля в UPPERCASE (status, traffic_limit_strategy).
        status_upper = data.status.upper() if isinstance(data.status, str) else data.status
        strategy_upper = (
            data.traffic_limit_strategy.upper()
            if isinstance(data.traffic_limit_strategy, str)
            else data.traffic_limit_strategy
        )

        # `unlimited_traffic_policy` controls *enforcement* (hard quota cap)
        # but NOT *tracking*. The `traffic_used_bytes` counter must always be
        # updated when a user is created with a traffic limit, otherwise
        # subsequent edits and deletes subtract from a counter that was
        # never incremented — driving it negative. (regression test in
        # test_users_api.py::test_traffic_counter_never_goes_negative)
        if admin.role != "superadmin" and admin.account_id is not None:
            acct = await get_admin_account_by_id(admin.account_id)
            policy = acct.get("unlimited_traffic_policy", "allowed") if acct else "allowed"
            if policy == "disabled":
                if data.traffic_limit_bytes is None:
                    raise api_error(403, E.TRAFFIC_LIMIT_REQUIRED)
                max_traffic_gb = acct.get("max_traffic_gb")
                if max_traffic_gb is not None:
                    current_used = acct.get("traffic_used_bytes", 0)
                    max_allowed = max_traffic_gb * 1073741824
                    if current_used + data.traffic_limit_bytes > max_allowed:
                        remaining_gb = max(0, (max_allowed - current_used) // 1073741824)
                        raise api_error(
                            403, E.TRAFFIC_QUOTA_EXCEEDED,
                            f"Traffic limit exceeds your quota. Available: {remaining_gb} GB",
                        )
            if policy == "enforced":
                data.traffic_limit_bytes = None

        try:
            result = await api_client.create_user(
                username=data.username,
                expire_at=expire_at_str,
                traffic_limit_bytes=data.traffic_limit_bytes,
                hwid_device_limit=data.hwid_device_limit,
                telegram_id=data.telegram_id,
                description=data.description,
                traffic_limit_strategy=strategy_upper,
                external_squad_uuid=data.external_squad_uuid,
                active_internal_squads=data.active_internal_squads,
                status=status_upper,
                tag=data.tag,
                email=data.email,
                short_uuid=data.short_uuid,
                trojan_password=data.trojan_password,
                vless_uuid=data.vless_uuid,
                ss_password=data.ss_password,
                uuid=data.uuid,
                created_at=data.created_at.isoformat() if data.created_at else None,
                last_traffic_reset_at=data.last_traffic_reset_at.isoformat() if data.last_traffic_reset_at else None,
            )
        except Exception as panel_exc:
            # Map Panel API error to a specific code so the frontend can
            # show a localized, contextual message.
            code, msg = _classify_panel_error(panel_exc)
            logger.error("create_user(username=%s) panel error: %s [%s]", data.username, msg, code.value, exc_info=True)
            raise api_error(400, code, msg)

        user = result.get('response', result) if isinstance(result, dict) else result

        if admin.account_id is not None:
            from web.backend.core.rbac import increment_usage_counter
            if not await increment_usage_counter(admin.account_id, "users_created"):
                # Roll back the user we just created to keep counters honest
                try:
                    await api_client.delete_user(user.get("uuid", ""))
                except Exception:
                    pass
                raise api_error(409, E.USERS_QUOTA_EXCEEDED,
                                "User quota exceeded. Please delete some users or contact your administrator.")
            # Always track traffic counter when the user has a limit. The
            # enforcement policy was already applied above; the counter
            # is purely informational and must stay consistent with the
            # user's actual allocation so edits and deletes don't drive
            # it negative. If the increment fails (race condition, DB
            # issue, etc.) we roll back the user we just created.
            if data.traffic_limit_bytes is not None and data.traffic_limit_bytes > 0:
                if not await increment_usage_counter(
                    admin.account_id, "traffic_used_bytes", data.traffic_limit_bytes
                ):
                    try:
                        await api_client.delete_user(user.get("uuid", ""))
                    except Exception:
                        pass
                    raise api_error(
                        409, E.TRAFFIC_QUOTA_EXCEEDED,
                        "Traffic limit exceeds your quota. Please delete some users or contact your administrator."
                    )

        # Persist full user data from Panel API response to local DB
        user_uuid = user.get('uuid', '') if isinstance(user, dict) else ''
        if user_uuid:
            try:
                from shared.database import db_service
                if db_service.is_connected:
                    await db_service.upsert_user(user)
                    if admin.account_id is not None:
                        async with db_service.acquire() as conn:
                            await conn.execute(
                                "UPDATE users SET created_by_admin_id = $1 WHERE uuid = $2",
                                admin.account_id, user_uuid,
                            )
            except Exception as e:
                logger.debug("Failed to persist user data: %s", e)

        # Audit
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="user.create",
            resource="users",
            resource_id=str(user_uuid),
            details=json.dumps({"username": data.username}),
            ip_address=get_client_ip(request),
        )

        fire_event("user.created", {
            "uuid": str(user_uuid),
            "username": data.username,
            "email": data.email,
            "telegram_id": data.telegram_id,
            "expire_at": expire_at_str,
            "created_by": admin.username,
        })

        return UserDetail(**_ensure_snake_case(user))

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("create_user(username=%s) failed: %s", data.username, e, exc_info=True)
        raise api_error(500, E.INTERNAL_ERROR)


@router.patch("/{user_uuid}", response_model=UserDetail)
async def update_user(
    user_uuid: str,
    request: Request,
    data: UserUpdate,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Update user fields."""
    await _ensure_user_visible(admin, user_uuid)

    update_data = data.model_dump(exclude_unset=True, mode='json')
    if not update_data:
        raise api_error(400, E.NO_FIELDS_TO_UPDATE)

    # Input validation (raises specific 400 errors via api_error)
    _validate_user_update_input(data)

    try:
        from shared.api_client import api_client

        # Panel API ждёт enum status в UPPERCASE (ACTIVE/LIMITED/DISABLED/EXPIRED).
        # Фронт хранит их в lowercase для удобства, апаем тут.
        if isinstance(update_data.get('status'), str):
            update_data['status'] = update_data['status'].upper()
        # traffic_limit_strategy — тоже enum, тоже UPPERCASE (NO_RESET / DAY / WEEK / MONTH)
        if isinstance(update_data.get('traffic_limit_strategy'), str):
            update_data['traffic_limit_strategy'] = update_data['traffic_limit_strategy'].upper()
        # Convert snake_case keys to camelCase for Remnawave API
        snake_to_camel = {
            'traffic_limit_bytes': 'trafficLimitBytes',
            'traffic_limit_strategy': 'trafficLimitStrategy',
            'expire_at': 'expireAt',
            'hwid_device_limit': 'hwidDeviceLimit',
            'telegram_id': 'telegramId',
            'active_internal_squads': 'activeInternalSquads',
            'external_squad_uuid': 'externalSquadUuid',
        }

        # The traffic counter tracks the user's currently-allocated quota and
        # must be updated whenever the limit changes, regardless of the
        # admin's enforcement policy. Otherwise a user created under
        # `policy="allowed"` (counter not incremented) and then later
        # edited/deleted under `policy="disabled"` would subtract from a
        # counter that was never credited — driving it negative.
        _traffic_delta = 0
        _traffic_tracked = False
        creator_admin_id = None

        # Fetch the owner (creator) of this user. The counter change will be
        # attributed to the OWNER, not the acting admin. This is important when
        # a higher-access admin (e.g. superadmin) edits a user that was created
        # by a less-privileged admin.
        from shared.database import db_service
        if db_service.is_connected:
            try:
                existing = await db_service.get_user_by_uuid(user_uuid)
                if existing:
                    creator_admin_id = existing.get("createdByAdminId")
            except Exception:
                logger.debug("Failed to fetch user for owner lookup user_uuid=%s", user_uuid)

        # Enforce per-admin unlimited_traffic_policy for non-superadmin
        if admin.role != "superadmin" and admin.account_id is not None and 'traffic_limit_bytes' in update_data:
            acct = await get_admin_account_by_id(admin.account_id)
            policy = acct.get("unlimited_traffic_policy", "allowed") if acct else "allowed"
            if policy == "disabled":
                if update_data['traffic_limit_bytes'] is None:
                    raise api_error(403, E.TRAFFIC_LIMIT_REQUIRED)
                old_limit = None
                user_used = 0
                try:
                    if db_service.is_connected:
                        existing = await db_service.get_user_by_uuid(user_uuid)
                        if existing:
                            old_limit = existing.get('trafficLimitBytes')
                            user_used = existing.get('usedTrafficBytes') or 0
                except Exception:
                    pass
                if old_limit is None:
                    try:
                        resp = await api_client.get_user_by_uuid(user_uuid)
                        user_data = resp.get('response', resp) if isinstance(resp, dict) else resp
                        old_limit = user_data.get('traffic_limit_bytes')
                        if old_limit is None:
                            raise ValueError("no limit in API response")
                        if not user_used:
                            user_used = user_data.get('used_traffic_bytes') or 0
                    except Exception:
                        pass
                if old_limit is None:
                    old_limit = 0
                new_limit = update_data['traffic_limit_bytes']
                if new_limit is not None and user_used > 0 and new_limit < user_used:
                    used_gb = (user_used + 1073741823) // 1073741824
                    raise api_error(
                        403, E.TRAFFIC_LIMIT_BELOW_USAGE,
                        f"Cannot set traffic limit below current usage ({used_gb} GB used).",
                    )
                _traffic_delta = (new_limit or 0) - old_limit
                if _traffic_delta > 0:
                    max_traffic_gb = acct.get("max_traffic_gb")
                    if max_traffic_gb is not None:
                        current_used = acct.get("traffic_used_bytes", 0)
                        max_allowed = max_traffic_gb * 1073741824
                        if current_used + _traffic_delta > max_allowed:
                            remaining_gb = max(0, (max_allowed - current_used) // 1073741824)
                            raise api_error(
                                403, E.TRAFFIC_QUOTA_EXCEEDED,
                                f"Traffic limit exceeds your quota. Available: {remaining_gb} GB",
                            )
                    _traffic_tracked = True
                elif _traffic_delta < 0:
                    _traffic_tracked = True
            if policy == "enforced":
                update_data['traffic_limit_bytes'] = 0

        # For non-disabled policies, the counter still needs to be updated so
        # future edits/deletes stay consistent. The delta is computed from
        # the local DB; if it's missing, fall back to 0 (no counter change).
        if (
            not _traffic_tracked
            and admin.role != "superadmin"
            and admin.account_id is not None
            and 'traffic_limit_bytes' in update_data
        ):
            acct = await get_admin_account_by_id(admin.account_id)
            policy = acct.get("unlimited_traffic_policy", "allowed") if acct else "allowed"
            if policy != "disabled":
                # Same delta calculation as above but without the enforcement
                # gate. We need this to keep the counter consistent even
                # when the admin's policy doesn't enforce a hard cap.
                try:
                    if db_service.is_connected:
                        existing_for_delta = await db_service.get_user_by_uuid(user_uuid)
                    else:
                        existing_for_delta = None
                except Exception:
                    existing_for_delta = None
                old_limit = (existing_for_delta or {}).get('trafficLimitBytes') or 0
                new_limit = update_data['traffic_limit_bytes'] or 0
                _traffic_delta = new_limit - old_limit
                if _traffic_delta != 0:
                    _traffic_tracked = True

        camel_data = {}
        for k, v in update_data.items():
            camel_data[snake_to_camel.get(k, k)] = v
        try:
            resp = await api_client.update_user(user_uuid, **camel_data)
        except Exception as panel_exc:
            code, msg = _classify_panel_error(panel_exc)
            logger.error("update_user(%s) panel error: %s [%s]", user_uuid, msg, code.value, exc_info=True)
            raise api_error(400, code, msg)
        user = resp.get('response', resp) if isinstance(resp, dict) else resp

        # Apply quota counter changes to the OWNER (creator), not the acting admin.
        if _traffic_tracked and creator_admin_id is not None and _traffic_delta != 0:
            from web.backend.core.rbac import increment_usage_counter
            await increment_usage_counter(creator_admin_id, "traffic_used_bytes", _traffic_delta)

        # Audit
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="user.update",
            resource="users",
            resource_id=str(user_uuid),
            details=json.dumps({k: str(v) for k, v in update_data.items()}),
            ip_address=get_client_ip(request),
        )

        fire_event("user.updated", {
            "uuid": user_uuid,
            "username": user.get("username") if isinstance(user, dict) else None,
            "changed_fields": sorted(update_data.keys()),
            "updated_by": admin.username,
        })

        return UserDetail(**_ensure_snake_case(user))

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_user(%s) failed: %s", user_uuid, e, exc_info=True)
        raise api_error(500, E.INTERNAL_ERROR)


@router.delete("/{user_uuid}", response_model=SuccessResponse)
async def delete_user(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "delete")),
):
    """Delete a user."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.api_client import api_client
        from shared.database import db_service

        # Fetch user before deleting to get ownership and usage for quota decrement
        creator_admin_id = None
        used_bytes = 0
        traffic_limit = 0
        if db_service.is_connected:
            existing = await db_service.get_user_by_uuid(user_uuid)
            if existing:
                creator_admin_id = existing.get("createdByAdminId")
                used_bytes = existing.get("usedTrafficBytes") or 0
                traffic_limit = existing.get("trafficLimitBytes") or 0

        try:
            await api_client.delete_user(user_uuid)
        except Exception as panel_exc:
            code, msg = _classify_panel_error(panel_exc)
            logger.error("delete_user(%s) panel error: %s [%s]", user_uuid, msg, code.value, exc_info=True)
            raise api_error(400, code, msg)

        # Also remove from local DB so UI updates immediately
        try:
            if db_service.is_connected:
                await db_service.delete_user(user_uuid)
        except Exception as e:
            logger.debug("Non-critical: failed to delete user from local DB: %s", e)

        # Apply quota counter changes via shared helper
        if creator_admin_id is not None:
            await apply_user_delete_quotas(creator_admin_id, traffic_limit or 0, used_bytes)

        # Audit
        await write_audit_log(
            admin_id=admin.account_id,
            admin_username=admin.username,
            action="user.delete",
            resource="users",
            resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )

        fire_event("user.deleted", {
            "uuid": user_uuid,
            "deleted_by": admin.username,
        })

        return SuccessResponse(message="User deleted")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("delete_user(%s) failed: %s", user_uuid, e, exc_info=True)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/{user_uuid}/enable", response_model=SuccessResponse)
async def enable_user(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Enable a disabled user."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.api_client import api_client

        await api_client.enable_user(user_uuid)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.enable", resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )
        fire_event("user.updated", {
            "uuid": user_uuid,
            "changed_fields": ["status"],
            "status": "active",
            "updated_by": admin.username,
        })
        return SuccessResponse(message="User enabled")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Internal server error")


@router.post("/{user_uuid}/disable", response_model=SuccessResponse)
async def disable_user(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Disable a user."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.api_client import api_client

        await api_client.disable_user(user_uuid)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.disable", resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid}),
            ip_address=get_client_ip(request),
        )
        fire_event("user.updated", {
            "uuid": user_uuid,
            "changed_fields": ["status"],
            "status": "disabled",
            "updated_by": admin.username,
        })
        return SuccessResponse(message="User disabled")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Internal server error")


@router.post("/{user_uuid}/reset-traffic", response_model=SuccessResponse)
async def reset_user_traffic(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Reset user's traffic usage."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.api_client import api_client

        # Fetch used_traffic_bytes BEFORE the reset
        creator_admin_id, _limit, used_bytes = await fetch_user_quota_data(user_uuid)

        await api_client.reset_user_traffic(user_uuid)

        # Apply quota counter changes via shared helper
        await apply_user_reset_traffic_quotas(creator_admin_id, used_bytes)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.reset_traffic", resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid, "used_bytes": used_bytes}),
            ip_address=get_client_ip(request),
        )
        return SuccessResponse(message="Traffic reset")

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Internal server error")


@router.post("/{user_uuid}/revoke", response_model=SuccessResponse)
async def revoke_user_subscription(
    user_uuid: str,
    request: Request,
    passwords_only: bool = Query(False, description="If true, only regenerate passwords, keep subscription URL"),
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Revoke user's subscription. passwords_only=true regenerates only connection passwords."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.api_client import api_client

        await api_client.revoke_user_subscription(user_uuid, revoke_only_passwords=passwords_only)

        action = "user.revoke_passwords" if passwords_only else "user.revoke"
        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action=action, resource="users", resource_id=user_uuid,
            details=json.dumps({"user_uuid": user_uuid, "passwords_only": passwords_only}),
            ip_address=get_client_ip(request),
        )
        msg = "Passwords regenerated" if passwords_only else "Subscription revoked"
        return SuccessResponse(message=msg)

    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Internal server error")


@router.post("/hwid-device-counts")
async def get_hwid_device_counts(
    user_uuids: List[str],
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get HWID device counts for multiple users in one call."""
    visible = await get_visible_user_uuids(admin)
    if visible is not None:
        user_uuids = [u for u in user_uuids if u.lower() in visible]
    import asyncio

    async def _get_count(uuid: str) -> tuple:
        try:
            from shared.api_client import api_client
            result = await api_client.get_user_hwid_devices(uuid)
            response = result.get("response", result) if isinstance(result, dict) else result
            devices = response if isinstance(response, list) else response.get("devices", []) if isinstance(response, dict) else []
            return (uuid, len(devices))
        except Exception:
            return (uuid, 0)

    # Limit concurrent requests
    semaphore = asyncio.Semaphore(10)

    async def _limited_get_count(uuid: str) -> tuple:
        async with semaphore:
            return await _get_count(uuid)

    results = await asyncio.gather(*[_limited_get_count(uid) for uid in user_uuids[:100]])
    return {uuid: count for uuid, count in results}


@router.get("/{user_uuid}/traffic-stats")
async def get_user_traffic_stats(
    user_uuid: str,
    period: str = Query("today", description="Period: today, week, month, 3month, 6month, year"),
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get per-user traffic statistics with per-node breakdown from Remnawave API.

    Uses /api/bandwidth-stats/users/{uuid} which returns actual per-user
    traffic data broken down by node for any date range.
    """
    await _ensure_user_visible(admin, user_uuid)
    from datetime import datetime, timedelta, timezone

    try:
        # Get user data for current/lifetime traffic
        user_data = None
        try:
            from shared.database import db_service
            if db_service.is_connected:
                user_data = await db_service.get_user_by_uuid(user_uuid)
        except Exception:
            pass

        if not user_data:
            try:
                from shared.api_client import api_client as _api
                resp = await _api.get_user_by_uuid(user_uuid)
                user_data = resp.get('response', resp) if isinstance(resp, dict) else resp
            except ImportError:
                raise api_error(503, E.API_SERVICE_UNAVAILABLE)

        if not user_data:
            raise api_error(404, E.USER_NOT_FOUND)

        user_data = _ensure_snake_case(user_data)

        used_bytes = user_data.get('used_traffic_bytes', 0) or 0
        lifetime_bytes = user_data.get('lifetime_used_traffic_bytes', 0) or 0
        traffic_limit = user_data.get('traffic_limit_bytes')

        # Calculate date range for the requested period
        # API expects YYYY-MM-DD format; end = tomorrow to include full current day
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        period_map = {
            'today': timedelta(days=1),
            'week': timedelta(days=7),
            'month': timedelta(days=30),
            '3month': timedelta(days=90),
            '6month': timedelta(days=180),
            'year': timedelta(days=365),
        }
        delta = period_map.get(period, timedelta(days=1))
        start_dt = today_start - delta if period != 'today' else today_start
        end_dt = today_start + timedelta(days=1)
        start_str = start_dt.strftime('%Y-%m-%d')
        end_str = end_dt.strftime('%Y-%m-%d')

        # Fetch per-user traffic from Remnawave bandwidth-stats API
        period_bytes = 0
        nodes_traffic = []
        try:
            from shared.api_client import api_client
            result = await api_client.get_user_traffic_stats(
                user_uuid, start=start_str, end=end_str, top_nodes_limit=50
            )
            # Parse response - API returns { response: { topNodes: [...], series: [...], ... } }
            response = result.get('response', result) if isinstance(result, dict) else result

            if isinstance(response, dict):
                # Per-node breakdown from topNodes array
                # Fields: uuid, name, countryCode, color, total (bytes as number)
                top_nodes = response.get('topNodes', [])
                if isinstance(top_nodes, list):
                    for node in top_nodes:
                        total = int(node.get('total', 0) or 0)
                        period_bytes += total
                        nodes_traffic.append({
                            'node_name': node.get('name', 'Unknown'),
                            'node_uuid': node.get('uuid', ''),
                            'total_bytes': total,
                        })
        except Exception as e:
            logger.warning("Failed to fetch per-user bandwidth stats for %s: %s", user_uuid, e)

        return {
            'used_bytes': used_bytes,
            'lifetime_bytes': lifetime_bytes,
            'traffic_limit_bytes': traffic_limit,
            'period': period,
            'period_bytes': period_bytes,
            'nodes_traffic': nodes_traffic,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error getting traffic stats for %s: %s", user_uuid, e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.get("/{user_uuid}/ip-history")
async def get_user_ip_history(
    user_uuid: str,
    period: str = Query("24h", description="Period: 24h, 7d, 30d"),
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get unique IP addresses for a user with geo enrichment."""
    await _ensure_user_visible(admin, user_uuid)
    period_days = {"24h": 1, "7d": 7, "30d": 30}.get(period, 1)
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            return {"items": [], "total": 0}

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    SPLIT_PART(uc.ip_address::text, '/', 1) as ip,
                    im.country_name as country,
                    im.city,
                    im.asn_org,
                    COUNT(uc.id) as connections,
                    MAX(uc.connected_at) as last_seen
                FROM user_connections uc
                LEFT JOIN ip_metadata im
                    ON SPLIT_PART(uc.ip_address::text, '/', 1) = TRIM(im.ip_address)
                WHERE uc.user_uuid = $1
                  AND uc.connected_at > NOW() - make_interval(days => $2)
                GROUP BY SPLIT_PART(uc.ip_address::text, '/', 1),
                         im.country_name, im.city, im.asn_org
                ORDER BY last_seen DESC
                """,
                user_uuid,
                period_days,
            )
            items = [
                {
                    "ip": r["ip"],
                    "country": r["country"] or "",
                    "city": r["city"] or "",
                    "asn_org": r["asn_org"] or "",
                    "connections": r["connections"],
                    "last_seen": r["last_seen"].isoformat() if r["last_seen"] else None,
                }
                for r in rows
            ]
            return {"items": items, "total": len(items)}
    except Exception as e:
        logger.error("Error getting IP history for %s: %s", user_uuid, e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/{user_uuid}/sync-hwid-devices")
async def sync_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Force re-sync HWID devices for a user from Remnawave API to local DB."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.sync import sync_service
        synced = await sync_service.sync_user_hwid_devices(user_uuid)
        return {"success": True, "synced": synced}
    except Exception as e:
        logger.error("Error syncing HWID devices for %s: %s", user_uuid, e)
        raise api_error(500, E.SYNC_FAILED)


@router.get("/{user_uuid}/hwid-devices", response_model=List[HwidDevice])
async def get_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get HWID devices for a user. Reads from local DB (synced via webhooks), API as fallback."""
    await _ensure_user_visible(admin, user_uuid)
    def _parse_devices(devices: list) -> List[HwidDevice]:
        items = []
        for d in devices:
            items.append(HwidDevice(
                hwid=d.get("hwid", ""),
                platform=d.get("platform"),
                os_version=d.get("osVersion") or d.get("os_version"),
                device_model=d.get("deviceModel") or d.get("device_model"),
                app_version=d.get("appVersion") or d.get("app_version"),
                user_agent=d.get("userAgent") or d.get("user_agent"),
                created_at=d.get("createdAt") or d.get("created_at"),
                updated_at=d.get("updatedAt") or d.get("updated_at"),
            ))
        return items

    # Read from local DB first (kept up-to-date via sync + webhooks)
    try:
        from shared.database import db_service
        if db_service.is_connected:
            db_devices = await db_service.get_user_hwid_devices(user_uuid)
            if db_devices:
                return _parse_devices(db_devices)
    except Exception as e:
        logger.debug("DB HWID fetch failed for %s, trying API: %s", user_uuid, e)

    # DB empty — trigger sync from Panel API (uses same logic as manual sync button)
    try:
        from shared.sync import sync_service
        synced = await sync_service.sync_user_hwid_devices(user_uuid)
        if synced:
            from shared.database import db_service
            if db_service.is_connected:
                db_devices = await db_service.get_user_hwid_devices(user_uuid)
                if db_devices:
                    return _parse_devices(db_devices)
    except Exception as e:
        logger.debug("Sync HWID failed for %s: %s", user_uuid, e)

    return []


@router.delete("/{user_uuid}/hwid-devices/{device_id}")
async def delete_user_hwid_device(
    user_uuid: str,
    device_id: str,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Delete a specific HWID device for a user."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.database import db_service
        from shared.api_client import api_client

        # Delete from local DB (parameter is hwid, not device_id)
        if db_service.is_connected:
            await db_service.delete_hwid_device(user_uuid=user_uuid, hwid=device_id)

        # Also delete from main API
        try:
            await api_client.delete_user_hwid_device(user_uuid, device_id)
        except Exception as e:
            logger.warning("Failed to delete HWID device %s from API for %s: %s", device_id, user_uuid, e)

        return {"success": True, "message": "Device deleted"}
    except Exception as e:
        logger.error("Error deleting HWID device %s for %s: %s", device_id, user_uuid, e)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{user_uuid}/hwid-devices")
async def delete_all_user_hwid_devices(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Delete all HWID devices for a user."""
    await _ensure_user_visible(admin, user_uuid)
    try:
        from shared.database import db_service
        from shared.api_client import api_client

        # Delete from local DB
        if db_service.is_connected:
            await db_service.delete_all_user_hwid_devices(user_uuid=user_uuid)

        # Also delete from main API
        try:
            await api_client.delete_all_user_hwid_devices(user_uuid)
        except Exception as e:
            logger.warning("Failed to delete all HWID devices from API for %s: %s", user_uuid, e)

        return {"success": True, "message": "All devices deleted"}
    except Exception as e:
        logger.error("Error deleting all HWID devices for %s: %s", user_uuid, e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Bulk operations ──────────────────────────────────────────────


@router.post("/bulk/enable", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_enable_users(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Enable multiple users at once (max 100)."""
    visible = await get_visible_user_uuids(admin)
    if visible is not None:
        body.uuids = [u for u in body.uuids if u.lower() in visible]

    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api_client.enable_user(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_enable", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


@router.post("/bulk/disable", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_disable_users(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Disable multiple users at once (max 100)."""
    visible = await get_visible_user_uuids(admin)
    if visible is not None:
        body.uuids = [u for u in body.uuids if u.lower() in visible]

    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api_client.disable_user(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_disable", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


@router.post("/bulk/delete", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_delete_users(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Delete multiple users at once (max 100)."""
    visible = await get_visible_user_uuids(admin)
    if visible is not None:
        body.uuids = [u for u in body.uuids if u.lower() in visible]

    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            from shared.database import db_service
            creator_admin_id = None
            used_bytes = 0
            traffic_limit = 0
            if db_service.is_connected:
                existing = await db_service.get_user_by_uuid(uuid)
                if existing:
                    creator_admin_id = existing.get("createdByAdminId")
                    used_bytes = existing.get("usedTrafficBytes") or 0
                    traffic_limit = existing.get("trafficLimitBytes") or 0

            await api_client.delete_user(uuid)
            if db_service.is_connected:
                try:
                    await db_service.delete_user(uuid)
                except Exception as e:
                    logger.debug("Non-critical: failed to delete user from local DB: %s", e)

            if creator_admin_id is not None:
                await apply_user_delete_quotas(creator_admin_id, traffic_limit or 0, used_bytes)

            success += 1
            fire_event("user.deleted", {
                "uuid": uuid,
                "deleted_by": admin.username,
                "bulk": True,
            })
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_delete", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


@router.post("/bulk/reset-traffic", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_reset_traffic(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Reset traffic for multiple users at once (max 100)."""
    visible = await get_visible_user_uuids(admin)
    if visible is not None:
        body.uuids = [u for u in body.uuids if u.lower() in visible]

    try:
        from shared.api_client import api_client
    except ImportError:
        raise api_error(503, E.API_SERVICE_UNAVAILABLE)

    # Fetch used_traffic_bytes BEFORE the reset
    users_data = await fetch_users_quota_data_batch(body.uuids)

    success, failed, errors = 0, 0, []
    for uuid in body.uuids:
        try:
            await api_client.reset_user_traffic(uuid)
            success += 1
        except Exception as e:
            failed += 1
            errors.append(BulkOperationError(uuid=uuid, error=str(e)))

    # Apply quota counter changes via shared helper
    await apply_users_reset_traffic_quotas_batch(users_data)

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_reset_traffic", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


@router.post("/bulk/reassign", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_reassign_users(
    request: Request,
    body: BulkReassignRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Reassign multiple users to another admin (superadmin only)."""
    if admin.role != "superadmin":
        raise api_error(403, E.FORBIDDEN)
    target = await get_admin_account_by_id(body.new_admin_id)
    if not target:
        raise api_error(404, E.ADMIN_NOT_FOUND)

    from shared.database import db_service

    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    # Fetch existing ownership and traffic data before updating
    rows = []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            select_sql(USERS_TABLE, "created_by_admin_id, used_traffic_bytes, traffic_limit_bytes", "WHERE uuid = ANY($1::uuid[])"),
            body.uuids,
        )

    success = len(body.uuids)
    errors = []
    async with db_service.acquire() as conn:
        try:
            result = await conn.execute(
                update_sql(USERS_TABLE, "created_by_admin_id = $1", "uuid = ANY($2::uuid[])"),
                body.new_admin_id, body.uuids,
            )
            if "UPDATE " in result:
                parts = result.split()
                if len(parts) >= 2:
                    try:
                        success = int(parts[1])
                    except (ValueError, IndexError):
                        pass
        except Exception as e:
            success = 0
            errors = [BulkOperationError(uuid=u, error=str(e)) for u in body.uuids]

    failed = len(body.uuids) - success

    # Apply quota counter changes via shared helper using per-user data
    per_user_data: list = []
    for r in rows:
        prev_id = r.get("created_by_admin_id")
        if prev_id == body.new_admin_id:
            continue
        per_user_data.append((
            prev_id,
            r.get("traffic_limit_bytes") or 0,
            r.get("used_traffic_bytes") or 0,
        ))
    await apply_users_reassign_quotas_batch(per_user_data, body.new_admin_id)

    await write_audit_log(
        admin_id=admin.account_id, admin_username=admin.username,
        action="user.bulk_reassign", resource="users", resource_id="bulk",
        details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed, "new_admin_id": body.new_admin_id}),
        ip_address=get_client_ip(request),
    )
    return BulkOperationResult(success=success, failed=failed, errors=errors)


# ── Subscription Info ────────────────────────────────────────────

@router.get("/{user_uuid}/subscription-info")
async def get_subscription_info(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Get detailed subscription info for a user via Panel API."""
    await _ensure_user_visible(admin, user_uuid)
    from shared.api_client import api_client
    from shared.database import db_service

    # Get user's short_uuid from DB
    if not db_service.is_connected:
        raise api_error(503, E.DB_UNAVAILABLE)

    user = await db_service.get_user_by_uuid(user_uuid)
    if not user:
        raise api_error(404, E.USER_NOT_FOUND)

    short_uuid = user.get("shortUuid") or user.get("short_uuid")
    if not short_uuid:
        raise api_error(404, E.USER_NOT_FOUND)

    try:
        result = await api_client.get_subscription_info(short_uuid)
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to get subscription info for %s: %s", user_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


# ── IP Control ────────────────────────────────────────────────────

@router.post("/{user_uuid}/fetch-ips")
async def fetch_user_ips(
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Запускает сбор IP-адресов пользователя через Panel API."""
    await _ensure_user_visible(admin, user_uuid)
    from shared.api_client import api_client

    try:
        result = await api_client.fetch_user_ips(user_uuid)
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to fetch IPs for %s: %s", user_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


# ── Reassign user to another admin ──────────────────────────────

class ReassignRequest(BaseModel):
    new_admin_id: int = Field(..., description="ID of the admin to assign the user to")


@router.post("/{user_uuid}/reassign", response_model=SuccessResponse)
async def reassign_user(
    user_uuid: str,
    request: Request,
    body: ReassignRequest,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Reassign a user to another admin (superadmin only)."""
    if admin.role != "superadmin":
        raise api_error(403, E.FORBIDDEN)
    target = await get_admin_account_by_id(body.new_admin_id)
    if not target:
        raise api_error(404, E.ADMIN_NOT_FOUND)
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            raise api_error(503, E.DB_UNAVAILABLE)
        previous_admin_id = None
        used_bytes = 0
        traffic_limit = 0
        async with db_service.acquire() as conn:
            existing = await conn.fetchrow(
                select_sql(USERS_TABLE, "created_by_admin_id, used_traffic_bytes, traffic_limit_bytes", "WHERE uuid = $1"),
                user_uuid,
            )
            if not existing:
                raise api_error(404, E.USER_NOT_FOUND)
            previous_admin_id = existing.get("created_by_admin_id")
            used_bytes = existing.get("used_traffic_bytes") or 0
            traffic_limit = existing.get("traffic_limit_bytes") or 0
            result = await conn.execute(
                update_sql(USERS_TABLE, "created_by_admin_id = $1", "uuid = $2"),
                body.new_admin_id, user_uuid,
            )
            if "UPDATE 0" in result:
                raise api_error(404, E.USER_NOT_FOUND)

        # Apply quota counter changes via shared helper
        await apply_user_reassign_quotas(
            previous_admin_id,
            body.new_admin_id,
            traffic_limit or 0,
            used_bytes,
        )

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.reassign", resource="users", resource_id=user_uuid,
            details=json.dumps({
                "new_admin_id": body.new_admin_id,
                "new_username": target["username"],
                "previous_admin_id": previous_admin_id,
            }),
            ip_address=get_client_ip(request),
        )
        return SuccessResponse(message="User reassigned")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("reassign_user failed: %s", e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/bulk/unassign-admin", response_model=BulkOperationResult)
@limiter.limit(RATE_BULK)
async def bulk_unassign_admin(
    request: Request,
    body: BulkUserRequest,
    admin: AdminUser = Depends(require_permission("users", "bulk_operations")),
):
    """Clear created_by_admin_id for multiple users at once (superadmin only, max 100)."""
    if admin.role != "superadmin":
        raise api_error(403, E.FORBIDDEN)
    visible = await get_visible_user_uuids(admin)
    if visible is not None:
        body.uuids = [u for u in body.uuids if u.lower() in visible]

    try:
        from shared.database import db_service
        if not db_service.is_connected:
            raise api_error(503, E.DB_UNAVAILABLE)

        # Fetch previous ownership before update so we can transfer counters
        rows = []
        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                select_sql(
                    USERS_TABLE,
                    "uuid::text, created_by_admin_id, traffic_limit_bytes, used_traffic_bytes",
                    "WHERE uuid = ANY($1::uuid[]) AND created_by_admin_id IS NOT NULL",
                ),
                body.uuids,
            )

        success, failed, errors = 0, 0, []
        async with db_service.acquire() as conn:
            try:
                result = await conn.execute(
                    update_sql(
                        USERS_TABLE,
                        "created_by_admin_id = NULL",
                        "uuid = ANY($1::uuid[])",
                    ),
                    body.uuids,
                )
                if "UPDATE " in result:
                    parts = result.split()
                    if len(parts) >= 2:
                        try:
                            success = int(parts[1])
                        except (ValueError, IndexError):
                            pass
            except Exception as e:
                success = 0
                errors = [BulkOperationError(uuid=u, error=str(e)) for u in body.uuids]

        failed = len(body.uuids) - success

        # Apply quota counter changes: previous owners lose the user
        # (unassign is like reassign to NULL — previous owner loses, no new owner gains)
        from shared.rbac import increment_usage_counter
        per_owner: dict = {}
        for r in rows:
            prev_id = r.get("created_by_admin_id")
            if prev_id is None:
                continue
            limit = r.get("traffic_limit_bytes") or 0
            used = r.get("used_traffic_bytes") or 0
            unused = max(0, limit - used)
            bucket = per_owner.setdefault(prev_id, {"count": 0, "unused": 0})
            bucket["count"] += 1
            if unused > 0:
                bucket["unused"] += unused
        try:
            for owner_id, bucket in per_owner.items():
                if bucket["count"] > 0:
                    await increment_usage_counter(owner_id, "users_created", -bucket["count"])
                if bucket["unused"] > 0:
                    await increment_usage_counter(owner_id, "traffic_used_bytes", -bucket["unused"])
        except Exception as e:
            logger.warning("Failed to update counters on bulk unassign: %s", e)

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.bulk_unassign_admin", resource="users", resource_id="bulk",
            details=json.dumps({"count": len(body.uuids), "success": success, "failed": failed}),
            ip_address=get_client_ip(request),
        )
        return BulkOperationResult(success=success, failed=failed, errors=errors)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("bulk_unassign_admin failed: %s", e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.post("/{user_uuid}/unassign-admin", response_model=SuccessResponse)
async def unassign_admin(
    user_uuid: str,
    request: Request,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Clear the created_by_admin_id for a user (superadmin only)."""
    if admin.role != "superadmin":
        raise api_error(403, E.FORBIDDEN)
    try:
        from shared.database import db_service
        if not db_service.is_connected:
            raise api_error(503, E.DB_UNAVAILABLE)
        previous_admin_id = None
        limit = 0
        used = 0
        async with db_service.acquire() as conn:
            existing = await conn.fetchrow(
                select_sql(USERS_TABLE, "created_by_admin_id, traffic_limit_bytes, used_traffic_bytes", "WHERE uuid = $1"),
                user_uuid,
            )
            if not existing:
                raise api_error(404, E.USER_NOT_FOUND)
            previous_admin_id = existing.get("created_by_admin_id")
            limit = existing.get("traffic_limit_bytes") or 0
            used = existing.get("used_traffic_bytes") or 0
            result = await conn.execute(
                update_sql(USERS_TABLE, "created_by_admin_id = NULL", "uuid = $1"),
                user_uuid,
            )
            if "UPDATE 0" in result:
                raise api_error(404, E.USER_NOT_FOUND)
        # Apply quota counter changes via shared helper
        if previous_admin_id is not None:
            from shared.rbac import increment_usage_counter
            await increment_usage_counter(previous_admin_id, "users_created", -1)
            unused = max(0, limit - used)
            if unused > 0:
                await increment_usage_counter(previous_admin_id, "traffic_used_bytes", -unused)
        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.unassign_admin", resource="users", resource_id=user_uuid,
            details=json.dumps({"cleared": True, "previous_admin_id": previous_admin_id}),
            ip_address=get_client_ip(request),
        )
        return SuccessResponse(message="Admin unassigned")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("unassign_admin failed: %s", e)
        raise api_error(500, E.INTERNAL_ERROR)


@router.get("/{user_uuid}/fetch-ips/result/{job_id}")
async def get_fetch_ips_result(
    user_uuid: str,
    job_id: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Получает результат сбора IP-адресов по jobId."""
    await _ensure_user_visible(admin, user_uuid)
    from shared.api_client import api_client

    try:
        result = await api_client.get_fetch_ips_result(job_id)
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to get fetch IPs result for job %s: %s", job_id, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.post("/{user_uuid}/drop-connections")
async def drop_user_connections(
    request: Request,
    user_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "edit")),
):
    """Сбрасывает активные соединения пользователя."""
    await _ensure_user_visible(admin, user_uuid)
    from shared.api_client import api_client

    body = await request.json()
    target_nodes = body.get("targetNodes", {"target": "allNodes"})

    try:
        result = await api_client.drop_connections(
            drop_by={"by": "userUuids", "userUuids": [user_uuid]},
            target_nodes=target_nodes,
        )
        payload = result.get("response", result) if isinstance(result, dict) else result

        await write_audit_log(
            admin_id=admin.account_id, admin_username=admin.username,
            action="user.drop_connections", resource="users", resource_id=user_uuid,
            details=json.dumps({"target_nodes": target_nodes}),
            ip_address=get_client_ip(request),
        )

        return payload
    except Exception as e:
        logger.error("Failed to drop connections for %s: %s", user_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


# ── Fetch Users IPs by Node ──────────────────────────────────────

@router.post("/node/{node_uuid}/fetch-users-ips")
async def fetch_users_ips_by_node(
    node_uuid: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Запускает сбор IP всех пользователей на ноде. Возвращает jobId."""
    from shared.api_client import api_client

    try:
        result = await api_client.fetch_users_ips_by_node(node_uuid)
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to fetch users IPs for node %s: %s", node_uuid, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)


@router.get("/node/{node_uuid}/fetch-users-ips/result/{job_id}")
async def get_fetch_users_ips_result(
    node_uuid: str,
    job_id: str,
    admin: AdminUser = Depends(require_permission("users", "view")),
):
    """Получает результат сбора IP пользователей по jobId."""
    from shared.api_client import api_client

    try:
        result = await api_client.get_fetch_users_ips_result(job_id)
        payload = result.get("response", result) if isinstance(result, dict) else result
        return payload
    except Exception as e:
        logger.error("Failed to get fetch users IPs result for job %s: %s", job_id, e)
        raise api_error(502, E.API_SERVICE_UNAVAILABLE)

