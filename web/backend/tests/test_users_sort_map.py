"""Карта сортировки списка пользователей: всё, что витрина умеет сортировать, есть в SQL."""
from shared.db.users import UsersMixin
from web.backend.api.v2.users import _filter_users_in_memory

# Ключи столбцов таблицы пользователей (web/frontend/src/pages/Users.tsx) и пункты
# мобильного «Сортировать по». Ключ без записи в карте молча сортирует по created_at (#263).
FRONTEND_SORT_KEYS = [
    "username", "status", "used_traffic_bytes", "hwid_device_limit", "online_at", "expire_at",
    "created_at", "created_by_admin_username", "traffic_limit_bytes", "lifetime_used_traffic_bytes",
    "raw_used_traffic_bytes", "tag", "telegram_id", "email", "external_squad_uuid",
    "active_internal_squads", "short_uuid", "description",
]


def test_every_frontend_column_is_sortable_in_sql():
    missing = [k for k in FRONTEND_SORT_KEYS if k not in UsersMixin._PAGINATED_SORT_MAP]
    assert missing == []


def test_lifetime_traffic_reads_user_traffic_of_panel_v3():
    """Регрессия: выражение читало только верхний уровень raw_data, а панель v3
    кладёт трафик в userTraffic — у всех выходил 0, и сортировка «не работала»."""
    expr = UsersMixin._PAGINATED_SORT_MAP["lifetime_used_traffic_bytes"]
    assert "raw_data->'userTraffic'->>'lifetimeUsedTrafficBytes'" in expr
    assert "raw_data->>'lifetimeUsedTrafficBytes'" in expr


def test_internal_squads_sort_uses_jsonb_functions():
    expr = UsersMixin._PAGINATED_SORT_MAP["active_internal_squads"]
    assert "jsonb_array_elements(" in expr and "jsonb_typeof(" in expr
    assert "json_array_elements(" not in expr.replace("jsonb_array_elements(", "")


def test_in_memory_sort_by_internal_squads():
    users = [
        {"uuid": "a", "username": "a", "status": "ACTIVE", "activeInternalSquads": [{"uuid": "2", "name": "VIP"}]},
        {"uuid": "b", "username": "b", "status": "ACTIVE", "activeInternalSquads": ["Alpha"]},
        {"uuid": "c", "username": "c", "status": "ACTIVE", "activeInternalSquads": None},
    ]
    asc, _ = _filter_users_in_memory(users, sort_by="active_internal_squads", sort_order="asc")
    assert [u["uuid"] for u in asc] == ["c", "b", "a"]
    desc, _ = _filter_users_in_memory(users, sort_by="active_internal_squads", sort_order="desc")
    assert [u["uuid"] for u in desc] == ["a", "b", "c"]
