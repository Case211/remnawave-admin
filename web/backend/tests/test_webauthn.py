"""Тесты WebAuthn-сервиса: challenge-token, rp/origin, генерация опций."""
import json
from types import SimpleNamespace

import pytest
from webauthn.helpers import base64url_to_bytes

from web.backend.core import webauthn_svc as wa
from web.backend.core.errors import E


def _req(host="admin.example.com", proto="https"):
    return SimpleNamespace(headers={"host": host, "x-forwarded-proto": proto},
                           url=SimpleNamespace(scheme=proto))


class TestChallengeToken:
    def test_roundtrip(self):
        tok = wa._make_token("wa_reg", b"\x01\x02\x03challenge-bytes-01", {"aid": 7})
        p = wa._read_token(tok, "wa_reg")
        assert p["aid"] == 7
        assert base64url_to_bytes(p["chal"]) == b"\x01\x02\x03challenge-bytes-01"

    def test_wrong_purpose(self):
        tok = wa._make_token("wa_reg", b"abcdefghij0123456789", {})
        with pytest.raises(wa.WebAuthnError) as exc:
            wa._read_token(tok, "wa_auth")
        assert exc.value.code == E.PASSKEY_CHALLENGE_EXPIRED

    def test_garbage_token_is_expired_challenge(self):
        with pytest.raises(wa.WebAuthnError) as exc:
            wa._read_token("not-a-jwt", "wa_reg")
        assert exc.value.code == E.PASSKEY_CHALLENGE_EXPIRED


class TestRpOrigin:
    def test_forwarded_host_port(self):
        rp, origin = wa._rp_origin(_req("panel.foo.com:443", "https"))
        assert rp == "panel.foo.com" and origin == "https://panel.foo.com:443"

    def test_settings_override_request(self, monkeypatch):
        """Прокси без X-Forwarded-Proto: адрес панели задаётся в настройках (#297)."""
        from shared.config_service import config_service
        values = {"webauthn_rp_id": "panel.foo.com", "webauthn_origin": "https://panel.foo.com"}
        monkeypatch.setattr(config_service, "get", lambda key, default=None: values.get(key, default))
        assert wa._rp_origin(_req("10.0.0.5:8080", "http")) == ("panel.foo.com", "https://panel.foo.com")

    def test_settings_are_registered(self):
        """Код читал эти ключи, а задать их было негде: PUT /settings отвечал 404."""
        from shared.config_service import DEFAULT_CONFIG_DEFINITIONS
        defs = {d["key"]: d for d in DEFAULT_CONFIG_DEFINITIONS}
        for key in ("webauthn_rp_id", "webauthn_origin"):
            assert defs[key]["category"] == "security"
            assert defs[key]["default_value"] == ""


class TestBeginRegistration:
    @pytest.mark.asyncio
    async def test_produces_options(self):
        out = await wa.begin_registration(_req(), {"id": 5, "username": "admin"})
        assert "options" in out and "token" in out
        opts = json.loads(out["options"])
        assert opts["rp"]["id"] == "admin.example.com"
        assert opts["user"]["name"] == "admin"
        assert wa._read_token(out["token"], "wa_reg")["aid"] == 5


class TestErrorCodes:
    @pytest.mark.asyncio
    async def test_failed_verification_keeps_library_reason(self):
        """Причина отказа доходит до админа, а не тонет в «Доступ запрещён»."""
        out = await wa.begin_registration(_req(), {"id": 5, "username": "admin"})
        credential = {"id": "eA", "rawId": "eA", "type": "public-key", "response": {}}
        with pytest.raises(wa.WebAuthnError) as exc:
            await wa.finish_registration(_req(), out["token"], credential, None)
        assert exc.value.code == E.PASSKEY_VERIFICATION_FAILED
        assert str(exc.value)

    @pytest.mark.asyncio
    async def test_api_answers_with_passkey_code(self, client):
        resp = await client.post("/api/v2/auth/webauthn/register/finish",
                                 json={"token": "not-a-jwt", "credential": {}})
        assert resp.status_code == 400
        assert resp.json()["detail"]["code"] == "PASSKEY_CHALLENGE_EXPIRED"
