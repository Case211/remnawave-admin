"""Tests for shared/http_client.py — BaseHttpClient transport layer.

Covers v3.0.0 empty-body responses (204/202) and error mapping.
"""
import httpx
import pytest

from shared.exceptions import (
    NotFoundError,
    RateLimitError,
    ServerError,
    UnauthorizedError,
    ValidationError,
)
from shared.http_client import BaseHttpClient


def _make_client(responses):
    class _Client(BaseHttpClient):
        def _create_client(self):
            transport = httpx.MockTransport(lambda request: responses.pop(0))
            return httpx.AsyncClient(
                base_url=self._base_url,
                headers=self._headers,
                timeout=httpx.Timeout(5.0),
                transport=transport,
            )

    return _Client("http://panel.test", "/api", {})


class TestEmptyBodyResponses:
    async def test_204_no_content_returns_empty_dict(self):
        client = _make_client([httpx.Response(204)])
        assert await client._get("/users/1") == {}

    async def test_204_delete_returns_empty_dict(self):
        client = _make_client([httpx.Response(204)])
        assert await client._delete("/users/1") == {}

    async def test_202_no_content_returns_empty_dict(self):
        client = _make_client([httpx.Response(202)])
        assert await client._post("/users/bulk/actions") == {}

    async def test_201_with_body_returns_parsed_json(self):
        client = _make_client([httpx.Response(201, json={"id": 7, "username": "alice"})])
        assert await client._post("/users", json={}) == {"id": 7, "username": "alice"}

    async def test_200_with_body_returns_parsed_json(self):
        client = _make_client([httpx.Response(200, json={"response": {"id": 1}})])
        assert await client._get("/users/1") == {"response": {"id": 1}}

    async def test_empty_body_does_not_raise_json_error(self):
        client = _make_client([httpx.Response(204)])
        result = await client._get("/hosts/abc")
        assert isinstance(result, dict)


class TestErrorMapping:
    async def test_404_raises_not_found(self):
        client = _make_client([httpx.Response(404, json={"message": "missing"})])
        with pytest.raises(NotFoundError):
            await client._get("/users/999")

    async def test_401_raises_unauthorized(self):
        client = _make_client([httpx.Response(401)])
        with pytest.raises(UnauthorizedError):
            await client._get("/users")

    async def test_400_raises_validation_error(self):
        client = _make_client([httpx.Response(400, json={"detail": "bad value"})])
        with pytest.raises(ValidationError) as exc_info:
            await client._post("/users", json={})
        assert "bad value" in str(exc_info.value)

    async def test_429_raises_rate_limit(self):
        client = _make_client([httpx.Response(429)])
        with pytest.raises(RateLimitError):
            await client._get("/users")

    async def test_500_with_message_raises_server_error(self):
        client = _make_client([httpx.Response(500, json={"message": "boom"})])
        with pytest.raises(ServerError) as exc_info:
            await client._get("/users")
        assert "boom" in str(exc_info.value)
