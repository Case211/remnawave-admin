"""Ограничения API-ключа: адреса, с которых он работает, и юзеры, которых он видит."""
from web.backend.api.v3.deps import ApiKeyUser
from web.backend.core.api_key_auth import ip_allowed


def test_ip_allowed_empty_list_means_any():
    assert ip_allowed("8.8.8.8", None)
    assert ip_allowed(None, [])


def test_ip_allowed_matches_subnet_and_exact():
    allowed = ["10.0.0.0/8", "203.0.113.7"]
    assert ip_allowed("10.20.30.40", allowed)
    assert ip_allowed("203.0.113.7", allowed)
    assert not ip_allowed("203.0.113.8", allowed)


def test_ip_allowed_rejects_unknown_address_when_restricted():
    assert not ip_allowed(None, ["10.0.0.0/8"])
    assert not ip_allowed("not-an-ip", ["10.0.0.0/8"])


def test_unrestricted_key_adds_no_condition():
    key = ApiKeyUser(key_id=1, key_name="k")
    assert not key.restricts_users
    assert key.user_scope_condition(3) == ("", [])


def test_scope_condition_numbers_parameters_from_given_index():
    key = ApiKeyUser(key_id=1, key_name="k", user_squads=["sq"], user_tag="vip")
    sql, args = key.user_scope_condition(4, column="user_uuid")
    assert sql.startswith("user_uuid IN (SELECT su.uuid FROM users su WHERE")
    assert "$4::text[]" in sql and "= $5" in sql
    assert args == [["sq"], "vip"]
