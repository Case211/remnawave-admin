"""Webhook сервер для приема уведомлений об изменении подписки от панели Remnawave."""
import hmac
import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from aiogram import Bot

from src.config import get_settings
from src.handlers.state import BOT_CREATING_USERS
from shared.api_client import api_client, NotFoundError
from shared.sync import sync_service
from shared.logger import logger
from src.utils.notifications import (
    send_user_notification,
    send_node_notification,
    send_service_notification,
    send_hwid_notification,
    send_error_notification,
    send_crm_notification,
    send_generic_notification,
)
app = FastAPI(title="Remnawave Admin Webhook")

# One-time warning about missing webhook secret
_settings = get_settings()
if not _settings.webhook_secret:
    logger.warning(
        "WEBHOOK_SECRET is not set. Webhook will only accept requests from localhost (127.0.0.1, ::1). "
        "Set WEBHOOK_SECRET for production use."
    )


@app.middleware("http")
async def catch_invalid_requests(request: Request, call_next):
    """
    Middleware для обработки некорректных HTTP-запросов.
    Подавляет предупреждения от uvicorn для известных паттернов некорректных запросов.
    """
    try:
        # Проверяем, является ли запрос валидным HTTP-запросом
        if request.method not in ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]:
            # Некорректный метод - возвращаем 405 без логирования
            return JSONResponse(status_code=405, content={"error": "Method not allowed"})
        
        # Проверяем путь - если это не наш endpoint, возвращаем 404 без логирования
        if request.url.path not in ["/webhook", "/webhook/health", "/webhook/test", "/"]:
            # Для корневого пути возвращаем простой ответ
            if request.url.path == "/":
                return JSONResponse(status_code=200, content={"service": "remnawave-admin-webhook", "status": "ok"})
            # Для других путей - 404 без логирования
            return JSONResponse(status_code=404, content={"error": "Not found"})
        
        # Продолжаем обработку валидного запроса
        response = await call_next(request)
        return response
    except Exception:
        # Если произошла ошибка при обработке запроса, возвращаем 400 без логирования
        return JSONResponse(status_code=400, content={"error": "Bad request"})


_WEBHOOK_MAX_AGE_SEC = 300  # окно анти-replay для timestamp вебхука


def _webhook_timestamp_fresh(ts: Optional[str]) -> bool:
    """True если timestamp свежий (или отсутствует/нераспознан — не ломаем совместимость).

    Timestamp входит в подписанное тело, подменить его без инвалидации подписи
    нельзя — проверка свежести ограничивает окно повторного проигрывания (replay).
    """
    if not ts:
        return True  # timestamp опционален
    try:
        parsed = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return True  # нераспознанный формат — не отклоняем
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = (datetime.now(timezone.utc) - parsed).total_seconds()
    return -60 <= delta <= _WEBHOOK_MAX_AGE_SEC  # старый → replay; небольшой сдвиг в будущее допускаем


def verify_webhook_secret(request: Request, body: bytes) -> bool:
    """
    Проверяет подпись webhook из заголовка X-Remnawave-Signature.
    
    Панель Remnawave может использовать два метода:
    1. Простое сравнение строк (устаревший метод)
    2. HMAC-SHA256 подпись от тела запроса (рекомендуемый метод)
    
    Функция проверяет оба метода для совместимости.
    """
    settings = get_settings()
    if not settings.webhook_secret:
        # Если секрет не настроен, разрешаем только запросы с localhost
        client_host = request.client.host if request.client else None
        if client_host in ("127.0.0.1", "::1", "localhost"):
            logger.debug("WEBHOOK_SECRET not set, accepting request from localhost (%s)", client_host)
            return True
        logger.warning(
            "WEBHOOK_SECRET not set and request is from non-localhost address (%s), rejecting",
            client_host,
        )
        return False
    
    # Официальный заголовок от панели Remnawave
    # Проверяем разные варианты имени заголовка (FastAPI нормализует к нижнему регистру)
    signature = (
        request.headers.get("X-Remnawave-Signature") or
        request.headers.get("x-remnawave-signature") or
        request.headers.get("X-REMNAWAVE-SIGNATURE")
    )
    
    if not signature:
        # Заголовки логируем только при проблеме — на каждый успешный вебхук
        # они превращали docker-логи в простыню
        logger.error(
            "X-Remnawave-Signature header missing. Available headers: %s. "
            "Проверьте, что в панели Remnawave установлена переменная WEBHOOK_SECRET_HEADER",
            list(request.headers.keys())
        )
        return False

    # Метод 1: Простое сравнение строк (для обратной совместимости) — тайминг-безопасно
    if hmac.compare_digest(signature, settings.webhook_secret):
        return True
    
    # Метод 2: HMAC-SHA256 подпись от тела запроса
    try:
        # Вычисляем HMAC-SHA256 от тела запроса
        expected_signature = hmac.new(
            settings.webhook_secret.encode('utf-8'),
            body,
            hashlib.sha256
        ).hexdigest()
        
        # Сравниваем с полученной подписью (безопасное сравнение)
        is_valid = hmac.compare_digest(expected_signature, signature)
        
        if is_valid:
            return True
        else:
            logger.error(
                "Webhook signature mismatch (lengths: received=%d, expected=%d). "
                "Убедитесь, что WEBHOOK_SECRET в боте совпадает с WEBHOOK_SECRET_HEADER в панели Remnawave.",
                len(signature) if signature else 0,
                len(expected_signature) if expected_signature else 0,
            )
            return False
    except Exception as exc:
        logger.error("Error verifying HMAC signature: %s", exc)
        return False


