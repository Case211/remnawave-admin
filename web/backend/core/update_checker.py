"""Update checker — fetches current version from GitHub Releases."""
import logging
import time
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_REPO = "Case211/remnawave-admin"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"

# Fallback version shown when GitHub API is unreachable
_FALLBACK_VERSION = "unknown"

# Cache: check at most once every 30 minutes
_cache: Dict[str, Any] = {}
_cache_ts: float = 0
_CACHE_TTL = 1800  # 30 min


async def _fetch_latest_release() -> Optional[Dict[str, Any]]:
    """Fetch latest release data from GitHub API. Returns None on failure."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                GITHUB_API_URL,
                headers={
                    "Accept": "application/vnd.github.v3+json",
                    "User-Agent": "remnawave-admin/update-checker",
                },
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
    except Exception as e:
        logger.warning("GitHub API request failed: %s", e)
        return None


async def get_latest_version() -> str:
    """Return the latest release version from GitHub (cached)."""
    if _cache and _cache.get("current_version"):
        return _cache["current_version"]
    result = await check_for_updates()
    return result.get("current_version") or _FALLBACK_VERSION


async def check_for_updates() -> Dict[str, Any]:
    """Check GitHub for latest release. Returns version info with changelog."""
    global _cache, _cache_ts

    if time.time() - _cache_ts < _CACHE_TTL and _cache:
        return _cache

    data = await _fetch_latest_release()

    if data is None:
        result = {
            "current_version": _cache.get("current_version") or _FALLBACK_VERSION,
            "latest_version": None,
            "update_available": False,
            "release_url": None,
            "changelog": None,
            "published_at": None,
        }
        _cache = result
        _cache_ts = time.time()
        return result

    latest_tag = data.get("tag_name", "").lstrip("v")
    release_url = data.get("html_url", "")
    changelog = data.get("body", "")
    published_at = data.get("published_at")

    result = {
        "current_version": latest_tag or _FALLBACK_VERSION,
        "latest_version": latest_tag or None,
        "update_available": False,
        "release_url": release_url,
        "changelog": changelog[:2000] if changelog else None,
        "published_at": published_at,
    }
    _cache = result
    _cache_ts = time.time()
    return result


async def get_dependency_versions() -> Dict[str, Any]:
    """Collect versions of key dependencies."""
    deps = {}

    # Python version
    import sys
    deps["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # PostgreSQL version
    try:
        from shared.database import db_service
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                row = await conn.fetchval("SELECT version()")
                if row:
                    # "PostgreSQL 16.1 ..."
                    parts = row.split()
                    deps["postgresql"] = parts[1] if len(parts) > 1 else row
    except Exception:
        deps["postgresql"] = None

    # FastAPI version
    try:
        import fastapi
        deps["fastapi"] = fastapi.__version__
    except Exception:
        deps["fastapi"] = None

    # Xray versions on nodes (extract from raw_data JSON if available)
    try:
        from shared.database import db_service
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                # Check if xray_version column exists
                col_exists = await conn.fetchval(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'nodes' AND column_name = 'xray_version'
                    )
                    """
                )
                if col_exists:
                    rows = await conn.fetch(
                        "SELECT name, xray_version FROM nodes WHERE xray_version IS NOT NULL"
                    )
                    deps["xray_nodes"] = {r["name"]: r["xray_version"] for r in rows}
                else:
                    # Try extracting from raw_data JSON
                    rows = await conn.fetch(
                        "SELECT name, raw_data FROM nodes WHERE raw_data IS NOT NULL"
                    )
                    xray_versions = {}
                    for r in rows:
                        rd = r["raw_data"] if isinstance(r["raw_data"], dict) else {}
                        ver = rd.get("xray_version") or rd.get("xrayVersion")
                        if ver and r["name"]:
                            xray_versions[r["name"]] = ver
                    deps["xray_nodes"] = xray_versions
    except Exception:
        deps["xray_nodes"] = {}

    return deps
