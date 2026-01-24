"""
Data access helpers.
Provides unified access to data from database (primary) with API fallback.
"""

from typing import Any, Dict, List, Optional

from src.services.database import db_service
from src.services.api_client import api_client
from src.utils.logger import logger


# ==================== User Access ====================

async def get_user_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    """
    Get user by UUID. Tries DB first, falls back to API.
    Returns user data in API format or None if not found.
    """
    # Try database first
    if db_service.is_connected:
        user = await db_service.get_user_by_uuid(uuid)
        if user and user.get("uuid"):
            logger.debug("User %s fetched from DB", uuid)
            return user
    
    # Fallback to API
    try:
        response = await api_client.get_user_by_uuid(uuid)
        user = response.get("response", {})
        if user:
            logger.debug("User %s fetched from API (DB miss)", uuid)
            return user
    except Exception as e:
        logger.warning("Failed to fetch user %s from API: %s", uuid, e)
    
    return None


async def get_user_by_uuid_wrapped(uuid: str) -> Dict[str, Any]:
    """
    Get user by UUID with response wrapper for backward compatibility.
    Returns {"response": user_data} format like API client.
    Falls back to API directly if not in DB.
    """
    # Try database first
    if db_service.is_connected:
        user = await db_service.get_user_by_uuid(uuid)
        if user and user.get("uuid"):
            logger.debug("User %s fetched from DB (wrapped)", uuid)
            return {"response": user}
    
    # Fallback to API (returns already wrapped)
    return await api_client.get_user_by_uuid(uuid)


async def get_user_by_short_uuid(short_uuid: str) -> Optional[Dict[str, Any]]:
    """Get user by short UUID. Tries DB first, falls back to API."""
    if db_service.is_connected:
        user = await db_service.get_user_by_short_uuid(short_uuid)
        if user and user.get("uuid"):
            return user
    
    try:
        response = await api_client.get_user_by_short_uuid(short_uuid)
        return response.get("response", {})
    except Exception:
        pass
    
    return None


# ==================== Token Access ====================

async def get_all_tokens() -> List[Dict[str, Any]]:
    """Get all API tokens. Tries DB first, falls back to API."""
    if db_service.is_connected:
        tokens = await db_service.get_all_tokens()
        if tokens:
            logger.debug("Tokens fetched from DB (%d)", len(tokens))
            return tokens
    
    try:
        response = await api_client.get_tokens()
        payload = response.get("response", {})
        
        # Handle different response formats
        if isinstance(payload, list):
            return payload
        elif isinstance(payload, dict):
            return payload.get("apiKeys") or payload.get("tokens") or []
    except Exception as e:
        logger.warning("Failed to fetch tokens from API: %s", e)
    
    return []


async def get_token_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    """Get token by UUID. Tries DB first, falls back to API."""
    if db_service.is_connected:
        token = await db_service.get_token_by_uuid(uuid)
        if token and token.get("uuid"):
            return token
    
    # API doesn't have get_token_by_uuid, so search in list
    tokens = await get_all_tokens()
    return next((t for t in tokens if t.get("uuid") == uuid), None)


# ==================== Template Access ====================

async def get_all_templates() -> List[Dict[str, Any]]:
    """Get all subscription templates. Tries DB first, falls back to API."""
    if db_service.is_connected:
        templates = await db_service.get_all_templates()
        if templates:
            logger.debug("Templates fetched from DB (%d)", len(templates))
            return templates
    
    try:
        response = await api_client.get_templates()
        payload = response.get("response", {})
        return payload.get("subscriptionTemplates", []) if isinstance(payload, dict) else []
    except Exception as e:
        logger.warning("Failed to fetch templates from API: %s", e)
    
    return []


async def get_template_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
    """Get template by UUID. Tries DB first, falls back to API."""
    if db_service.is_connected:
        tpl = await db_service.get_template_by_uuid(uuid)
        if tpl and tpl.get("uuid"):
            return tpl
    
    try:
        response = await api_client.get_template(uuid)
        return response.get("response", {})
    except Exception:
        pass
    
    return None


