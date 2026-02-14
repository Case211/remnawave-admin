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
]
LogResult = Literal["success", "error", "skipped"]

# ── Config validation helpers ────────────────────────────────

_ALLOWED_TRIGGER_KEYS: dict[str, set[str]] = {
    "event": {"event", "min_score", "offline_minutes"},
    "schedule": {"cron", "interval_minutes"},
    "threshold": {"metric", "operator", "value"},
}
_ALLOWED_ACTION_KEYS: dict[str, set[str]] = {
    "disable_user": {"reason"},
    "block_user": {"reason"},
    "notify": {"channel", "webhook_url", "message"},
    "restart_node": {"node_uuid"},
    "cleanup_expired": {"older_than_days"},
    "reset_traffic": {"target_status"},
    "force_sync": {"node_uuid"},
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


# ── Request schemas ──────────────────────────────────────────

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

    @model_validator(mode="after")
    def validate_configs(self) -> "AutomationRuleCreate":
        allowed_t = _ALLOWED_TRIGGER_KEYS.get(self.trigger_type)
        if allowed_t:
            bad = set(self.trigger_config.keys()) - allowed_t
            if bad:
                raise ValueError(f"Unknown trigger_config keys for '{self.trigger_type}': {bad}")
        allowed_a = _ALLOWED_ACTION_KEYS.get(self.action_type)
        if allowed_a:
            bad_a = set(self.action_config.keys()) - allowed_a
            if bad_a:
                raise ValueError(f"Unknown action_config keys for '{self.action_type}': {bad_a}")
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
    description: str
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
    details: str
