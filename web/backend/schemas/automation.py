"""Automation schemas for web panel API."""
from typing import Optional, List, Literal, Any
from datetime import datetime
from pydantic import BaseModel, Field, model_validator


# ── Enums / Literals ─────────────────────────────────────────

AutomationCategory = Literal["users", "nodes", "violations", "system"]
TriggerType = Literal["event", "schedule", "threshold"]
ActionType = Literal[
    "disable_user", "block_user", "notify", "restart_node",
    "cleanup_expired", "reset_traffic", "force_sync",
    "enable_node", "disable_node", "throttle_user", "warn_user",
]
LogResult = Literal["success", "error", "skipped"]

# ── Config validation helpers ────────────────────────────────

# Общие для любого триггера: своя пауза между срабатываниями и «И»/«ИЛИ» в условиях
_COMMON_TRIGGER_KEYS = {"cooldown_minutes", "conditions_match"}
_ALLOWED_TRIGGER_KEYS: dict[str, set[str]] = {
    "event": {"event", "min_score", "offline_minutes"} | _COMMON_TRIGGER_KEYS,
    "schedule": {"cron", "interval_minutes"} | _COMMON_TRIGGER_KEYS,
    "threshold": {"metric", "operator", "value", "node_uuid"} | _COMMON_TRIGGER_KEYS,
}
_ALLOWED_ACTION_KEYS: dict[str, set[str]] = {
    "disable_user": {"reason", "duration_hours"},
    "block_user": {"reason", "duration_hours"},
    "notify": {"channel", "webhook_url", "message", "topic_type", "channels", "severity", "buttons",
               "quiet_from", "quiet_to"},
    "restart_node": {"node_uuid", "max_per_hour"},
    "enable_node": {"node_uuid"},
    "disable_node": {"node_uuid"},
    "cleanup_expired": {"older_than_days", "squad_uuids", "tag"},
    "reset_traffic": {"target_status"},
    "force_sync": {"node_uuid"},
    # Урезать скорость через шейпер (как «ограничить» в нарушениях)
    "throttle_user": {"rate_kbit", "duration_hours", "reason"},
    # Предупредить клиента по шаблону из «Нарушения → Предупреждения»
    "warn_user": {"force"},
}
MAX_EXTRA_ACTIONS = 5
# Что реально присылает движок: неизвестное событие или метрика = правило,
# которое никогда не сработает
EVENT_TYPES = {
    "violation.detected", "node.went_offline", "node.online", "user.traffic_exceeded",
    "torrent.detected", "user.created", "user.expired",
}
THRESHOLD_METRICS = {
    "users_online", "traffic_today", "user_traffic_percent",
    "user_node_traffic_gb", "user_node_traffic_today_gb", "user_traffic_today_gb",
    "node_cpu_percent", "node_memory_percent", "node_disk_percent",
    "violations_last_hour", "users_new_today",
}
# Действия, которые меняют юзеров и ноды: шаблоны с ними создаются выключенными
DESTRUCTIVE_ACTIONS = {
    "disable_user", "block_user", "cleanup_expired", "restart_node", "disable_node", "reset_traffic",
    "throttle_user", "warn_user",
}
_MAX_CONFIG_DEPTH = 2
_MAX_CONFIG_STR_LEN = 1000


