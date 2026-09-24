"""Алерты — в автоматизации: один движок вместо двух.

Revision ID: 0122
Revises: 0121

Пороговые правила алертов (CPU/RAM/диск нод, трафик за сутки, онлайн, нода
офлайн) переносятся в правила автоматизаций с действием «уведомить»: те же
порог, пауза, окно «держится N минут», каналы, важность и топик Telegram.
Переносятся только включённые: стандартные выключенные алерты есть среди
шаблонов автоматизаций. Текст уведомления — человеческий, на языке панели
(bot_language), без сырых имён метрик.

Сами алерты выключаются; таблицы и журнал срабатываний остаются как история.
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0122"
down_revision: Union[str, None] = "0121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPERATORS = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "==", "neq": "!="}

# метрика алерта → (метрика автоматизации, категория)
_METRICS = {
    "cpu_usage_percent": ("node_cpu_percent", "nodes"),
    "ram_usage_percent": ("node_memory_percent", "nodes"),
    "disk_usage_percent": ("node_disk_percent", "nodes"),
    "traffic_today_gb": ("traffic_today", "system"),
    "users_online": ("users_online", "system"),
}

_MESSAGES = {
    "ru": {
        "node_cpu_percent": "🔥 CPU на ноде {node_code}: <b>{value}%</b> (порог {threshold}%)",
        "node_memory_percent": "🧠 Память на ноде {node_code}: <b>{value}%</b> (порог {threshold}%)",
        "node_disk_percent": "💾 Диск на ноде {node_code}: <b>{value}%</b> (порог {threshold}%)",
        "traffic_today": "📈 Трафик за сегодня: <b>{traffic_today_gb} ГБ</b>",
        "users_online": "👥 Сейчас онлайн: <b>{users_online}</b>",
        "offline": "🔴 Нода {node_code} офлайн уже <b>{offline_minutes} мин</b>",
    },
    "en": {
        "node_cpu_percent": "🔥 CPU on node {node_code}: <b>{value}%</b> (threshold {threshold}%)",
        "node_memory_percent": "🧠 Memory on node {node_code}: <b>{value}%</b> (threshold {threshold}%)",
        "node_disk_percent": "💾 Disk on node {node_code}: <b>{value}%</b> (threshold {threshold}%)",
        "traffic_today": "📈 Traffic today: <b>{traffic_today_gb} GB</b>",
        "users_online": "👥 Online now: <b>{users_online}</b>",
        "offline": "🔴 Node {node_code} has been offline for <b>{offline_minutes} min</b>",
    },
}


def _notify_config(rule, message: str) -> dict:
    channels = rule["channels"]
    if isinstance(channels, str):
        channels = json.loads(channels)
    channels = channels or ["in_app"]
    config = {
        "channel": "telegram",
        "message": message,
        "channels": [c for c in channels if c in ("in_app", "email")],
        "severity": rule["severity"] if rule["severity"] in ("info", "warning", "critical") else "warning",
    }
    if "telegram" not in channels:
        config["telegram"] = False
    if rule["topic_type"]:
        config["topic_type"] = rule["topic_type"]
    return config


def upgrade() -> None:
    conn = op.get_bind()
    lang = conn.execute(sa.text("SELECT value FROM bot_config WHERE key = 'bot_language'")).scalar()
    messages = _MESSAGES["en" if (lang or "ru").lower().startswith("en") else "ru"]

    rules = conn.execute(sa.text(
        "SELECT * FROM alert_rules WHERE rule_type = 'threshold' AND is_enabled ORDER BY id"
    )).mappings().all()
    for rule in rules:
        operator = _OPERATORS.get(rule["operator"] or "gt", ">")
        threshold = float(rule["threshold"] or 0)
        cooldown = int(rule["cooldown_minutes"] or 0)
        if rule["metric"] == "node_offline_minutes":
            # Событие «нода офлайн» срабатывает один раз на падение — паузы не нужно
            trigger_type, category = "event", "nodes"
            trigger_config = {"event": "node.went_offline", "offline_minutes": int(threshold)}
            message = messages["offline"]
        elif rule["metric"] in _METRICS:
            metric, category = _METRICS[rule["metric"]]
            trigger_type = "threshold"
            trigger_config = {"metric": metric, "operator": operator, "value": threshold}
            if cooldown > 0:
                trigger_config["cooldown_minutes"] = cooldown
            if int(rule["duration_minutes"] or 0) > 0:
                trigger_config["for_minutes"] = int(rule["duration_minutes"])
            message = messages[metric]
        else:
            continue
        conn.execute(
            sa.text(
                "INSERT INTO automation_rules (name, description, is_enabled, category, trigger_type, "
                "trigger_config, conditions, action_type, action_config, created_by) "
                "VALUES (:name, :description, :enabled, :category, :trigger_type, "
                "CAST(:trigger_config AS jsonb), '[]'::jsonb, 'notify', CAST(:action_config AS jsonb), :created_by)"
            ),
            {
                "name": rule["name"],
                "description": rule["description"],
                "enabled": True,
                "category": category,
                "trigger_type": trigger_type,
                "trigger_config": json.dumps(trigger_config),
                "action_config": json.dumps(_notify_config(rule, message), ensure_ascii=False),
                "created_by": rule["created_by"],
            },
        )
    op.execute("UPDATE alert_rules SET is_enabled = false")


def downgrade() -> None:
    # Перенесённые правила автоматизаций не отличить от созданных руками —
    # откат их не трогает; алерты остаются выключенными
    pass
