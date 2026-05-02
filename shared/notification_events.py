"""Каталог событий уведомлений с группировкой по категориям.

Используется для:
1. Mobile-клиента (динамический UI настроек: рендерим группы и свичи прямо
   из этого каталога — не нужно зашивать список в APK).
2. push_service: фильтрация по `data.event` против device.subscriptions.
3. UI-описаний (label/severity).

Расширение: чтобы добавить новое событие — допиши его в `CATALOG` и в любом
месте (notification_service / bot notifications) клади `event=<id>` в data.
Ничего больше менять не нужно — клиент подтянет на следующем GET /me/notification-events.

Категории совпадают с PUSH_CATEGORIES в `web/backend/api/v2/me_devices.py`:
- violations: нарушения юзеров (от collector/violation_detector)
- alerts: системные алерты, ноды офлайн, эскалации
- info: создание/изменение юзеров, lifecycle подписок, информационное
"""
from __future__ import annotations

from typing import Any, Dict, List


def _e(id: str, label: str, severity: str = "info") -> Dict[str, str]:
    return {"id": id, "label": label, "severity": severity}


CATALOG: List[Dict[str, Any]] = [
    {
        "id": "violations",
        "label": "Нарушения",
        "description": "Детектор abuse: одновременные подключения, гео, ASN, профиль",
        "category": "violations",
        "events": [
            _e("violation.detected", "Нарушение обнаружено", "warning"),
        ],
    },
    {
        "id": "system_alerts",
        "label": "Системные алерты",
        "description": "Падения нод, эскалации алертов от alert_engine",
        "category": "alerts",
        "events": [
            _e("node.connection_lost", "Нода ушла офлайн", "critical"),
            _e("node.connection_restored", "Нода вернулась онлайн", "info"),
            _e("node.disabled", "Нода отключена", "warning"),
            _e("node.enabled", "Нода включена", "info"),
            _e("node.created", "Нода создана", "info"),
            _e("node.modified", "Нода изменена", "info"),
            _e("node.deleted", "Нода удалена", "warning"),
            _e("node.traffic_notify", "Превышение трафика ноды", "warning"),
            _e("alert.fired", "Сработал алерт", "warning"),
            _e("escalation.triggered", "Эскалация неподтверждённого алерта", "critical"),
            _e("service.panel_started", "Панель перезапущена", "info"),
            _e("service.login_attempt_failed", "Неудачная попытка входа", "warning"),
            _e("errors.bandwidth_usage_threshold_reached_max_notifications",
               "Лимит уведомлений по трафику", "warning"),
        ],
    },
    {
        "id": "subscriptions",
        "label": "Подписки юзеров",
        "description": "Истечение подписки и lifecycle юзеров",
        "category": "info",
        "events": [
            _e("user.expires_in_72_hours", "Подписка истекает через 72 ч", "info"),
            _e("user.expires_in_48_hours", "Подписка истекает через 48 ч", "info"),
            _e("user.expires_in_24_hours", "Подписка истекает через 24 ч", "warning"),
            _e("user.expired", "Подписка истекла", "warning"),
            _e("user.expired_24_hours_ago", "Истекла 24 часа назад", "info"),
            _e("user.created", "Юзер создан", "info"),
            _e("user.modified", "Юзер изменён", "info"),
            _e("user.deleted", "Юзер удалён", "warning"),
            _e("user.disabled", "Юзер отключён", "info"),
            _e("user.enabled", "Юзер включён", "info"),
            _e("user.revoked", "Подписка отозвана", "warning"),
            _e("user.limited", "Достиг лимита трафика", "warning"),
            _e("user.traffic_reset", "Трафик сброшен", "info"),
            _e("user.first_connected", "Первое подключение", "info"),
            _e("user.bandwidth_usage_threshold_reached",
               "Достигнут порог трафика", "warning"),
            _e("user.not_connected", "Долго не подключался", "info"),
        ],
    },
    {
        "id": "hwid",
        "label": "Устройства HWID",
        "description": "Регистрация и удаление девайсов юзеров",
        "category": "info",
        "events": [
            _e("user_hwid_devices.added", "Добавлено новое устройство", "info"),
            _e("user_hwid_devices.deleted", "Устройство удалено", "info"),
        ],
    },
    {
        "id": "billing",
        "label": "Биллинг нод",
        "description": "Напоминания об оплате и просрочки",
        "category": "info",
        "events": [
            _e("crm.infra_billing_node_payment_in_7_days", "Оплата через 7 дней", "info"),
            _e("crm.infra_billing_node_payment_in_48hrs", "Оплата через 48 ч", "info"),
            _e("crm.infra_billing_node_payment_in_24hrs", "Оплата через 24 ч", "warning"),
            _e("crm.infra_billing_node_payment_due_today", "Оплата сегодня", "warning"),
            _e("crm.infra_billing_node_payment_overdue_24hrs", "Просрочка 24 ч", "critical"),
            _e("crm.infra_billing_node_payment_overdue_48hrs", "Просрочка 48 ч", "critical"),
            _e("crm.infra_billing_node_payment_overdue_7_days", "Просрочка 7 дней", "critical"),
        ],
    },
]


def all_categories() -> List[str]:
    return list({g["category"] for g in CATALOG})


def all_event_ids() -> List[str]:
    return [e["id"] for g in CATALOG for e in g["events"]]


def category_for_event(event_id: str) -> str:
    """Возвращает категорию для event_id; 'info' если не найдено."""
    for g in CATALOG:
        for e in g["events"]:
            if e["id"] == event_id:
                return g["category"]
    return "info"
