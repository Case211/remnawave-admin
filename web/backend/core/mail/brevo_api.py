"""Brevo (ex-Sendinblue) — исходящая почта через HTTP API v3 вместо SMTP.

Для тех, у кого хостер режет 25/587: письмо уходит по HTTPS, DKIM-подпись и
доставка до MX получателя — на стороне Brevo. Домен отправителя должен быть
подтверждён в аккаунте Brevo (Senders & IP → Domains), иначе API отвечает
ошибкой, и она видна в очереди как причина неотправки.
"""
import base64
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
_TIMEOUT = 30.0


class BrevoError(RuntimeError):
    """Ошибка API Brevo с текстом, пригодным для очереди писем."""


def build_payload(
    *,
    from_email: str,
    to_email: str,
    subject: str,
    from_name: Optional[str] = None,
    body_text: str = "",
    body_html: Optional[str] = None,
    headers: Optional[Dict[str, Any]] = None,
    attachments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Тело запроса POST /v3/smtp/email."""
    sender: Dict[str, str] = {"email": from_email}
    if from_name:
        sender["name"] = from_name
    payload: Dict[str, Any] = {
        "sender": sender,
        "to": [{"email": to_email}],
        "subject": subject or "(без темы)",
    }
    if body_html:
        payload["htmlContent"] = body_html
    if body_text:
        payload["textContent"] = body_text
    elif not body_html:
        # Brevo требует хотя бы один контент и отвергает пустую строку.
        payload["textContent"] = " "
    clean_headers = {str(k): str(v) for k, v in (headers or {}).items() if v}
    if clean_headers:
        payload["headers"] = clean_headers
    files = [
        {"name": att.get("filename") or "attachment",
         "content": base64.b64encode(att["content"]).decode()}
        for att in (attachments or []) if att.get("content")
    ]
    if files:
        payload["attachment"] = files
    return payload


async def send_email(api_key: str, payload: Dict[str, Any], timeout: float = _TIMEOUT) -> str:
    """Отправить письмо; вернуть строку для поля smtp_response очереди."""
    headers = {"api-key": api_key, "accept": "application/json", "content-type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(BREVO_URL, json=payload, headers=headers)
    except httpx.HTTPError as e:
        raise BrevoError(f"Brevo: сеть/HTTP: {e}")

    if resp.status_code not in (200, 201, 202):
        try:
            data = resp.json()
            detail = (data.get("message") or data.get("code") or "") if isinstance(data, dict) else ""
        except ValueError:
            detail = resp.text[:200]
        raise BrevoError(f"Brevo HTTP {resp.status_code}: {detail}".rstrip(": "))

    try:
        data = resp.json()
        message_id = data.get("messageId") if isinstance(data, dict) else None
    except ValueError:
        message_id = None
    return f"brevo accepted messageId={message_id}" if message_id else "brevo accepted"
