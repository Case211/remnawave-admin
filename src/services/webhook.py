"""Webhook сервер для приема уведомлений об изменении подписки от панели Remnawave."""
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from aiogram import Bot

from src.config import get_settings
from src.services.api_client import api_client, NotFoundError
from src.utils.logger import logger
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


def verify_webhook_secret(request: Request) -> bool:
    """
    Проверяет подпись webhook из заголовка X-Remnawave-Signature.
    
    Согласно официальной документации Remnawave, панель отправляет
    подпись в заголовке X-Remnawave-Signature.
    """
    settings = get_settings()
    if not settings.webhook_secret:
        # Если секрет не настроен, разрешаем все запросы (для разработки)
        logger.warning("WEBHOOK_SECRET not set, allowing all requests")
        return True
    
    # Официальный заголовок от панели Remnawave
    # Проверяем разные варианты имени заголовка (FastAPI нормализует к нижнему регистру)
    signature = (
        request.headers.get("X-Remnawave-Signature") or
        request.headers.get("x-remnawave-signature") or
        request.headers.get("X-REMNAWAVE-SIGNATURE")
    )
    
    # Логируем все заголовки для отладки (без секретных данных)
    all_headers = dict(request.headers)
    logger.debug("Webhook request headers: %s", {k: v for k, v in all_headers.items() if k.lower() not in ['x-remnawave-signature']})
    
    if not signature:
        logger.error(
            "X-Remnawave-Signature header missing. Available headers: %s. "
            "Проверьте, что в панели Remnawave установлена переменная WEBHOOK_SECRET_HEADER",
            list(request.headers.keys())
        )
        return False
    
    # Сравниваем подпись с секретным ключом
    is_valid = signature == settings.webhook_secret
    
    if not is_valid:
        logger.error(
            "Webhook signature mismatch! "
            "Ожидаемая длина: %d, Полученная длина: %d. "
            "Первые 10 символов полученного ключа: '%s'. "
            "Убедитесь, что WEBHOOK_SECRET в боте совпадает с WEBHOOK_SECRET_HEADER в панели Remnawave.",
            len(settings.webhook_secret) if settings.webhook_secret else 0,
            len(signature) if signature else 0,
            signature[:10] if signature else "None"
        )
    
    return is_valid


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
    - X-Remnawave-Signature: подпись для проверки
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
    if not verify_webhook_secret(request):
        logger.warning("Webhook request rejected: invalid secret")
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        data = await request.json()
        logger.info("Received webhook from Remnawave panel: %s", data)
        
        # Определяем тип события (официальные события из events.ts)
        event = data.get("event", "")
        timestamp = data.get("timestamp")
        
        logger.info(
            "Processing webhook event=%s timestamp=%s",
            event,
            timestamp
        )
        
        # Получаем данные события
        event_data = data.get("data", {})
        
        # Получаем бот из контекста приложения
        bot: Optional[Bot] = request.app.state.bot
        if not bot:
            logger.error("Bot instance not found in app state")
            raise HTTPException(status_code=500, detail="Bot instance not available")
        
        # Обрабатываем события по категориям
        if event.startswith("user."):
            await _handle_user_event(bot, event, event_data)
        elif event.startswith("node."):
            await _handle_node_event(bot, event, event_data)
        elif event.startswith("service."):
            await _handle_service_event(bot, event, event_data)
        elif event.startswith("user_hwid_devices."):
            await _handle_hwid_event(bot, event, event_data)
        elif event.startswith("errors."):
            await _handle_error_event(bot, event, event_data)
        elif event.startswith("crm."):
            await _handle_crm_event(bot, event, event_data)
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


async def _handle_user_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события пользователей."""
        
    """Обрабатывает события пользователей."""
    if not event_data:
        logger.warning("User data not found in webhook payload")
        return
    
    # Извлекаем UUID пользователя
    user_uuid = event_data.get("uuid")
    
    if not user_uuid:
        logger.warning("User UUID not found in webhook data")
        return
    
    # Определяем действие для уведомления на основе официальных событий
    if event == "user.created":
        action = "created"
    elif event == "user.modified":
        action = "updated"
    elif event == "user.deleted":
        action = "deleted"
    elif event in (
        "user.revoked", "user.disabled", "user.enabled", "user.limited", 
        "user.expired", "user.traffic_reset",
        "user.expires_in_72_hours", "user.expires_in_48_hours", "user.expires_in_24_hours",
        "user.expired_24_hours_ago", "user.first_connected",
        "user.bandwidth_usage_threshold_reached", "user.not_connected"
    ):
        # Все эти события обрабатываем как обновления
        action = "updated"
    else:
        # Для любых других событий пользователей
        action = "updated"
    
    # Нормализуем структуру данных пользователя
    if "response" not in event_data:
        user_data = {"response": event_data}
    else:
        user_data = event_data
    
    logger.info(
        "Sending user notification event=%s user_uuid=%s",
        event,
        user_uuid
    )
    
    await send_user_notification(
        bot=bot,
        action=action,
        user_info=user_data,
        old_user_info=None,
    )


async def _handle_node_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события нод."""
    logger.info("Sending node notification event=%s", event)
    
    # Нормализуем структуру данных
    if "response" not in event_data:
        node_data = {"response": event_data}
    else:
        node_data = event_data
    
    await send_node_notification(
        bot=bot,
        event=event,
        node_data=node_data,
    )


async def _handle_service_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события сервиса."""
    logger.info("Sending service notification event=%s", event)
    
    await send_service_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


async def _handle_hwid_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события HWID устройств."""
    logger.info("Sending HWID notification event=%s", event)
    
    await send_hwid_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


async def _handle_error_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события ошибок."""
    logger.info("Sending error notification event=%s", event)
    
    await send_error_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


async def _handle_crm_event(bot: Bot, event: str, event_data: dict) -> None:
    """Обрабатывает события CRM (биллинг инфраструктуры)."""
    logger.info("Sending CRM notification event=%s", event)
    
    await send_crm_notification(
        bot=bot,
        event=event,
        event_data=event_data,
    )


def _esc(text: str) -> str:
    """Экранирует HTML символы."""
    if not text:
        return ""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


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
    if not verify_webhook_secret(request):
        raise HTTPException(status_code=401, detail="Unauthorized")
    
    try:
        data = await request.json()
        user_uuid = data.get("userUuid")
        if not user_uuid:
            raise HTTPException(status_code=400, detail="userUuid is required")
        
        logger.info("Test webhook received for user_uuid=%s", user_uuid)
        
        # Получаем данные пользователя из API
        try:
            user = await api_client.get_user_by_uuid(user_uuid)
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
