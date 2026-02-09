"""Settings API endpoints - CRUD for bot_config table."""
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser, require_permission

logger = logging.getLogger(__name__)

router = APIRouter()


class ConfigItemResponse(BaseModel):
    """Single config item."""
    key: str
    value: Optional[str] = None
    value_type: str = "string"
    category: str = "general"
    subcategory: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    default_value: Optional[str] = None
    env_var_name: Optional[str] = None
    env_value: Optional[str] = None
    is_secret: bool = False
    is_readonly: bool = False
    is_env_override: bool = False
    source: str = "default"  # "db", "env", "default"
    options: Optional[List[str]] = None
    sort_order: int = 0


class ConfigUpdateRequest(BaseModel):
    """Update config value."""
    value: str


class ConfigByCategoryResponse(BaseModel):
    """Config items grouped by category."""
    categories: Dict[str, List[ConfigItemResponse]]


def _determine_source(db_value: Optional[str], env_var_name: Optional[str], default_value: Optional[str]) -> str:
    """Determine effective value source. Priority: DB > .env > default."""
    if db_value is not None:
        return "db"
    if env_var_name:
        env_val = os.getenv(env_var_name)
        if env_val is not None and env_val != "":
            return "env"
    if default_value is not None:
        return "default"
    return "none"


def _effective_value(db_value: Optional[str], env_var_name: Optional[str], default_value: Optional[str]) -> Optional[str]:
    """Get effective value based on priority: DB > .env > default."""
    if db_value is not None:
        return db_value
    if env_var_name:
        env_val = os.getenv(env_var_name)
        if env_val is not None and env_val != "":
            return env_val
    return default_value


@router.get("", response_model=ConfigByCategoryResponse)
async def get_all_settings(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Get all settings grouped by category. Priority: DB > .env > default."""
    try:
        from src.services.database import db_service
        from src.services.config_service import DEFAULT_CONFIG_DEFINITIONS
        if not db_service.is_connected:
            return ConfigByCategoryResponse(categories={})

        # Only show keys that exist in current definitions
        valid_keys = {d['key'] for d in DEFAULT_CONFIG_DEFINITIONS}

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT key, value, value_type, category, subcategory,
                       display_name, description, default_value, env_var_name,
                       is_secret, is_readonly, validation_regex, options_json,
                       sort_order, created_at, updated_at
                FROM bot_config
                ORDER BY category, sort_order, key
                """
            )

        categories: Dict[str, List[ConfigItemResponse]] = {}
        for row in rows:
            if row['key'] not in valid_keys:
                continue
            row_dict = dict(row)
            category = row_dict.get('category', 'general')

            # Parse options
            options = None
            if row_dict.get('options_json'):
                try:
                    options = json.loads(row_dict['options_json'])
                except Exception:
                    pass

            db_value = row_dict.get('value')
            env_var_name = row_dict.get('env_var_name')
            default_value = row_dict.get('default_value')

            source = _determine_source(db_value, env_var_name, default_value)
            effective = _effective_value(db_value, env_var_name, default_value)

            # Check if env var exists (informational, not blocking)
            has_env = False
            env_display = None
            if env_var_name:
                env_val = os.getenv(env_var_name)
                if env_val is not None and env_val != "":
                    has_env = True
                    env_display = env_val

            # Mask secret values
            display_value = effective
            if row_dict.get('is_secret') and display_value:
                display_value = display_value[:3] + '***' if len(display_value) > 3 else '***'
                if env_display:
                    env_display = env_display[:3] + '***' if len(env_display) > 3 else '***'

            item = ConfigItemResponse(
                key=row_dict['key'],
                value=display_value,
                value_type=row_dict.get('value_type', 'string'),
                category=category,
                subcategory=row_dict.get('subcategory'),
                display_name=row_dict.get('display_name'),
                description=row_dict.get('description'),
                default_value=default_value,
                env_var_name=env_var_name,
                env_value=env_display,
                is_secret=row_dict.get('is_secret', False),
                is_readonly=row_dict.get('is_readonly', False),
                is_env_override=has_env,
                source=source,
                options=options,
                sort_order=row_dict.get('sort_order', 0),
            )

            if category not in categories:
                categories[category] = []
            categories[category].append(item)

        return ConfigByCategoryResponse(categories=categories)

    except ImportError:
        return ConfigByCategoryResponse(categories={})
    except Exception as e:
        logger.error("Error fetching settings: %s", e)
        return ConfigByCategoryResponse(categories={})


