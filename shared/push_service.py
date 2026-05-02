"""FCM push delivery — общий для бота и web-backend.

Лежит в shared/, потому что:
- web-backend дёргает из notification_service для violations/alerts/automation
- бот дёргает из src/utils/notifications.py для node/user/hwid/service-событий,
  которые приходят через Panel webhook напрямую в бот (мимо notification_service)

Конфиг читаем из переменных окружения, чтобы не таскать сюда web/bot pydantic
settings — модуль остаётся независимым и подключается одним импортом.

`firebase-admin` лениво — если пакета нет или FCM_ENABLED=false, всё no-op'ит
тихо. Хост-процесс не падает из-за отсутствия зависимости.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)


_app = None
_init_lock = asyncio.Lock()
_init_attempted = False


def _is_enabled() -> bool:
    return (
        os.getenv("FCM_ENABLED", "").strip().lower() in ("1", "true", "yes", "on")
        and bool(os.getenv("FCM_CREDENTIALS_PATH"))
    )


def _credentials_path() -> Optional[str]:
    p = os.getenv("FCM_CREDENTIALS_PATH")
    return p.strip() if p else None


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

            cred_path = _credentials_path()
            cred = credentials.Certificate(cred_path)
            # Уникальное имя app — иначе при попытке инициализировать второй раз
            # (бот + web-backend в одном процессе при тестах) firebase-admin падает.
            # В продкоде они в разных процессах, но защититься дешёво.
            app_name = "remnawave-admin"
            try:
                _app = firebase_admin.get_app(name=app_name)
            except ValueError:
                _app = firebase_admin.initialize_app(cred, name=app_name)
            logger.info("Firebase Admin SDK initialized")
        except Exception as e:
            logger.error("Failed to init firebase-admin: %s", e)
            _app = None
        return _app


def _category_for_type(notification_type: Optional[str]) -> str:
    """Fallback маппинг по data['type'] для случаев, когда event_id не указан
    (в legacy-вызовах из notification_service до добавления event)."""
    if notification_type == "violation":
        return "violations"
    if notification_type in ("alert", "escalation"):
        return "alerts"
    return "info"


def _resolve_category(event_id: Optional[str], notification_type: Optional[str]) -> str:
    """Сначала пытаемся найти категорию по event_id в каталоге; если не нашли —
    деривируем из data.type. Это даёт обратную совместимость со старыми вызовами
    и приоритет более точному `event` для новых."""
    if event_id:
        try:
            from shared.notification_events import category_for_event
            return category_for_event(event_id)
        except Exception:
            pass
    return _category_for_type(notification_type)


def _decode_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            import json
            value = json.loads(value)
        except Exception:
            return []
    return list(value) if isinstance(value, list) else []


def _device_accepts(
    category: str,
    event_id: Optional[str],
    enabled: bool,
    subscriptions,
    disabled_categories,
    disabled_events,
) -> bool:
    """True если устройство хочет получать пуш этой категории/события.

    Логика, в порядке проверки:
      1. notifications_enabled=false → False
      2. event_id в disabled_events → False (точечный отказ от конкретного события)
      3. category в disabled_categories → False (отказ от группы целиком)
      4. legacy whitelist `subscriptions` (массив) — если задан и непуст,
         категория должна быть в нём; пустой = «отписан от всего».
      5. иначе → True
    """
    if not enabled:
        return False
    de = _decode_list(disabled_events)
    if event_id and event_id in de:
        return False
    dc = _decode_list(disabled_categories)
    if category in dc:
        return False
    # Legacy формат: subscriptions = массив-whitelist (только эти категории)
    if subscriptions is not None:
        subs = _decode_list(subscriptions)
        if subs:
            return category in subs
        # Пустой whitelist = клиент явно отписался от всего (старый клиент)
        # — но если он же выставит явно disabled_categories=[]/disabled_events=[],
        # ниже мы уже не отказали, значит здесь возвращаем False только если
        # subscriptions реально передавался как пустой явный whitelist.
        return False
    return True


_DEVICE_FIELDS = (
    "fcm_token, notifications_enabled, subscriptions, "
    "disabled_categories, disabled_events"
)


async def _list_devices_for_admin(admin_id: int) -> List[dict]:
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {_DEVICE_FIELDS} FROM admin_devices WHERE admin_id = $1",
            admin_id,
        )
    return [dict(r) for r in rows]


async def _list_devices_for_all_admins() -> List[dict]:
    from shared.database import db_service
    if not db_service.is_connected:
        return []
    async with db_service.acquire() as conn:
        rows = await conn.fetch(
            f"SELECT {_DEVICE_FIELDS}, admin_id FROM admin_devices",
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


def _filter_tokens(devices: list, data: Optional[Dict[str, Any]]) -> List[str]:
    payload = data or {}
    event_id = payload.get("event")
    notification_type = payload.get("type")
    category = _resolve_category(event_id, notification_type)
    return [
        d["fcm_token"] for d in devices
        if _device_accepts(
            category=category,
            event_id=event_id,
            enabled=d["notifications_enabled"],
            subscriptions=d["subscriptions"],
            disabled_categories=d.get("disabled_categories"),
            disabled_events=d.get("disabled_events"),
        )
    ]


async def send_to_admin(
    admin_id: int,
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """Push конкретному админу. Фильтр: notifications_enabled, точечный
    disabled_events, disabled_categories, плюс legacy `subscriptions` whitelist."""
    if not _is_enabled():
        return {"sent": 0, "failed": 0}
    devices = await _list_devices_for_admin(admin_id)
    return await _send_via_fcm(_filter_tokens(devices, data), title, body, data)


async def broadcast_to_admins(
    title: str,
    body: str,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, int]:
    """Push всем устройствам всех админов с тем же фильтром."""
    if not _is_enabled():
        return {"sent": 0, "failed": 0}
    devices = await _list_devices_for_all_admins()
    return await _send_via_fcm(_filter_tokens(devices, data), title, body, data)


def is_enabled() -> bool:
    """Внешним вызывающим — для гейта над регистрацией токенов."""
    return _is_enabled()