@app.post("/webhook")
async def remnawave_webhook(request: Request):
    """
    Webhook endpoint для приема уведомлений от панели Remnawave.
    
    Официальный формат webhook от панели:
    {
        "event": "user.modified",  // тип события
        "data": {...},             // данные события
        "timestamp": "2026-01-12T23:31:32Z"
    }
    
    Заголовки:
    - X-Remnawave-Signature: подпись для проверки (HMAC-SHA256 или простое значение)
    - X-Remnawave-Timestamp: временная метка (опционально)
    
    Поддерживаемые события:
    
    Пользователи:
    - user.created, user.modified, user.deleted
    - user.revoked, user.disabled, user.enabled
    - user.limited, user.expired, user.traffic_reset
    - user.expires_in_72_hours, user.expires_in_48_hours, user.expires_in_24_hours
    - user.expired_24_hours_ago, user.first_connected
    - user.bandwidth_usage_threshold_reached, user.not_connected
    
    HWID устройства:
    - user_hwid_devices.added, user_hwid_devices.deleted
    
    Ноды:
    - node.created, node.modified, node.deleted
    - node.disabled, node.enabled
    - node.connection_lost, node.connection_restored
    - node.traffic_notify
    
    Сервис:
    - service.panel_started
    - service.login_attempt_failed, service.login_attempt_success
    
    Ошибки:
    - errors.bandwidth_usage_threshold_reached_max_notifications
    
    CRM (биллинг):
    - crm.infra_billing_node_payment_in_7_days
    - crm.infra_billing_node_payment_in_48hrs
    - crm.infra_billing_node_payment_in_24hrs
    - crm.infra_billing_node_payment_due_today
    - crm.infra_billing_node_payment_overdue_24hrs
    - crm.infra_billing_node_payment_overdue_48hrs
    - crm.infra_billing_node_payment_overdue_7_days
    """
    # Читаем тело запроса как байты для проверки HMAC подписи
    body = await request.body()
    
    # Проверяем подпись
    if not verify_webhook_secret(request, body):
        logger.warning("Webhook request rejected: invalid secret")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        # Парсим JSON из прочитанного тела
        data = json.loads(body.decode('utf-8'))
        event = data.get("event", "")
        timestamp = data.get("timestamp")
        meta = data.get("meta") or {}

        # Анти-replay: устаревший подписанный вебхук отклоняем
        if not _webhook_timestamp_fresh(timestamp):
            logger.warning("Webhook rejected: stale timestamp %r (possible replay)", timestamp)
            raise HTTPException(status_code=401, detail="Stale webhook timestamp")

        logger.info("📩 Webhook: %s", event)
        
        # Получаем данные события
        event_data = data.get("data", {})
        
        # Получаем бот из контекста приложения
        bot: Optional[Bot] = request.app.state.bot
        if not bot:
            logger.error("Bot instance not found in app state")
            raise HTTPException(status_code=500, detail="Bot instance not available")
        
        # Синхронизируем данные в БД и получаем diff для уведомлений
        diff_result = None
        try:
            diff_result = await sync_service.handle_webhook_event(event, event_data)
        except Exception as sync_exc:
            # рассинхрон локальной БД с панелью — это ошибка, и без трейса
            # её причину не восстановить
            logger.error("Failed to sync webhook event %s to database: %s",
                         event, sync_exc, exc_info=True)
        
        # Обрабатываем события по категориям
        if event.startswith("user."):
            await _handle_user_event(bot, event, event_data, diff_result, meta)
        elif event.startswith("node."):
            await _handle_node_event(bot, event, event_data, diff_result)
        elif event.startswith("service."):
            await _handle_service_event(bot, event, event_data)
        elif event.startswith("user_hwid_devices."):
            await _handle_hwid_event(bot, event, event_data)
        elif event.startswith("errors."):
            await _handle_error_event(bot, event, event_data)
        elif event.startswith("crm."):
            await _handle_crm_event(bot, event, event_data)
        elif event.startswith("torrent_blocker."):
            await _handle_torrent_blocker_event(bot, event, event_data)
        else:
            logger.debug("Unknown event type: %s", event)
            await send_generic_notification(
                bot=bot,
                title="Неизвестное событие",
                message=f"Получено событие: <code>{_esc(event)}</code>\n\nДанные: <code>{_esc(str(event_data)[:200])}</code>",
                emoji="❓",
            )
        
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "message": "Notification sent"}
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error processing webhook: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


