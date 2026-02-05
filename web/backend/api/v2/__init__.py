"""API v2 routers."""
from web.backend.api.v2 import auth, users, nodes, analytics, violations, hosts, websocket

__all__ = ["auth", "users", "nodes", "analytics", "violations", "hosts", "websocket"]