# ==================== Snippet Access ====================

async def get_all_snippets() -> List[Dict[str, Any]]:
    """Get all snippets. Tries DB first, falls back to API."""
    if db_service.is_connected:
        snippets = await db_service.get_all_snippets()
        if snippets:
            logger.debug("Snippets fetched from DB (%d)", len(snippets))
            return snippets
    
    try:
        response = await api_client.get_snippets()
        payload = response.get("response", {})
        return payload.get("snippets", []) if isinstance(payload, dict) else []
    except Exception as e:
        logger.warning("Failed to fetch snippets from API: %s", e)
    
    return []


async def get_snippet_by_name(name: str) -> Optional[Dict[str, Any]]:
    """Get snippet by name. Tries DB first, falls back to API."""
    if db_service.is_connected:
        snippet = await db_service.get_snippet_by_name(name)
        if snippet and snippet.get("name"):
            return snippet
    
    try:
        response = await api_client.get_snippet(name)
        return response.get("response", {})
    except Exception:
        pass
    
    return None


# ==================== Squad Access ====================

async def get_all_internal_squads() -> List[Dict[str, Any]]:
    """Get all internal squads. Tries DB first, falls back to API."""
    if db_service.is_connected:
        squads = await db_service.get_all_internal_squads()
        if squads:
            logger.debug("Internal squads fetched from DB (%d)", len(squads))
            return squads
    
    try:
        response = await api_client.get_internal_squads()
        payload = response.get("response", {})
        return payload.get("internalSquads", []) if isinstance(payload, dict) else []
    except Exception as e:
        logger.warning("Failed to fetch internal squads from API: %s", e)
    
    return []


async def get_all_external_squads() -> List[Dict[str, Any]]:
    """Get all external squads. Tries DB first, falls back to API."""
    if db_service.is_connected:
        squads = await db_service.get_all_external_squads()
        if squads:
            logger.debug("External squads fetched from DB (%d)", len(squads))
            return squads
    
    try:
        response = await api_client.get_external_squads()
        payload = response.get("response", {})
        return payload.get("externalSquads", []) if isinstance(payload, dict) else []
    except Exception as e:
        logger.warning("Failed to fetch external squads from API: %s", e)
    
    return []


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


# ==================== Host Access ====================

async def get_all_hosts() -> List[Dict[str, Any]]:
    """Get all hosts. Tries DB first, falls back to API."""
    if db_service.is_connected:
        hosts = await db_service.get_all_hosts()
        if hosts:
            logger.debug("Hosts fetched from DB (%d)", len(hosts))
            return hosts
    
    try:
        response = await api_client.get_hosts()
        return response.get("response", [])
    except Exception as e:
        logger.warning("Failed to fetch hosts from API: %s", e)
    
    return []


async def get_all_hosts_wrapped() -> Dict[str, Any]:
    """Get all hosts with response wrapper for backward compatibility."""
    if db_service.is_connected:
        hosts = await db_service.get_all_hosts()
        if hosts:
            logger.debug("Hosts fetched from DB (wrapped, %d)", len(hosts))
            return {"response": hosts}
    
    return await api_client.get_hosts()


# ==================== Node Access ====================

async def get_all_nodes() -> List[Dict[str, Any]]:
    """Get all nodes. Tries DB first, falls back to API."""
    if db_service.is_connected:
        nodes = await db_service.get_all_nodes()
        if nodes:
            logger.debug("Nodes fetched from DB (%d)", len(nodes))
            return nodes
    
    try:
        response = await api_client.get_nodes()
        return response.get("response", [])
    except Exception as e:
        logger.warning("Failed to fetch nodes from API: %s", e)
    
    return []


async def get_all_nodes_wrapped() -> Dict[str, Any]:
    """Get all nodes with response wrapper for backward compatibility."""
    if db_service.is_connected:
        nodes = await db_service.get_all_nodes()
        if nodes:
            logger.debug("Nodes fetched from DB (wrapped, %d)", len(nodes))
            return {"response": nodes}
    
    return await api_client.get_nodes()