@router.put("/{key}")
async def update_setting(
    key: str,
    data: ConfigUpdateRequest,
    admin: AdminUser = Depends(require_permission("settings", "edit")),
):
    """Update a single setting value. DB takes priority over .env."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            raise HTTPException(status_code=503, detail="Database not connected")

        # Check if setting exists and is editable
        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT key, is_readonly, env_var_name, is_secret FROM bot_config WHERE key = $1",
                key
            )

        if not row:
            raise HTTPException(status_code=404, detail="Setting not found")

        if row['is_readonly']:
            raise HTTPException(status_code=403, detail="Setting is read-only")

        # Update in DB (no env blocking — DB takes priority now)
        async with db_service.acquire() as conn:
            await conn.execute(
                "UPDATE bot_config SET value = $2, updated_at = NOW() WHERE key = $1",
                key, data.value
            )

        # Update config_service cache for immediate effect
        try:
            from src.services.config_service import config_service
            if key in config_service._cache:
                config_service._cache[key].value = data.value
                config_service._cache[key].updated_at = datetime.utcnow()
        except Exception:
            pass

        return {"status": "ok", "key": key}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating setting %s: %s", key, e)
        raise HTTPException(status_code=500, detail="Internal error")


@router.delete("/{key}")
async def reset_setting(
    key: str,
    admin: AdminUser = Depends(require_permission("settings", "edit")),
):
    """Reset a setting to default (remove DB value, fallback to .env or default)."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            raise HTTPException(status_code=503, detail="Database not connected")

        async with db_service.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT key, is_readonly FROM bot_config WHERE key = $1",
                key
            )

        if not row:
            raise HTTPException(status_code=404, detail="Setting not found")

        if row['is_readonly']:
            raise HTTPException(status_code=403, detail="Setting is read-only")

        # Set value to NULL — fallback to .env or default
        async with db_service.acquire() as conn:
            await conn.execute(
                "UPDATE bot_config SET value = NULL, updated_at = NOW() WHERE key = $1",
                key
            )

        # Update config_service cache
        try:
            from src.services.config_service import config_service
            if key in config_service._cache:
                config_service._cache[key].value = None
                config_service._cache[key].updated_at = datetime.utcnow()
        except Exception:
            pass

        return {"status": "ok", "key": key, "reset": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resetting setting %s: %s", key, e)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/ip-whitelist")
async def get_ip_whitelist(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Get current IP whitelist configuration."""
    from web.backend.core.config import get_web_settings
    from web.backend.core.ip_whitelist import parse_ip_list

    settings = get_web_settings()
    ips = parse_ip_list(settings.allowed_ips)
    return {
        "enabled": len(ips) > 0,
        "ips": ips,
        "env_var": "WEB_ALLOWED_IPS",
    }


@router.put("/ip-whitelist")
async def update_ip_whitelist(
    data: ConfigUpdateRequest,
    admin: AdminUser = Depends(require_permission("settings", "edit")),
):
    """Update IP whitelist. Value is a comma-separated list of IPs/CIDRs.

    The setting is stored as WEB_ALLOWED_IPS environment variable override.
    Changes take effect after restart (env vars are read at startup).
    To apply immediately, the value is also hot-patched into the running config.
    """
    import ipaddress

    # Validate all entries
    entries = [ip.strip() for ip in data.value.split(",") if ip.strip()] if data.value.strip() else []
    for entry in entries:
        try:
            if "/" in entry:
                ipaddress.ip_network(entry, strict=False)
            else:
                ipaddress.ip_address(entry)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid IP/CIDR: {entry}")

    # Hot-patch the running config
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    new_value = ",".join(entries)

    # Update the env var so middleware picks it up
    os.environ["WEB_ALLOWED_IPS"] = new_value
    # Also patch the cached settings object
    object.__setattr__(settings, "allowed_ips", new_value)

    logger.info("IP whitelist updated by %s: %s", admin.username, new_value or "(disabled)")

    return {"status": "ok", "ips": entries, "enabled": len(entries) > 0}


@router.get("/sync-status")
async def get_sync_status(
    admin: AdminUser = Depends(require_permission("settings", "view")),
):
    """Get sync status for all entity types."""
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return {"items": []}

        async with db_service.acquire() as conn:
            rows = await conn.fetch(
                "SELECT * FROM sync_metadata ORDER BY key"
            )

        return {
            "items": [
                {
                    "key": row['key'],
                    "last_sync_at": row['last_sync_at'].isoformat() if row['last_sync_at'] else None,
                    "sync_status": row['sync_status'],
                    "error_message": row.get('error_message'),
                    "records_synced": row.get('records_synced', 0),
                }
                for row in rows
            ]
        }

    except Exception as e:
        logger.error("Error fetching sync status: %s", e)
        return {"items": []}


@router.post("/sync/{entity}")
async def trigger_sync(
    entity: str,
    admin: AdminUser = Depends(require_permission("settings", "edit")),
):
    """Trigger manual sync for a specific entity type."""
    try:
        from src.services.sync import sync_service

        sync_methods = {
            'users': sync_service.sync_users,
            'nodes': sync_service.sync_nodes,
            'hosts': sync_service.sync_hosts,
            'config_profiles': sync_service.sync_config_profiles,
            'hwid_devices': sync_service.sync_all_hwid_devices,
            'all': sync_service.full_sync,
        }

        if entity == 'asn':
            from src.services.asn_parser import ASNParser
            from src.services.database import db_service
            parser = ASNParser(db_service)
            try:
                stats = await parser.sync_russian_asn_database(limit=None)
                records = stats.get('success', 0) if isinstance(stats, dict) else 0
                await db_service.update_sync_metadata(
                    key="asn", status="success", records_synced=records
                )
                result = stats
            except Exception as asn_err:
                await db_service.update_sync_metadata(
                    key="asn", status="error", error_message=str(asn_err)
                )
                raise
            finally:
                await parser.close()
        else:
            method = sync_methods.get(entity)
            if not method:
                raise HTTPException(status_code=400, detail=f"Unknown entity: {entity}")
            result = await method()
        return {"success": True, "entity": entity, "result": result}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error triggering sync for %s: %s", entity, e)
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
