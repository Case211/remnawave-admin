"""
Data access helpers.
Provides unified access to data from database (primary) with API fallback.
"""

from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional

from shared.database import db_service
from shared.api_client import api_client
from shared.logger import logger
from shared.db_schema import INTERNAL_SQUADS_TABLE, EXTERNAL_SQUADS_TABLE
from shared.db_query import select_sql


# ==================== Generic Helpers ====================

async def _fetch_single(
    id_value: str,
    db_method: Callable[[str], Awaitable[Optional[Dict[str, Any]]]],
    api_method: Callable[[str], Awaitable[Dict[str, Any]]],
    entity_name: str,
    id_field: str = "uuid",
) -> Optional[Dict[str, Any]]:
    if db_service.is_connected:
        result = await db_method(id_value)
        if result and result.get(id_field):
            logger.debug("%s %s fetched from DB", entity_name.title(), id_value)
            return result
    try:
        response = await api_method(id_value)
        data = response.get("response", {})
        if data:
            logger.debug("%s %s fetched from API (DB miss)", entity_name.title(), id_value)
            return data
    except Exception as e:
        logger.warning("Failed to fetch %s %s from API: %s", entity_name, id_value, e)
    return None


async def _fetch_single_wrapped(
    id_value: str,
    db_method: Callable[[str], Awaitable[Optional[Dict[str, Any]]]],
    api_method: Callable[[str], Awaitable[Dict[str, Any]]],
    entity_name: str,
    id_field: str = "uuid",
) -> Dict[str, Any]:
    if db_service.is_connected:
        result = await db_method(id_value)
        if result and result.get(id_field):
            logger.debug("%s %s fetched from DB (wrapped)", entity_name.title(), id_value)
            return {"response": result}
    return await api_method(id_value)


async def _fetch_list(
    db_method: Callable[[], Awaitable[List[Dict[str, Any]]]],
    api_method: Callable[[], Awaitable[Dict[str, Any]]],
    entity_name: str,
    response_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if db_service.is_connected:
        items = await db_method()
        if items:
            logger.debug("%s fetched from DB (%d)", entity_name.title(), len(items))
            return items
    try:
        response = await api_method()
        payload = response.get("response", {})
        if response_key is None:
            return payload if isinstance(payload, list) else []
        return payload.get(response_key, []) if isinstance(payload, dict) else []
    except Exception as e:
        logger.warning("Failed to fetch %s from API: %s", entity_name, e)
    return []


async def _fetch_list_wrapped(
    db_method: Callable[[], Awaitable[List[Dict[str, Any]]]],
    api_method: Callable[[], Awaitable[Dict[str, Any]]],
    entity_name: str,
) -> Dict[str, Any]:
    if db_service.is_connected:
        items = await db_method()
        if items:
            logger.debug("%s fetched from DB (wrapped, %d)", entity_name.title(), len(items))
            return {"response": items}
    return await api_method()


# ==================== User Access ====================

async def _api_user_by_id_fallback(identifier: str) -> dict:
    """Panel v3 has no uuid lookup — the API fallback only works for numeric ids."""
    if isinstance(identifier, str) and identifier.isdigit():
        return await api_client.get_user_by_id(int(identifier))
    return {}


async def get_user_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(uuid, db_service.get_user_by_uuid, _api_user_by_id_fallback, "user")


async def get_user_by_uuid_wrapped(uuid: str) -> Dict[str, Any]:
    return await _fetch_single_wrapped(uuid, db_service.get_user_by_uuid, _api_user_by_id_fallback, "user")


async def get_user_by_short_uuid(short_uuid: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(short_uuid, db_service.get_user_by_short_uuid, api_client.get_user_by_short_uuid, "user")


# ==================== Panel Identifier Resolution ====================

async def resolve_panel_user_id(user_uuid: str) -> str | int:
    """Resolve a local user uuid to the identifier the panel API expects.

    v3 panels identify users by numeric id (stored in users.id); v2 by the
    user's uuid. When the local row carries a panel id we return it,
    otherwise we fall back to the local uuid (v2).
    """
    if db_service.is_connected and user_uuid:
        try:
            panel_id = await db_service.get_user_panel_id_by_uuid(user_uuid)
            if panel_id is not None:
                return panel_id
        except Exception as e:
            logger.debug("resolve_panel_user_id(%s) failed: %s", user_uuid, e)
    return user_uuid


async def resolve_panel_user_ids(user_uuids: list[str]) -> list[str | int]:
    """Batch version of resolve_panel_user_id for a list of local uuids."""
    if not user_uuids:
        return []
    if db_service.is_connected:
        try:
            mapping = await db_service.get_panel_ids_by_uuids(user_uuids)
            return [mapping.get(u, u) for u in user_uuids]
        except Exception as e:
            logger.debug("resolve_panel_user_ids failed: %s", e)
    return list(user_uuids)


# ==================== Template Access ====================

async def get_all_templates() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_templates, api_client.get_templates, "templates", "subscriptionTemplates")


async def get_template_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(uuid, db_service.get_template_by_uuid, api_client.get_template, "template")


# ==================== Snippet Access ====================

async def get_all_snippets() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_snippets, api_client.get_snippets, "snippets", "snippets")


async def get_snippet_by_name(name: str) -> Optional[Dict[str, Any]]:
    return await _fetch_single(name, db_service.get_snippet_by_name, api_client.get_snippet, "snippet", id_field="name")


