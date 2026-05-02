"""FCM push delivery for the mobile admin app.

Тонкая обёртка над firebase-admin: в проде поднимается лениво при первом
обращении (init_firebase), потому что не у каждой инсталляции есть mobile —
нет смысла грузить SDK, если FCM_ENABLED=false. Если credentials не отдали
или firebase-admin не установлен — фасад просто молча no-op'ит, чтобы не
ронять hot-path notification_service.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


_app = None
_init_lock = asyncio.Lock()
_init_attempted = False


def _is_enabled() -> bool:
    try:
        from web.backend.core.config import get_web_settings
        s = get_web_settings()
        return bool(s.fcm_enabled and s.fcm_credentials_path)
    except Exception:
        return False


async def _ensure_app():
    """Lazy-init firebase_admin.App. Безопасно дёргать многократно."""
    global _app, _init_attempted
    if _app is not None:
        return _app
    if _init_attempted:
        return _app  # уже пробовали и не получилось — молча no-op
    async with _init_lock:
        if _app is not None or _init_attempted:
            return _app
        _init_attempted = True
        if not _is_enabled():
            logger.info("FCM disabled (FCM_ENABLED=false or credentials missing)")
            return None
        try:
            import firebase_admin
            from firebase_admin import credentials

            from web.backend.core.config import get_web_settings
            cred_path = get_web_settings().fcm_credentials_path
            cred = credentials.Certificate(cred_path)
            _app = firebase_admin.initialize_app(cred, name="remnawave-admin")
            logger.info("Firebase Admin SDK initialized")
        except Exception as e:
            logger.error("Failed to init firebase-admin: %s", e)
            _app = None
        return _app


def _category_for_type(notification_type: Optional[str]) -> str:
    """Маппинг {`violation`, `alert`, `escalation`, остальное} → канонические
    категории `violations`/`alerts`/`info`. Совпадает со списком в `me_devices`."""
    if notification_type == "violation":
        return "violations"
    if notification_type in ("alert", "escalation"):
        return "alerts"
    return "info"


def _device_accepts(category: str, enabled: bool, subscriptions) -> bool:
    """True если устройство хочет получать пуш этой категории."""
    if not enabled:
        return False
    # null/None — клиент не настраивал → шлём всё
    if subscriptions is None:
        return True
    # Пустой список — клиент явно отписался от всего
    if isinstance(subscriptions, str):
        try:
            import json
            subscriptions = json.loads(subscriptions)
        except Exception:
            return True  # Битые данные — лучше пропустить, чем потерять алерт
    if not isinstance(subscriptions, list):
        return True
    return category in subscriptions


async def _list_devices_for_admin(admin_id: int) -> List[dict]:
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT fcm_token, notifications_enabled, subscriptions "
            "FROM admin_devices WHERE admin_id = $1",
            admin_id,
        )
    return [dict(r) for r in rows]


async def _list_devices_for_all_admins() -> List[dict]:
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            "SELECT fcm_token, admin_id, notifications_enabled, subscriptions FROM admin_devices",
        )
    return [dict(r) for r in rows]


async def _delete_token(token: str) -> None:
    from shared.database import db_service
    if not db_service.is_connected:
        return
    async with db_service.acquire() as conn:
        await conn.execute(
            "DELETE FROM admin_devices WHERE fcm_token = $1", token,
        )


async def _send_via_fcm(
    tokens: Sequence[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None,
) -> Dict[str, int]:
    """Отправка списку токенов. Невалидные токены чистим автоматически."""
    if not tokens:
        return {"sent": 0, "failed": 0}
    app = await _ensure_app()
    if app is None:
        return {"sent": 0, "failed": 0}

    from firebase_admin import messaging

    sent = 0
    failed = 0
    invalid_tokens: List[str] = []

    # Все строки в data; FCM требует строковые поля
    payload_data: Dict[str, str] = {k: str(v) for k, v in (data or {}).items()}

    def _send_sync(token: str) -> bool:
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=payload_data,
                token=token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        # Используем default channel; на стороне клиента создадим
                        # канал с тем же id для приоритета IMPORTANCE_HIGH.
                        channel_id="remnawave_admin",
                        default_sound=True,
                    ),
                ),
            )
            messaging.send(message, app=app)
            return True
        except messaging.UnregisteredError:
            invalid_tokens.append(token)
            return False
        except Exception as e:
            err = str(e).lower()
            if "registration" in err or "invalid" in err or "not-found" in err:
                invalid_tokens.append(token)
            logger.warning("FCM send failed for %s...: %s", token[:12], e)
            return False

    loop = asyncio.get_event_loop()
    results = await asyncio.gather(
        *[loop.run_in_executor(None, _send_sync, t) for t in tokens],
        return_exceptions=False,
    )
    sent = sum(1 for r in results if r)
    failed = len(results) - sent

    if invalid_tokens:
        logger.info("FCM: cleaning %d invalid tokens", len(invalid_tokens))
        for t in invalid_tokens:
            await _delete_token(t)

    return {"sent": sent, "failed": failed}


# Public API ────────────────────────────────────────────────────────────────


async def send_to_admin(
    admin_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """Push конкретному админу на все его устройства, отфильтрованные по
    notifications_enabled и subscriptions (по категории из data['type'])."""
    if not _is_enabled():
        return {"sent": 0, "failed": 0}
    devices = await _list_devices_for_admin(admin_id)
    category = _category_for_type((data or {}).get("type"))
    tokens = [
        d["fcm_token"] for d in devices
        if _device_accepts(category, d["notifications_enabled"], d["subscriptions"])
    ]
    return await _send_via_fcm(tokens, title, body, data)


async def broadcast_to_admins(
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """Push всем устройствам всех админов с тем же фильтром по подпискам."""
    if not _is_enabled():
        return {"sent": 0, "failed": 0}
    devices = await _list_devices_for_all_admins()
    category = _category_for_type((data or {}).get("type"))
    tokens = [
        d["fcm_token"] for d in devices
        if _device_accepts(category, d["notifications_enabled"], d["subscriptions"])
    ]
    return await _send_via_fcm(tokens, title, body, data)


def is_enabled() -> bool:
    """Внешним вызывающим — для гейта над регистрацией токенов."""
    return _is_enabled()
