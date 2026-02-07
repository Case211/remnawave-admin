"""Settings API endpoints - CRUD for bot_config table."""
import logging
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

# Add src to path for importing bot services
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from web.backend.api.deps import get_current_admin, AdminUser

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
    is_secret: bool = False
    is_readonly: bool = False
    is_env_override: bool = False
    options: Optional[List[str]] = None
    sort_order: int = 0


class ConfigUpdateRequest(BaseModel):
    """Update config value."""
    value: str


class ConfigByCategoryResponse(BaseModel):
    """Config items grouped by category."""
    categories: Dict[str, List[ConfigItemResponse]]


@router.get("", response_model=ConfigByCategoryResponse)
async def get_all_settings(
    admin: AdminUser = Depends(get_current_admin),
):
    """Get all settings grouped by category."""
    import os
    try:
        from src.services.database import db_service
        if not db_service.is_connected:
            return ConfigByCategoryResponse(categories={})

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
            row_dict = dict(row)
            category = row_dict.get('category', 'general')

            # Parse options
            options = None
            if row_dict.get('options_json'):
                import json
                try:
                    options = json.loads(row_dict['options_json'])
                except Exception:
                    pass

            # Check if env var overrides
            is_env_override = False
            if row_dict.get('env_var_name'):
                env_val = os.getenv(row_dict['env_var_name'])
                if env_val is not None and env_val != "":
                    is_env_override = True

            # Mask secret values
            display_value = row_dict.get('value')
            if row_dict.get('is_secret') and display_value:
                display_value = display_value[:3] + '***' if len(display_value) > 3 else '***'

            item = ConfigItemResponse(
                key=row_dict['key'],
                value=display_value,
                value_type=row_dict.get('value_type', 'string'),
                category=category,
                subcategory=row_dict.get('subcategory'),
                display_name=row_dict.get('display_name'),
                description=row_dict.get('description'),
                default_value=row_dict.get('default_value'),
                env_var_name=row_dict.get('env_var_name'),
                is_secret=row_dict.get('is_secret', False),
                is_readonly=row_dict.get('is_readonly', False),
                is_env_override=is_env_override,
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
    admin: AdminUser = Depends(get_current_admin),
):
    """Update a single setting value."""
    import os
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

        # Check if env var overrides
        if row.get('env_var_name'):
            env_val = os.getenv(row['env_var_name'])
            if env_val is not None and env_val != "":
                raise HTTPException(
                    status_code=409,
                    detail=f"Setting is overridden by env variable {row['env_var_name']}"
                )

        # Update in DB
        async with db_service.acquire() as conn:
            await conn.execute(
                "UPDATE bot_config SET value = $2, updated_at = NOW() WHERE key = $1",
                key, data.value
            )

        # Also update config_service cache if available
        try:
            from src.services.config_service import config_service
            if key in config_service._cache:
                config_service._cache[key].value = data.value
        except Exception:
            pass

        return {"status": "ok", "key": key}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error updating setting %s: %s", key, e)
        raise HTTPException(status_code=500, detail="Internal error")


@router.get("/sync-status")
async def get_sync_status(
    admin: AdminUser = Depends(get_current_admin),
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