# ==================== Squad Access ====================

async def get_all_internal_squads() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_internal_squads, api_client.get_internal_squads, "internal squads", "internalSquads")


async def get_all_external_squads() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_external_squads, api_client.get_external_squads, "external squads", "externalSquads")


async def get_all_squads() -> tuple[List[Dict[str, Any]], str]:
    """
    Get all squads (internal first, then external if empty).
    Returns tuple of (squads_list, source) where source is "internal" or "external".
    """
    squads = await get_all_internal_squads()
    if squads:
        return squads, "internal"
    
    squads = await get_all_external_squads()
    return squads, "external"


async def get_squads_for_admin(
    account_id: Optional[int],
    role_id: Optional[int],
    role: Optional[str],
) -> tuple[List[Dict[str, Any]], str]:
    """
    Get squads filtered by admin's access scope.
    Returns tuple of (squads_list, source) where source is "internal" or "external".
    """
    from shared.rbac import get_scope
    
    squad_scope = await get_scope(account_id, role_id, role, "squad", "view")
    
    # If no scope restriction (superadmin, legacy, or no policies), return all squads
    if squad_scope is None:
        return await get_all_squads()
    
    # If scope is empty set, admin has no access to any squads
    if not squad_scope:
        return [], "internal"
    
    squad_list = list(squad_scope)
    
    # Fetch internal squads that match the scope
    if db_service.is_connected:
        try:
            rows = await db_service._pool.fetch(
                select_sql(
                    INTERNAL_SQUADS_TABLE,
                    "*",
                    "WHERE uuid = ANY($1::uuid[])",
                ),
                squad_list
            )
            internal_squads = [dict(row) for row in rows]
            if internal_squads:
                return internal_squads, "internal"
        except Exception as e:
            logger.warning("Failed to fetch internal squads for admin scope: %s", e)
    
    # Fallback to API for internal squads
    try:
        response = await api_client.get_internal_squads()
        payload = response.get("response", {})
        all_internal = payload.get("internalSquads", []) if isinstance(payload, dict) else []
        filtered = [s for s in all_internal if s.get("uuid", "").lower() in squad_scope]
        if filtered:
            return filtered, "internal"
    except Exception as e:
        logger.warning("Failed to fetch internal squads from API for admin scope: %s", e)
    
    # If no internal squads match, try external squads
    if db_service.is_connected:
        try:
            rows = await db_service._pool.fetch(
                select_sql(
                    EXTERNAL_SQUADS_TABLE,
                    "*",
                    "WHERE uuid = ANY($1::uuid[])",
                ),
                squad_list
            )
            external_squads = [dict(row) for row in rows]
            if external_squads:
                return external_squads, "external"
        except Exception as e:
            logger.warning("Failed to fetch external squads for admin scope: %s", e)
    
    # Fallback to API for external squads
    try:
        response = await api_client.get_external_squads()
        payload = response.get("response", {})
        all_external = payload.get("externalSquads", []) if isinstance(payload, dict) else []
        filtered = [s for s in all_external if s.get("uuid", "").lower() in squad_scope]
        return filtered, "external"
    except Exception as e:
        logger.warning("Failed to fetch external squads from API for admin scope: %s", e)
    
    return [], "internal"


async def _scoped_squads_by_type(
    account_id: Optional[int],
    role_id: Optional[int],
    role: Optional[str],
    fetch_all,
) -> List[Dict[str, Any]]:
    """Squads of a single type (internal OR external), filtered by the admin's
    squad:view scope. Returns the full list when the admin has no scope
    restriction (superadmin/legacy), an empty list when the admin has no
    squad access."""
    from shared.rbac import get_scope

    squad_scope = await get_scope(account_id, role_id, role, "squad", "view")
    if squad_scope is None:
        return await fetch_all()
    if not squad_scope:
        return []
    all_squads = await fetch_all()
    return [s for s in all_squads if str(s.get("uuid", "")).lower() in squad_scope]


async def get_internal_squads_for_admin(
    account_id: Optional[int],
    role_id: Optional[int],
    role: Optional[str],
) -> List[Dict[str, Any]]:
    """Internal squads visible to the admin (scope-filtered)."""
    return await _scoped_squads_by_type(account_id, role_id, role, get_all_internal_squads)


async def get_external_squads_for_admin(
    account_id: Optional[int],
    role_id: Optional[int],
    role: Optional[str],
) -> List[Dict[str, Any]]:
    """External squads visible to the admin (scope-filtered)."""
    return await _scoped_squads_by_type(account_id, role_id, role, get_all_external_squads)


# ==================== Host Access ====================

async def get_all_hosts() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_hosts, api_client.get_hosts, "hosts")


async def get_all_hosts_wrapped() -> Dict[str, Any]:
    return await _fetch_list_wrapped(db_service.get_all_hosts, api_client.get_hosts, "hosts")


# ==================== Node Access ====================

async def get_all_nodes() -> List[Dict[str, Any]]:
    return await _fetch_list(db_service.get_all_nodes, api_client.get_nodes, "nodes")


async def get_all_nodes_wrapped() -> Dict[str, Any]:
    return await _fetch_list_wrapped(db_service.get_all_nodes, api_client.get_nodes, "nodes")
