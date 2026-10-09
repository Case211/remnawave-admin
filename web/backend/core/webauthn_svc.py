"""Passkeys / WebAuthn — церемонии регистрации и входа (py_webauthn 3.x).

RP ID / origin берутся из настроек webauthn_rp_id / webauthn_origin, а если они
пусты — из запроса (за trust-proxy — X-Forwarded-Host/Proto).
Challenge между begin/finish хранится в подписанном коротком JWT (stateless).
credential_id / public_key в БД — base64url.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from jose import jwt, JWTError
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (
    PublicKeyCredentialDescriptor,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from shared.db_schema import WEBAUTHN_CREDENTIALS_TABLE as TBL
from web.backend.core.errors import E

logger = logging.getLogger(__name__)

_RP_NAME = "Remnawave Admin"


class WebAuthnError(Exception):
    """Ошибка WebAuthn: код для фронта и человекочитаемое сообщение.

    Код свой у каждой причины: под общим FORBIDDEN фронт показывал «Доступ
    запрещён», и понять, что не сошёлся origin или истёк challenge, было
    нельзя без DevTools.
    """

    def __init__(self, code: E, message: str):
        super().__init__(message)
        self.code = code


# ── RP / origin из запроса ───────────────────────────────────────

def _rp_origin(request) -> tuple:
    from shared.config_service import config_service
    cfg_rp = str(config_service.get("webauthn_rp_id", "") or "").strip()
    cfg_origin = str(config_service.get("webauthn_origin", "") or "").strip()
    host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
    proto = (request.headers.get("x-forwarded-proto") or (request.url.scheme if request.url else "https")).split(",")[0].strip()
    rp_id = cfg_rp or host.split(":")[0]
    origin = cfg_origin or (f"{proto}://{host}" if host else "")
    if not rp_id or not origin:
        raise WebAuthnError(E.PASSKEY_DOMAIN_UNKNOWN, "не удалось определить домен для passkey")
    return rp_id, origin


# ── Challenge-token (подписанный, 5 мин) ─────────────────────────

def _make_token(purpose: str, challenge: bytes, extra: Optional[Dict[str, Any]] = None) -> str:
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "type": purpose, "chal": bytes_to_base64url(challenge),
        "iat": int(now.timestamp()), "exp": int((now + timedelta(minutes=5)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def _read_token(token: str, purpose: str) -> Dict[str, Any]:
    from web.backend.core.config import get_web_settings
    settings = get_web_settings()
    try:
        p = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    except JWTError:
        raise WebAuthnError(E.PASSKEY_CHALLENGE_EXPIRED, "challenge истёк или недействителен — начни заново")
    if p.get("type") != purpose:
        raise WebAuthnError(E.PASSKEY_CHALLENGE_EXPIRED, "неверный тип challenge")
    return p


# ── БД credentials ───────────────────────────────────────────────

def _row(r) -> Dict[str, Any]:
    d = dict(r)
    for k in ("created_at", "last_used_at"):
        if d.get(k) is not None:
            d[k] = d[k].isoformat()
    return d


async def list_credentials(account_id: int) -> List[Dict[str, Any]]:
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT * FROM {TBL} WHERE account_id = $1 ORDER BY created_at", account_id)
    return [_row(r) for r in rows]


async def get_credential(credential_id: str) -> Optional[Dict[str, Any]]:
    from shared.database import db_service
    if not db_service.is_connected:
        return None
    async with db_service.acquire() as conn:
        r = await conn.fetchrow(f"SELECT * FROM {TBL} WHERE credential_id = $1", credential_id)
    return _row(r) if r else None


async def _save_credential(account_id: int, credential_id: str, public_key: str,
                           sign_count: int, transports: Optional[str], name: Optional[str]) -> None:
    from shared.database import db_service
    if not db_service.is_connected:
        raise WebAuthnError(E.DB_UNAVAILABLE, "База данных недоступна")
    async with db_service.acquire() as conn:
        await conn.execute(
            f"""INSERT INTO {TBL} (account_id, credential_id, public_key, sign_count, transports, name)
                VALUES ($1, $2, $3, $4, $5, $6)""",
            account_id, credential_id, public_key, sign_count, transports, name)


async def _update_sign_count(cred_id: int, sign_count: int) -> None:
    from shared.database import db_service
    if not db_service.is_connected:
        return
    async with db_service.acquire() as conn:
        await conn.execute(
            f"UPDATE {TBL} SET sign_count = $1, last_used_at = NOW() WHERE id = $2", sign_count, cred_id)


async def delete_credential(cred_id: int, account_id: int) -> bool:
    from shared.database import db_service
    if not db_service.is_connected:
        return False
    async with db_service.acquire() as conn:
        res = await conn.execute(f"DELETE FROM {TBL} WHERE id = $1 AND account_id = $2", cred_id, account_id)
    return isinstance(res, str) and res.endswith("1")


# ── Регистрация ──────────────────────────────────────────────────

async def begin_registration(request, account: Dict[str, Any]) -> Dict[str, str]:
    rp_id, _ = _rp_origin(request)
    exclude = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
               for c in await list_credentials(account["id"])]
    uname = account.get("username") or (str(account.get("telegram_id")) if account.get("telegram_id") else f"admin{account['id']}")
    opts = generate_registration_options(
        rp_id=rp_id, rp_name=_RP_NAME,
        user_id=str(account["id"]).encode(), user_name=uname, user_display_name=uname,
        exclude_credentials=exclude or None,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED),
    )
    token = _make_token("wa_reg", opts.challenge, {"aid": account["id"]})
    return {"options": options_to_json(opts), "token": token}


async def finish_registration(request, token: str, credential: Any, name: Optional[str]) -> Dict[str, Any]:
    rp_id, origin = _rp_origin(request)
    p = _read_token(token, "wa_reg")
    aid = int(p["aid"])
    try:
        v = verify_registration_response(
            credential=credential, expected_challenge=base64url_to_bytes(p["chal"]),
            expected_rp_id=rp_id, expected_origin=origin, require_user_verification=False)
    except Exception as e:  # noqa: BLE001
        # Текст библиотеки и есть диагноз: «Unexpected client data origin …»
        raise WebAuthnError(E.PASSKEY_VERIFICATION_FAILED, str(e))
    transports = None
    if isinstance(credential, dict):
        tr = (credential.get("response") or {}).get("transports")
        if isinstance(tr, list):
            transports = ",".join(tr)
    await _save_credential(aid, bytes_to_base64url(v.credential_id),
                           bytes_to_base64url(v.credential_public_key),
                           v.sign_count, transports, (name or "").strip()[:60] or None)
    return {"credential_id": bytes_to_base64url(v.credential_id)}


# ── Вход ─────────────────────────────────────────────────────────

async def begin_authentication(request, username: Optional[str] = None) -> Dict[str, str]:
    rp_id, _ = _rp_origin(request)
    allow: List[PublicKeyCredentialDescriptor] = []
    if username:
        from web.backend.core.admin_accounts import get_admin_account_by_username
        acc = await get_admin_account_by_username(username.strip())
        if acc:
            allow = [PublicKeyCredentialDescriptor(id=base64url_to_bytes(c["credential_id"]))
                     for c in await list_credentials(acc["id"])]
    opts = generate_authentication_options(
        rp_id=rp_id, allow_credentials=allow or None,
        user_verification=UserVerificationRequirement.PREFERRED)
    token = _make_token("wa_auth", opts.challenge)
    return {"options": options_to_json(opts), "token": token}


async def finish_authentication(request, token: str, credential: Any) -> Dict[str, Any]:
    rp_id, origin = _rp_origin(request)
    p = _read_token(token, "wa_auth")
    cid = credential.get("id") or credential.get("rawId") if isinstance(credential, dict) else None
    if not cid:
        raise WebAuthnError(E.PASSKEY_NOT_FOUND, "нет id credential")
    stored = await get_credential(cid)
    if not stored:
        raise WebAuthnError(E.PASSKEY_NOT_FOUND, "passkey не найден — зарегистрируй его в настройках")
    try:
        v = verify_authentication_response(
            credential=credential, expected_challenge=base64url_to_bytes(p["chal"]),
            expected_rp_id=rp_id, expected_origin=origin,
            credential_public_key=base64url_to_bytes(stored["public_key"]),
            credential_current_sign_count=int(stored["sign_count"]),
            require_user_verification=False)
    except Exception as e:  # noqa: BLE001
        raise WebAuthnError(E.PASSKEY_VERIFICATION_FAILED, str(e))
    await _update_sign_count(int(stored["id"]), v.new_sign_count)
    from web.backend.core.admin_accounts import get_admin_account_by_id
    acc = await get_admin_account_by_id(int(stored["account_id"]))
    if not acc:
        raise WebAuthnError(E.ADMIN_NOT_FOUND, "аккаунт не найден")
    return acc
