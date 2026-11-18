"""Validation tests for access-policy rules."""
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["post", "patch"])
@pytest.mark.parametrize("actions", [["edit"], ["delete"], ["view", "edit"]])
async def test_user_rules_reject_unsupported_actions(client, method, actions):
    rule = {
        "resource_type": "user",
        "scope_type": "uuid",
        "scope_value": "11111111-1111-1111-1111-111111111111",
        "actions": actions,
    }
    with patch("shared.database.db_service") as db:
        db.is_connected = True
        db.create_access_policy = AsyncMock()
        db.get_access_policy = AsyncMock(return_value={
            "id": 7,
            "name": "user policy",
            "description": None,
            "rules": [],
            "role_ids": [],
            "admin_ids": [],
        })
        db.update_access_policy = AsyncMock()
        if method == "post":
            response = await client.post(
                "/api/v2/access-policies",
                json={"name": "user policy", "rules": [rule]},
            )
        else:
            response = await client.patch(
                "/api/v2/access-policies/7",
                json={"rules": [rule]},
            )

    assert response.status_code == 400, response.text
    assert "only supports the 'view' action" in response.text
    db.create_access_policy.assert_not_awaited()
    db.update_access_policy.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_user_rules_keep_mutation_actions(client):
    rule = {
        "resource_type": "node",
        "scope_type": "uuid",
        "scope_value": "node-1",
        "actions": ["view", "edit", "delete"],
    }
    with patch("shared.database.db_service") as db:
        db.is_connected = True
        db.create_access_policy = AsyncMock(return_value=7)
        db.get_access_policy = AsyncMock(return_value={
            "id": 7,
            "name": "node policy",
            "description": None,
            "rules": [{"id": 11, **rule}],
            "role_ids": [],
            "admin_ids": [],
        })
        response = await client.post(
            "/api/v2/access-policies",
            json={"name": "node policy", "rules": [rule]},
        )

    assert response.status_code == 200, response.text
    assert response.json()["rules"][0]["actions"] == ["view", "edit", "delete"]