def _validate_config_values(obj: Any, depth: int = 0) -> None:
    """Reject deeply nested or excessively large config values."""
    if depth > _MAX_CONFIG_DEPTH:
        raise ValueError("Config nesting too deep")
    if isinstance(obj, dict):
        for v in obj.values():
            _validate_config_values(v, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            _validate_config_values(item, depth + 1)
    elif isinstance(obj, str) and len(obj) > _MAX_CONFIG_STR_LEN:
        raise ValueError(f"Config string value exceeds {_MAX_CONFIG_STR_LEN} chars")


def _check_action_keys(action_type: str, action_config: dict) -> None:
    allowed = _ALLOWED_ACTION_KEYS.get(action_type)
    if allowed:
        bad = set(action_config.keys()) - allowed
        if bad:
            raise ValueError(f"Unknown action_config keys for '{action_type}': {bad}")


# ── Request schemas ──────────────────────────────────────────


class ExtraAction(BaseModel):
    """Действие после основного — «уведомить + урезать скорость»."""
    action_type: ActionType
    action_config: dict = Field(default_factory=dict)

class AutomationRuleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    is_enabled: bool = False
    category: AutomationCategory
    trigger_type: TriggerType
    trigger_config: dict = Field(default_factory=dict)
    conditions: list = Field(default_factory=list)
    action_type: ActionType
    action_config: dict = Field(default_factory=dict)
    extra_actions: List[ExtraAction] = Field(default_factory=list, max_length=MAX_EXTRA_ACTIONS)

    @model_validator(mode="after")
    def validate_configs(self) -> "AutomationRuleCreate":
        if self.trigger_type == "event" and self.trigger_config.get("event") not in EVENT_TYPES:
            raise ValueError(f"Unknown event: {self.trigger_config.get('event')!r}")
        if self.trigger_type == "threshold" and self.trigger_config.get("metric") not in THRESHOLD_METRICS:
            raise ValueError(f"Unknown metric: {self.trigger_config.get('metric')!r}")
        allowed_t = _ALLOWED_TRIGGER_KEYS.get(self.trigger_type)
        if allowed_t:
            bad = set(self.trigger_config.keys()) - allowed_t
            if bad:
                raise ValueError(f"Unknown trigger_config keys for '{self.trigger_type}': {bad}")
        _check_action_keys(self.action_type, self.action_config)
        for extra in self.extra_actions:
            _check_action_keys(extra.action_type, extra.action_config)
            _validate_config_values(extra.action_config)
        match = self.trigger_config.get("conditions_match")
        if match is not None and match not in ("all", "any"):
            raise ValueError("conditions_match must be 'all' or 'any'")
        cooldown = self.trigger_config.get("cooldown_minutes")
        if cooldown is not None and (not isinstance(cooldown, int) or isinstance(cooldown, bool)
                                     or not 0 <= cooldown <= 10080):
            raise ValueError("cooldown_minutes must be an integer 0..10080")
        _validate_config_values(self.trigger_config)
        _validate_config_values(self.action_config)
        _validate_config_values(self.conditions)
        return self


class AutomationRuleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    category: Optional[AutomationCategory] = None
    trigger_type: Optional[TriggerType] = None
    trigger_config: Optional[dict] = None
    conditions: Optional[list] = None
    action_type: Optional[ActionType] = None
    action_config: Optional[dict] = None
    extra_actions: Optional[List[ExtraAction]] = Field(None, max_length=MAX_EXTRA_ACTIONS)


# ── Response schemas ─────────────────────────────────────────

class AutomationRuleResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    is_enabled: bool
    category: str
    trigger_type: str
    trigger_config: dict
    conditions: list
    action_type: str
    action_config: dict
    extra_actions: list = Field(default_factory=list)
    last_triggered_at: Optional[datetime] = None
    trigger_count: int
    created_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class AutomationRuleListResponse(BaseModel):
    items: List[AutomationRuleResponse]
    total: int
    page: int
    per_page: int
    pages: int
    total_active: int = 0
    total_triggers: int = 0
    # По всем правилам, а не по текущей странице
    last_triggered_at: Optional[datetime] = None


class AutomationLogEntry(BaseModel):
    id: int
    rule_id: int
    rule_name: Optional[str] = None
    triggered_at: Optional[datetime] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    action_taken: str
    result: str
    details: Optional[dict] = None


class AutomationLogResponse(BaseModel):
    items: List[AutomationLogEntry]
    total: int
    page: int
    per_page: int
    pages: int


class AutomationTemplate(BaseModel):
    id: str
    name: str
    name_key: Optional[str] = None
    description: str
    description_key: Optional[str] = None
    category: str
    trigger_type: str
    trigger_config: dict
    conditions: list
    action_type: str
    action_config: dict


class AutomationTestResult(BaseModel):
    rule_id: int
    would_trigger: bool
    matching_targets: list
    estimated_actions: int
    details: str = ""
    # Данные прогона: trigger_type, event/cron/metric…, action_type, targets —
    # текст собирает фронт на языке админа
    summary: dict = Field(default_factory=dict)