def _expiration_action_from_hours(hours) -> str:
    """2.8.0: единое событие user.expiration несёт meta.expiration (часы
    относительно expireAt). Маппим стандартные значения на прежние действия,
    чтобы логика уведомлений осталась без изменений. Отрицательное — за N часов
    ДО истечения, положительное — через N часов ПОСЛЕ."""
    try:
        h = int(hours)
    except (TypeError, ValueError):
        return "expired"
    mapping = {-72: "expires_in_72h", -48: "expires_in_48h", -24: "expires_in_24h", 24: "expired_24h_ago"}
    if h in mapping:
        return mapping[h]
    return "expired_24h_ago" if h > 0 else "expires_in_24h"


async def _handle_user_event(bot: Bot, event: str, event_data: dict, diff_result: dict = None, meta: dict = None) -> None:
    """Обрабатывает события пользователей с поддержкой diff."""
    if not event_data:
        logger.warning("User data not found in webhook payload")
        return
    
    # Извлекаем UUID пользователя (v2) или числовой id (panel v3)
    user_uuid = event_data.get("uuid") or event_data.get("id")
    
    if not user_uuid:
        logger.warning("User UUID not found in webhook data")
        return
    
    # Определяем действие для уведомления на основе официальных событий
    special_events = {
        "user.expired": "expired",
        "user.expires_in_72_hours": "expires_in_72h",
        "user.expires_in_48_hours": "expires_in_48h",
        "user.expires_in_24_hours": "expires_in_24h",
        "user.expired_24_hours_ago": "expired_24h_ago",
        "user.revoked": "revoked",
        "user.disabled": "disabled",
        "user.enabled": "enabled",
        "user.limited": "limited",
        "user.traffic_reset": "traffic_reset",
        "user.first_connected": "first_connected",
        "user.bandwidth_usage_threshold_reached": "bandwidth_threshold",
        "user.not_connected": "not_connected",
    }
    
    if event == "user.created":
        action = "created"
        # Если бот сам создал этого пользователя — вебхук уже не нужен,
        # бот отправил уведомление сам.
        username = event_data.get("username") if isinstance(event_data, dict) else None
        if username and username in BOT_CREATING_USERS:
            logger.debug("Skipping webhook user.created notification for %s (bot handled)", username)
            return
    elif event == "user.modified":
        action = "updated"
    elif event == "user.deleted":
        action = "deleted"
    elif event == "user.expiration":
        # 2.8.0: единое событие истечения с количеством часов в meta.expiration
        action = _expiration_action_from_hours((meta or {}).get("expiration"))
    elif event in special_events:
        action = special_events[event]
    else:
        action = "updated"
    
    # Нормализуем структуру данных пользователя
    if "response" not in event_data:
        user_data = {"response": event_data}
    else:
        user_data = event_data
    
    # Извлекаем данные из diff_result
    old_user_info = None
    changes = None
    if diff_result:
        old_user_info = diff_result.get("old_data")
        changes = diff_result.get("changes")
    
    
    subscription_url = None
    if action == "created":
        # Извлекаем subscriptionUrl из event_data для QR-кода
        info = user_data.get("response", user_data)
        subscription_url = info.get("subscriptionUrl")
    
    await send_user_notification(
        bot=bot,
        action=action,
        user_info=user_data,
        old_user_info=old_user_info,
        changes=changes,
        event_type=event,
        subscription_url=subscription_url,
    )


