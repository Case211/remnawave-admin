"""Фильтр списка пользователей по внутренним сквадам (API-фолбэк и нормализация)."""
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
    USERS = [
        _user("u1", [{"uuid": "S1", "name": "Standard"}]),
        _user("u2", ["s1", "s3"]),
        _user("u3", [{"uuid": "S2"}]),
        _user("u4", None),
    ]

    def test_filters_members_of_squad(self):
        result, total = _filter_users_in_memory(self.USERS, internal_squad_uuids=["s1"])
        assert total == 2
        assert sorted(u["uuid"] for u in result) == ["u1", "u2"]

    def test_several_squads_mean_any_of_them(self):
        """Мультивыбор: юзер проходит, состоя хотя бы в одном из выбранных."""
        result, total = _filter_users_in_memory(self.USERS, internal_squad_uuids=["S2", "s3"])
        assert total == 2
        assert sorted(u["uuid"] for u in result) == ["u2", "u3"]

    def test_no_filter_keeps_everyone(self):
        _, total = _filter_users_in_memory(self.USERS)
        assert total == 4
