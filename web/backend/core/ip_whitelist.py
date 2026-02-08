"""IP whitelist middleware for the web admin panel.

If WEB_ALLOWED_IPS is configured, only those IPs can access the API.
Empty / not set = no restriction (allow all).
Supports individual IPs and CIDR notation (e.g. 192.168.1.0/24).
"""
import ipaddress
import logging
from typing import List, Optional, Set

from web.backend.core.config import get_web_settings

logger = logging.getLogger(__name__)


def parse_ip_list(raw: str) -> List[str]:
    """Parse comma-separated IP/CIDR string into a list of trimmed entries."""
    if not raw or not raw.strip():
        return []
    return [ip.strip() for ip in raw.split(",") if ip.strip()]


def is_ip_allowed(client_ip: str, allowed_list: List[str]) -> bool:
    """Check if client_ip is in the allowed list.

    Supports both plain IPs (1.2.3.4) and CIDR (10.0.0.0/8).
    Returns True if allowed_list is empty (no restriction).
    """
    if not allowed_list:
        return True

    try:
        addr = ipaddress.ip_address(client_ip)
    except ValueError:
        logger.warning("Invalid client IP: %s", client_ip)
        return False

    for entry in allowed_list:
        try:
            if "/" in entry:
                network = ipaddress.ip_network(entry, strict=False)
                if addr in network:
                    return True
            else:
                if addr == ipaddress.ip_address(entry):
                    return True
        except ValueError:
            logger.warning("Invalid IP whitelist entry: %s", entry)
            continue

    return False


def get_allowed_ips() -> List[str]:
    """Get the current IP whitelist from settings."""
    settings = get_web_settings()
    return parse_ip_list(settings.allowed_ips)
