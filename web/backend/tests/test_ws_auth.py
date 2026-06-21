"""Tests for WebSocket handshake authentication (extract_ws_token)."""
import pytest

from web.backend.api.deps import extract_ws_token, WS_AUTH_SUBPROTOCOL


class FakeWebSocket:
    """Minimal stand-in: extract_ws_token uses headers/cookies/query_params."""

    def __init__(self, headers=None, query_params=None, cookies=None):
        self.headers = headers or {}
        self.query_params = query_params or {}
        self.cookies = cookies or {}


class TestExtractWsToken:
    def test_subprotocol_token(self):
        """Токен из Sec-WebSocket-Protocol — основной механизм."""
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, my.jwt.token"}
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "my.jwt.token"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_subprotocol_whitespace_tolerant(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": " access-token ,  my.jwt.token "}
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "my.jwt.token"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_query_fallback(self):
        """Старые клиенты с ?token= продолжают работать (deprecated)."""
        ws = FakeWebSocket(query_params={"token": "legacy.jwt"})
        token, subprotocol = extract_ws_token(ws)
        assert token == "legacy.jwt"
        assert subprotocol is None

    def test_subprotocol_wins_over_query(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, header.jwt"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "header.jwt"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_foreign_subprotocol_falls_back_to_query(self):
        """Чужой subprotocol (не access-token) не трактуется как токен."""
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "graphql-ws"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "query.jwt"
        assert subprotocol is None

    def test_marker_without_token_falls_back(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "query.jwt"
        assert subprotocol is None

    def test_empty_token_part_falls_back(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, "},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token is None
        assert subprotocol is None

    def test_no_auth_at_all(self):
        token, subprotocol = extract_ws_token(FakeWebSocket())
        assert token is None
        assert subprotocol is None

    def test_cookie_source(self):
        """HttpOnly cookie rw_access — источник для cookie-аутентификации."""
        ws = FakeWebSocket(cookies={"rw_access": "cookie.jwt"})
        token, subprotocol = extract_ws_token(ws)
        assert token == "cookie.jwt"
        assert subprotocol is None

    def test_subprotocol_wins_over_cookie(self):
        ws = FakeWebSocket(
            headers={"sec-websocket-protocol": "access-token, header.jwt"},
            cookies={"rw_access": "cookie.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "header.jwt"
        assert subprotocol == WS_AUTH_SUBPROTOCOL

    def test_cookie_wins_over_query(self):
        ws = FakeWebSocket(
            cookies={"rw_access": "cookie.jwt"},
            query_params={"token": "query.jwt"},
        )
        token, subprotocol = extract_ws_token(ws)
        assert token == "cookie.jwt"
        assert subprotocol is None
