"""Dependencies for public API v3 — API key authentication and rate limiting."""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)


@dataclass
class ApiKeyUser:
    """Authenticated API key context."""
    key_id: int
    key_name: str
    scopes: List[str] = field(default_factory=list)
    # Ограничение по юзерам: только эти сквады и/или тег; пусто — все юзеры
    user_squads: List[str] = field(default_factory=list)
    user_tag: Optional[str] = None

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    @property
    def restricts_users(self) -> bool:
        return bool(self.user_squads or self.user_tag)

    def user_scope_condition(self, next_idx: int, column: str = "uuid") -> Tuple[str, list]:
        """SQL-условие «юзер в пределах ключа» с аргументами, начиная с $next_idx.

        Пустая строка — ключ не ограничен. column — поле с uuid юзера в
        основном запросе (у нарушений это user_uuid).
        """
        if not self.restricts_users:
            return "", []
        parts, args = [], []
        if self.user_squads:
            parts.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements("
                "COALESCE(su.raw_data::jsonb->'activeInternalSquads', '[]'::jsonb)) s "
                f"WHERE s->>'uuid' = ANY(${next_idx}::text[]))"
            )
            args.append(self.user_squads)
            next_idx += 1
        if self.user_tag:
            parts.append(f"su.raw_data::jsonb->>'tag' = ${next_idx}")
            args.append(self.user_tag)
        return f"{column} IN (SELECT su.uuid FROM users su WHERE {' AND '.join(parts)})", args


async def require_api_key(request: Request) -> ApiKeyUser:
    """Dependency: extract and validate X-API-Key header."""
    raw_key = request.headers.get("X-API-Key")
    if not raw_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
        )

    from web.backend.core.api_key_auth import validate_api_key
    from web.backend.api.deps import get_client_ip
    key_data = await validate_api_key(raw_key, get_client_ip(request))
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    user = ApiKeyUser(
        key_id=key_data["id"],
        key_name=key_data["name"],
        scopes=key_data["scopes"],
        user_squads=key_data.get("user_squads") or [],
        user_tag=key_data.get("user_tag"),
    )
    # Stash on request.state so rate-limit keyfunc can read it without re-auth.
    request.state.api_key_user = user
    return user


def require_scope(scope: str):
    """Dependency factory: check that the API key has a specific scope AND
    enforces a per-key rate limit (read/write/bulk) based on method+path.
    """
    async def _check(request: Request) -> ApiKeyUser:
        api_key = await require_api_key(request)
        if not api_key.has_scope(scope):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing scope: {scope}",
            )
        # Apply rate limit per request method/path.
        from web.backend.api.v3.rate_limit import read_limit, write_limit, bulk_limit
        path = request.url.path or ""
        method = request.method.upper()
        if "/bulk/" in path:
            await bulk_limit(request)
        elif method == "GET":
            await read_limit(request)
        else:
            await write_limit(request)
        return api_key
    return _check


def api_key_identifier(request: Request) -> str:
    """key_func for slowapi — bucket by API key id, fall back to IP."""
    user = getattr(request.state, "api_key_user", None)
    if user is not None:
        return f"apikey:{user.key_id}"
    # Before dependency runs (shouldn't really happen if decorator comes after Depends)
    from slowapi.util import get_remote_address
    return f"ip:{get_remote_address(request)}"
