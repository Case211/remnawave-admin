"""Фильтр списка пользователей по внутреннему скваду (API-фолбэк и нормализация)."""
from web.backend.api.v2.users import _filter_users_in_memory, _internal_squad_uuids


def _user(uuid: str, squads):
    return {"uuid": uuid, "username": uuid, "status": "ACTIVE", "activeInternalSquads": squads}


class TestInternalSquadUuids:
    def test_objects_and_strings_become_lowercase_uuids(self):
        value = [{"uuid": "AAA", "name": "Standard"}, "BBB", {"name": "no uuid"}, None]
        assert _internal_squad_uuids(value) == ["aaa", "bbb"]

    def test_non_list_is_empty(self):
        assert _internal_squad_uuids(None) == []
        assert _internal_squad_uuids("AAA") == []


class TestInMemoryFilter:
    def test_filters_members_of_squad(self):
        users = [
            _user("u1", [{"uuid": "S1", "name": "Standard"}]),
            _user("u2", ["s1"]),
            _user("u3", [{"uuid": "S2"}]),
            _user("u4", None),
        ]
        result, total = _filter_users_in_memory(users, internal_squad_uuid="s1")
        assert total == 2
        assert sorted(u["uuid"] for u in result) == ["u1", "u2"]

    def test_no_filter_keeps_everyone(self):
        users = [_user("u1", [{"uuid": "S1"}]), _user("u2", None)]
        _, total = _filter_users_in_memory(users)
        assert total == 2