async def _handle_node_event(bot: Bot, event: str, event_data: dict, diff_result: dict = None) -> None:
    """Обрабатывает события нод с поддержкой diff."""
    # Нормализуем структуру данных
    if "response" not in event_data:
        node_data = {"response": event_data}
    else:
        node_data = event_data
    
    # Извлекаем данные из diff_result
    old_node_data = None
    changes = None
    if diff_result:
        old_node_data = diff_result.get("old_data")
        changes = diff_result.get("changes")
    
    logger.debug("Node notification: event=%s", event)
    
    await send_node_notification(
        bot=bot,
        event=event,
        node_data=node_data,
        old_node_data=old_node_data,
        changes=changes,
    )


async def _handle_torrent_blocker_event(bot: Bot, event: str, event_data: dict) -> None:
    """Отчёты плагина torrent-blocker с ноды.

    Панель шлёт их вебхуком, а под наши префиксы событие не подходило и
    падало в общую ветку: владелец получал «Неизвестное событие» с куском
    сырого словаря вместо человеческого текста.
    """
    node = event_data.get("node") if isinstance(event_data, dict) else None
    node_name = ""
    if isinstance(node, dict):
        node_name = str(node.get("name") or "").strip()

    lines = []
    if node_name:
        lines.append(f"Нода: <b>{_esc(node_name)}</b>")

    # Человек один, а полей под него в отчёте два: username и email. Берём
    # первое непустое — иначе в уведомлении дважды подряд идёт строка
    # «Пользователь» с разными написаниями одного и того же абонента.
    who = event_data.get("username") or event_data.get("email") if isinstance(event_data, dict) else None
    if who:
        lines.append(f"Пользователь: <code>{_esc(str(who))}</code>")

    # Состав отчёта у плагина меняется от версии к версии, поэтому берём то,
    # что есть, и не пытаемся угадать полную схему.
    for key, label in (("ip", "IP"), ("destination", "Назначение"),
                       ("action", "Действие"), ("reason", "Причина")):
        value = event_data.get(key) if isinstance(event_data, dict) else None
        if value:
            lines.append(f"{label}: <code>{_esc(str(value))}</code>")

    await send_generic_notification(
        bot=bot,
        title="Торрент-блокировщик",
        message=chr(10).join(lines) if lines else "Нода прислала отчёт торрент-блокировщика.",
        emoji="🚫",
    )


async def _handle_service_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события сервиса."""
    logger.debug("Service notification: event=%s", event)
    
    await send_service_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


async def _handle_hwid_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события HWID устройств."""
    logger.debug("HWID notification: event=%s", event)
    
    # Устройства синхронизируются в user_hwid_devices через sync_service.handle_webhook_event()
    # который вызывается выше в handle_webhook() до этого обработчика уведомлений
    
    await send_hwid_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


async def _handle_error_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события ошибок."""
    logger.debug("Error notification: event=%s", event)
    
    await send_error_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


async def _handle_crm_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события CRM (биллинг инфраструктуры)."""
    logger.debug("CRM notification: event=%s", event)
    
    await send_crm_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


from src.utils.formatters import _esc  # noqa: E402


@app.get("/webhook/health")
async def webhook_health():
    """Проверка здоровья webhook сервера."""
    return JSONResponse(status_code=200, content={"status": "ok", "service": "webhook"})


@app.post("/webhook/test")
async def test_webhook(request: Request):
    """
    Тестовый endpoint для проверки работы webhook.
    Принимает userUuid и отправляет уведомление об обновлении.
    """
    # Читаем тело запроса как байты для проверки HMAC подписи
    body = await request.body()
    
    # Проверяем подпись
    if not verify_webhook_secret(request, body):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        # Парсим JSON из прочитанного тела
        data = json.loads(body.decode('utf-8'))
        user_uuid = data.get("userUuid")
        if not user_uuid:
            raise HTTPException(status_code=400, detail="userUuid is required")
        
        logger.info("Test webhook received for user_uuid=%s", user_uuid)
        
        # Получаем данные пользователя из API
        try:
            from shared.data_access import resolve_panel_user_id
            user = await api_client.get_user_by_id(await resolve_panel_user_id(user_uuid))
        except NotFoundError:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Получаем бот из контекста приложения
        bot: Optional[Bot] = request.app.state.bot
        if not bot:
            raise HTTPException(status_code=500, detail="Bot instance not available")
        
        # Отправляем тестовое уведомление
        await send_user_notification(
            bot=bot,
            action="updated",
            user_info=user,
            old_user_info=None,
        )
        
        return JSONResponse(
            status_code=200,
            content={"status": "ok", "message": "Test notification sent"}
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error processing test webhook: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
