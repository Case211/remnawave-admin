"""Brevo: сборка запроса и обработка ответов API."""
import base64
from unittest.mock import patch

import httpx
import pytest

from web.backend.core.mail import brevo_api


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _patched_client(handler):
    def factory(**kw):
        kw.pop("transport", None)
        return _REAL_ASYNC_CLIENT(transport=httpx.MockTransport(handler), **kw)
    return factory


def test_payload_has_sender_content_headers_and_attachments():
    payload = brevo_api.build_payload(
        from_email="noreply@stijoin.com", from_name="STi Host", to_email="u@example.com",
        subject="Hi", body_text="text", body_html="<p>x</p>",
        headers={"In-Reply-To": "<a@b>", "References": None},
        attachments=[{"filename": "a.txt", "content": b"abc", "content_type": "text/plain"}],
    )
    assert payload["sender"] == {"email": "noreply@stijoin.com", "name": "STi Host"}
    assert payload["to"] == [{"email": "u@example.com"}]
    assert payload["textContent"] == "text" and payload["htmlContent"] == "<p>x</p>"
    assert payload["headers"] == {"In-Reply-To": "<a@b>"}
    assert payload["attachment"] == [{"name": "a.txt", "content": base64.b64encode(b"abc").decode()}]


def test_payload_never_sends_empty_body_or_subject():
    payload = brevo_api.build_payload(from_email="a@b.c", to_email="u@example.com", subject="", body_text="")
    assert payload["textContent"] == " "
    assert payload["subject"]
    assert "headers" not in payload and "attachment" not in payload


@pytest.mark.asyncio
async def test_send_email_returns_message_id():
    seen = {}

    def h(request: httpx.Request) -> httpx.Response:
        seen["key"] = request.headers.get("api-key")
        seen["url"] = str(request.url)
        return httpx.Response(201, json={"messageId": "<42@smtp-relay.mailin.fr>"})

    with patch("httpx.AsyncClient", _patched_client(h)):
        result = await brevo_api.send_email("xkeysib-1", {"sender": {"email": "a@b.c"}})
    assert seen == {"key": "xkeysib-1", "url": brevo_api.BREVO_URL}
    assert "42@smtp-relay.mailin.fr" in result


@pytest.mark.asyncio
async def test_send_email_raises_with_api_message():
    def h(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"code": "unauthorized", "message": "Key not found"})

    with patch("httpx.AsyncClient", _patched_client(h)):
        with pytest.raises(brevo_api.BrevoError) as exc:
            await brevo_api.send_email("bad", {})
    assert "401" in str(exc.value) and "Key not found" in str(exc.value)
