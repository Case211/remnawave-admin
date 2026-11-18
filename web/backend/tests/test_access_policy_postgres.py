"""Real PostgreSQL coverage for user access policies.

Set TEST_DATABASE_URL to a disposable database. The test upgrades the production
schema to 0127, verifies the old failure, exercises 0128 through HTTP APIs, and
checks downgrade cleanup. Never point this at a production database.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

import asyncpg
import pytest

pytest.importorskip("alembic", reason="root requirements are not installed")
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from web.backend.api.deps import AdminUser, get_current_admin
from web.backend.api.v2.access_policies import router as access_policies_router
from web.backend.api.v2.users import router as users_router

PROJECT_ROOT = Path(__file__).resolve().parents[3]
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL is not set"),
]


def _uuid(name: str) -> str:
    return str(uuid5(NAMESPACE_DNS, f"rwa-access-policy-integration:{name}"))


async def _insert_user(conn, name: str, *, created_by=None, tag=None, created_at=None) -> str:
    value = _uuid(name)
    await conn.execute(
        """
        INSERT INTO users (uuid, short_uuid, username, status, tag, created_by_admin_id, created_at)
        VALUES ($1, $2, $3, 'active', $4, $5, $6)
        """,
        value,
        name[:16],
        name,
        tag,
        created_by,
        created_at or datetime(2026, 2, 1, tzinfo=timezone.utc),
    )
    return value


async def test_user_policy_migration_api_and_visibility(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))

    # Start at the existing production head, not at an empty synthetic schema.
    command.upgrade(cfg, "0127")
    conn = await asyncpg.connect(TEST_DATABASE_URL)
    db_service = None
    try:
        probe_policy = await conn.fetchval("INSERT INTO access_policies (name) VALUES ('old schema probe') RETURNING id")
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO access_policy_rules (policy_id, resource_type, scope_type, scope_value)
                VALUES ($1, 'user', 'uuid', $2)
                """,
                probe_policy,
                _uuid("blocked-before-0128"),
            )
        await conn.execute("DELETE FROM access_policies WHERE id = $1", probe_policy)

        command.upgrade(cfg, "head")
        head = await conn.fetchval("SELECT version_num FROM alembic_version")
        assert head == "0128"

        # The new constraint still rejects types the API does not know.
        probe_policy = await conn.fetchval("INSERT INTO access_policies (name) VALUES ('unknown type probe') RETURNING id")
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO access_policy_rules (policy_id, resource_type, scope_type, scope_value)
                VALUES ($1, 'device', 'uuid', 'unknown')
                """,
                probe_policy,
            )
        await conn.execute("DELETE FROM access_policies WHERE id = $1", probe_policy)

        from shared.database import db_service as connected_db
        db_service = connected_db
        assert await db_service.connect(TEST_DATABASE_URL)

        app = FastAPI()
        app.include_router(access_policies_router, prefix="/access-policies")
        app.include_router(users_router, prefix="/users")
        current = AdminUser(role="superadmin", account_id=None, username="integration-superadmin")
        app.dependency_overrides[get_current_admin] = lambda: current

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            foreign_uuid = _uuid("foreign-uuid")
            create_uuid = await client.post("/access-policies", json={
                "name": "Users by UUID",
                "description": "before update",
                "rules": [{
                    "resource_type": "user",
                    "scope_type": "uuid",
                    "scope_value": foreign_uuid.upper(),
                    "actions": ["view"],
                }],
            })
            assert create_uuid.status_code == 200, create_uuid.text
            uuid_policy_id = create_uuid.json()["id"]

            read_uuid = await client.get(f"/access-policies/{uuid_policy_id}")
            assert read_uuid.status_code == 200
            assert read_uuid.json()["rules"][0]["scope_value"] == foreign_uuid.upper()

            update_uuid = await client.patch(f"/access-policies/{uuid_policy_id}", json={
                "description": "updated",
                "rules": read_uuid.json()["rules"],
            })
            assert update_uuid.status_code == 200, update_uuid.text
            assert update_uuid.json()["description"] == "updated"
            assert update_uuid.json()["rules"][0]["resource_type"] == "user"

            create_tag = await client.post("/access-policies", json={
                "name": "Users by tag",
                "rules": [{
                    "resource_type": "user",
                    "scope_type": "tag",
                    "scope_value": "vip",
                    "actions": ["view"],
                }],
            })
            assert create_tag.status_code == 200, create_tag.text
            tag_policy_id = create_tag.json()["id"]

            create_node = await client.post("/access-policies", json={
                "name": "Nodes only",
                "rules": [{
                    "resource_type": "node",
                    "scope_type": "tag",
                    "scope_value": "production",
                    "actions": ["view", "edit"],
                }],
            })
            assert create_node.status_code == 200, create_node.text
            node_policy_id = create_node.json()["id"]

            for actions in (["edit"], ["delete"], ["view", "delete"]):
                rejected = await client.post("/access-policies", json={
                    "name": f"Invalid user actions {actions}",
                    "rules": [{
                        "resource_type": "user",
                        "scope_type": "uuid",
                        "scope_value": foreign_uuid,
                        "actions": actions,
                    }],
                })
                assert rejected.status_code == 400, rejected.text

            unknown = await client.post("/access-policies", json={
                "name": "Unknown resource",
                "rules": [{
                    "resource_type": "device",
                    "scope_type": "uuid",
                    "scope_value": "unknown",
                    "actions": ["view"],
                }],
            })
            assert unknown.status_code == 400, unknown.text

            roles = {
                row["name"]: row["id"]
                for row in await conn.fetch("SELECT id, name FROM admin_roles WHERE name = ANY($1)", ["manager", "viewer"])
            }
            accounts = {}
            for key, role_name, unrestricted in (
                ("all_no_user_policy", "manager", True),
                ("owned_no_user_policy", "manager", False),
                ("all_with_user_policy", "viewer", True),
                ("owned_with_user_policy", "viewer", False),
                ("direct_policy", "manager", True),
            ):
                accounts[key] = await conn.fetchval(
                    """
                    INSERT INTO admin_accounts (username, role_id, unrestricted_user_access)
                    VALUES ($1, $2, $3) RETURNING id
                    """,
                    f"integration-{key}",
                    roles[role_name],
                    unrestricted,
                )

            user_policy_ids = [uuid_policy_id, tag_policy_id]
            attached_role = await client.post(
                f"/access-policies/_roles/{roles['viewer']}/attach",
                json={"policy_ids": user_policy_ids},
            )
            assert attached_role.status_code == 200, attached_role.text
            attached_direct = await client.post(
                f"/access-policies/_admins/{accounts['direct_policy']}/attach",
                json={"policy_ids": user_policy_ids},
            )
            assert attached_direct.status_code == 200, attached_direct.text
            attached_nodes = await client.post(
                f"/access-policies/_roles/{roles['manager']}/attach",
                json={"policy_ids": [node_policy_id]},
            )
            assert attached_nodes.status_code == 200, attached_nodes.text

            # This user sorts after the first 100 rows in the default DESC list.
            beyond = await _insert_user(
                conn,
                "user-101-beyond-first-page",
                created_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
            )
            base = datetime(2026, 1, 1, tzinfo=timezone.utc)
            for index in range(100):
                await _insert_user(
                    conn,
                    f"page-filler-{index:03d}",
                    created_at=base + timedelta(minutes=index),
                )

            owned_no_policy = await _insert_user(
                conn, "owned-no-policy", created_by=accounts["owned_no_user_policy"],
            )
            owned_in_scope = await _insert_user(
                conn, "owned-in-scope", created_by=accounts["owned_with_user_policy"], tag="vip",
            )
            owned_out_scope = await _insert_user(
                conn, "owned-out-of-scope", created_by=accounts["owned_with_user_policy"],
            )
            foreign_tag = await _insert_user(conn, "foreign-tag", tag="vip")
            assert await _insert_user(conn, "foreign-uuid") == foreign_uuid

            from shared.rbac import get_visible_user_uuids, invalidate_scope_cache

            async def list_for(account_key: str, role_name: str):
                nonlocal current
                current = AdminUser(
                    username=account_key,
                    role=role_name,
                    role_id=roles[role_name],
                    account_id=accounts[account_key],
                    permissions={("users", "view")},
                )
                invalidate_scope_cache()
                response = await client.get("/users", params={"per_page": 100})
                assert response.status_code == 200, response.text
                return response.json()

            unrestricted = await get_visible_user_uuids(accounts["all_no_user_policy"], "manager")
            assert unrestricted is None
            all_no_policy = await list_for("all_no_user_policy", "manager")
            assert all_no_policy["total"] == 106

            owned_no_policy_page = await list_for("owned_no_user_policy", "manager")
            assert {item["uuid"] for item in owned_no_policy_page["items"]} == {owned_no_policy}

            all_policy_page = await list_for("all_with_user_policy", "viewer")
            assert {item["uuid"] for item in all_policy_page["items"]} == {
                owned_in_scope, foreign_tag, foreign_uuid,
            }
            assert owned_out_scope not in {item["uuid"] for item in all_policy_page["items"]}

            owned_policy_page = await list_for("owned_with_user_policy", "viewer")
            assert {item["uuid"] for item in owned_policy_page["items"]} == {owned_in_scope}

            direct_page = await list_for("direct_policy", "manager")
            assert {item["uuid"] for item in direct_page["items"]} == {
                owned_in_scope, foreign_tag, foreign_uuid,
            }

            # Exercise the real paginated endpoint used by the policy editor.
            current = AdminUser(role="superadmin", account_id=None)
            first_page = await client.get("/users", params={"page": 1, "per_page": 100})
            second_page = await client.get("/users", params={"page": 2, "per_page": 100})
            assert first_page.status_code == second_page.status_code == 200
            assert len(first_page.json()["items"]) == 100
            assert len(second_page.json()["items"]) == 6
            assert beyond not in {item["uuid"] for item in first_page.json()["items"]}
            search = await client.get("/users", params={"per_page": 100, "search": "user-101-beyond-first-page"})
            assert search.status_code == 200, search.text
            assert [item["uuid"] for item in search.json()["items"]] == [beyond]
            too_large = await client.get("/users", params={"per_page": 500})
            assert too_large.status_code == 422

        await db_service.disconnect()
        db_service = None

        # Downgrade removes only user rules and restores the old constraint.
        command.downgrade(cfg, "0127")
        assert await conn.fetchval("SELECT version_num FROM alembic_version") == "0127"
        assert await conn.fetchval("SELECT COUNT(*) FROM access_policy_rules WHERE resource_type = 'user'") == 0
        assert await conn.fetchval("SELECT COUNT(*) FROM access_policy_rules WHERE resource_type = 'node'") == 1
        assert await conn.fetchval("SELECT COUNT(*) FROM access_policies") == 3
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO access_policy_rules (policy_id, resource_type, scope_type, scope_value)
                VALUES ($1, 'user', 'uuid', $2)
                """,
                uuid_policy_id,
                foreign_uuid,
            )
    finally:
        if db_service is not None:
            await db_service.disconnect()
        await conn.close()
