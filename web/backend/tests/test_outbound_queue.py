"""Tests for OutboundMailQueue: noreply handling and hourly rate limiting."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from web.backend.core.mail.outbound_queue import OutboundMailQueue


def _row(from_email: str, body_html: str | None = None) -> dict:
    return {
        "subject": "Test",
        "from_email": from_email,
        "from_name": None,
        "to_email": "user@example.com",
        "domain": "stijoin.com",
        "body_text": "Hello",
        "body_html": body_html,
    }


def test_noreply_mail_marked_and_gets_notice():
    msg = OutboundMailQueue()._build_message(_row("noreply@stijoin.com"))

    assert msg["Auto-Submitted"] == "auto-generated"
    assert msg["X-Auto-Response-Suppress"] == "All"
    body = msg.get_content()
    assert "ответы не доходят" in body
    assert "do not reply" in body


def test_noreply_notice_inserted_before_body_close():
    html = "<html><body><p>Hi</p></body></html>"
    msg = OutboundMailQueue()._build_message(_row("noreply@stijoin.com", body_html=html))

    html_part = msg.get_body(preferencelist=("html",)).get_content()
    assert "ответы не доходят" in html_part
    # Notice must sit inside the body, before the closing tag.
    assert html_part.index("ответы не доходят") < html_part.rindex("</body>")


def test_relayed_user_mail_is_untouched():
    """Mail relayed from a real user mailbox must not be marked or annotated."""
    msg = OutboundMailQueue()._build_message(_row("ceo@stijoin.com"))

    assert msg["Auto-Submitted"] is None
    assert msg["X-Auto-Response-Suppress"] is None
    assert "do not reply" not in msg.get_content()


# ── effective hourly limit (domain override vs global default) ──────

def _cfg(global_limit):
    cfg = MagicMock()
    cfg.get.return_value = global_limit
    return cfg


def test_effective_limit_uses_domain_override():
    """A positive per-domain value wins over the global setting."""
    q = OutboundMailQueue()
    with patch("shared.config_service.config_service", _cfg(1000)):
        assert q._effective_hourly_limit(500) == 500


def test_effective_limit_inherits_global_when_zero_or_null():
    q = OutboundMailQueue()
    with patch("shared.config_service.config_service", _cfg(1000)):
        assert q._effective_hourly_limit(0) == 1000
        assert q._effective_hourly_limit(None) == 1000


def test_effective_limit_unlimited_when_global_zero():
    q = OutboundMailQueue()
    with patch("shared.config_service.config_service", _cfg(0)):
        assert q._effective_hourly_limit(0) == 0  # <= 0 ⇒ unlimited upstream


# ── _check_rate_limit ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_check_rate_limit_blocks_at_global_cap():
    """Domain inherits global (row=0); already at the cap ⇒ blocked."""
    q = OutboundMailQueue()
    conn = AsyncMock()
    conn.fetchrow.return_value = {"max_send_per_hour": 0}
    conn.fetchval.return_value = 1000  # sent in last hour
    with patch("shared.config_service.config_service", _cfg(1000)):
        assert await q._check_rate_limit(conn, 3) is False


@pytest.mark.asyncio
async def test_check_rate_limit_allows_under_global_cap():
    q = OutboundMailQueue()
    conn = AsyncMock()
    conn.fetchrow.return_value = {"max_send_per_hour": 0}
    conn.fetchval.return_value = 50
    with patch("shared.config_service.config_service", _cfg(1000)):
        assert await q._check_rate_limit(conn, 3) is True


@pytest.mark.asyncio
async def test_check_rate_limit_unlimited_skips_count():
    """When effective limit is unlimited we never even count the queue."""
    q = OutboundMailQueue()
    conn = AsyncMock()
    conn.fetchrow.return_value = {"max_send_per_hour": 0}
    with patch("shared.config_service.config_service", _cfg(0)):
        assert await q._check_rate_limit(conn, 3) is True
    conn.fetchval.assert_not_called()


# ── Доставка через Brevo ────────────────────────────────────────

def _db_mock():
    conn = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    db = MagicMock()
    db.acquire = MagicMock(return_value=cm)
    return db, conn


def test_delivery_mode_defaults_to_direct():
    from web.backend.core.mail import outbound_queue as oq

    cfg = MagicMock()
    cfg.get.return_value = None
    with patch("shared.config_service.config_service", cfg):
        assert oq._delivery_mode() == "direct"
    cfg.get.return_value = " Brevo "
    with patch("shared.config_service.config_service", cfg):
        assert oq._delivery_mode() == "brevo"


@pytest.mark.asyncio
async def test_send_one_via_brevo_skips_mx_and_smtp():
    """В режиме brevo письмо уходит в API; MX и SMTP не трогаются, статус — sent."""
    q = OutboundMailQueue()
    db, conn = _db_mock()
    row = {**_row("noreply@stijoin.com", body_html="<p>Hi</p>"),
           "id": 7, "attempts": 0, "max_attempts": 5}
    settings = {"mailserver_delivery_mode": "brevo", "mailserver_brevo_api_key": "xkeysib-1"}
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: settings.get(key, default)

    with patch("shared.database.db_service", db), \
         patch("shared.config_service.config_service", cfg), \
         patch.object(q, "_load_attachments", AsyncMock(return_value=[])), \
         patch.object(q, "_resolve_mx", AsyncMock(side_effect=AssertionError("MX must not be resolved"))), \
         patch("web.backend.core.mail.brevo_api.send_email",
               AsyncMock(return_value="brevo accepted messageId=42")) as send:
        await q._send_one(row)

    api_key, payload = send.call_args.args
    assert api_key == "xkeysib-1"
    assert payload["sender"] == {"email": "noreply@stijoin.com"}
    assert payload["to"] == [{"email": "user@example.com"}]
    assert "<p>Hi</p>" in payload["htmlContent"]
    assert "ответы не доходят" in payload["textContent"]
    assert "status = 'sent'" in conn.execute.call_args.args[0]


@pytest.mark.asyncio
async def test_send_one_via_brevo_without_key_fails_gracefully():
    """Нет ключа — письмо помечается failed с понятной причиной, а не падает исключением."""
    q = OutboundMailQueue()
    db, conn = _db_mock()
    row = {**_row("noreply@stijoin.com"), "id": 8, "attempts": 0, "max_attempts": 5}
    cfg = MagicMock()
    cfg.get.side_effect = lambda key, default=None: {"mailserver_delivery_mode": "brevo"}.get(key, default)

    with patch("shared.database.db_service", db), \
         patch("shared.config_service.config_service", cfg), \
         patch.object(q, "_load_attachments", AsyncMock(return_value=[])):
        await q._send_one(row)

    args = conn.execute.call_args.args
    assert "status = $1" in args[0] and args[1] == "failed"
    assert "Brevo" in args[2]
