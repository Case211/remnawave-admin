"""Update checker — compares current version with GitHub Releases."""
import logging
import time
from typing import Optional, Dict, Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_REPO = "Case211/remnawave-admin"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
CURRENT_VERSION = "2.0.0"

# Cache: check at most once every 30 minutes
_cache: Dict[str, Any] = {}
_cache_ts: float = 0
_CACHE_TTL = 1800  # 30 min


async def check_for_updates() -> Dict[str, Any]:
    """Check GitHub for latest release. Returns version info with changelog."""
    global _cache, _cache_ts

    if time.time() - _cache_ts < _CACHE_TTL and _cache:
        return _cache

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
                # No releases yet
                result = {
                    "current_version": CURRENT_VERSION,
                    "latest_version": None,
                    "update_available": False,
                    "release_url": None,
                    "changelog": None,
                    "published_at": None,
                }
                _cache = result
                _cache_ts = time.time()
                return result

            resp.raise_for_status()
            data = resp.json()

            latest_tag = data.get("tag_name", "").lstrip("v")
            release_url = data.get("html_url", "")
            changelog = data.get("body", "")
            published_at = data.get("published_at")

            update_available = _compare_versions(CURRENT_VERSION, latest_tag)

            result = {
                "current_version": CURRENT_VERSION,
                "latest_version": latest_tag or None,
                "update_available": update_available,
                "release_url": release_url,
                "changelog": changelog[:2000] if changelog else None,
                "published_at": published_at,
            }
            _cache = result
            _cache_ts = time.time()
            return result

    except Exception as e:
        logger.warning("Update check failed: %s", e)
        return {
            "current_version": CURRENT_VERSION,
            "latest_version": None,
            "update_available": False,
            "release_url": None,
            "changelog": None,
            "published_at": None,
            "error": str(e),
        }


def _compare_versions(current: str, latest: str) -> bool:
    """Simple semver comparison. Returns True if latest > current."""
    if not latest:
        return False
    try:
        current_parts = [int(x) for x in current.split(".")]
        latest_parts = [int(x) for x in latest.split(".")]
        return latest_parts > current_parts
    except (ValueError, TypeError):
        return False


async def get_dependency_versions() -> Dict[str, Any]:
    """Collect versions of key dependencies."""
    deps = {}

    # Python version
    import sys
    deps["python"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"

    # PostgreSQL version
    try:
        from src.services.database import db_service
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

    # Xray versions on nodes
    try:
        from src.services.database import db_service
        if db_service.is_connected:
            async with db_service.acquire() as conn:
                rows = await conn.fetch(
                    "SELECT name, xray_version FROM nodes WHERE xray_version IS NOT NULL"
                )
                xray_versions = {}
                for r in rows:
                    xray_versions[r["name"]] = r["xray_version"]
                deps["xray_nodes"] = xray_versions
    except Exception:
        deps["xray_nodes"] = {}

    return deps
