"""API-ключи: ограничения, мягкая ротация, журнал запросов; тело в доставках вебхуков.

Revision ID: 0120
Revises: 0119

- allowed_ips — ключ работает только с этих адресов/подсетей (пусто — с любых);
- user_squads / user_tag — ключ видит и меняет только юзеров этих сквадов/тега;
- prev_key_hash / prev_valid_until — после ротации старый ключ живёт ещё
  несколько часов, чтобы интеграция успела переключиться без простоя;
- api_key_requests — последние запросы ключа (метод, путь, код, IP);
- webhook_deliveries.payload — тело события, чтобы доставку можно было повторить.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0120"
down_revision: Union[str, None] = "0119"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS allowed_ips TEXT[]")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS user_squads TEXT[]")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS user_tag TEXT")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS prev_key_hash TEXT")
    op.execute("ALTER TABLE api_keys ADD COLUMN IF NOT EXISTS prev_valid_until TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_api_keys_prev_hash ON api_keys (prev_key_hash) "
        "WHERE prev_key_hash IS NOT NULL"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS api_key_requests (
            id BIGSERIAL PRIMARY KEY,
            key_id INTEGER NOT NULL REFERENCES api_keys(id) ON DELETE CASCADE,
            method VARCHAR(10) NOT NULL,
            path TEXT NOT NULL,
            status_code INTEGER NOT NULL,
            ip_address VARCHAR(45),
            duration_ms INTEGER,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_api_key_requests_key ON api_key_requests (key_id, id DESC)")
    op.execute("ALTER TABLE webhook_deliveries ADD COLUMN IF NOT EXISTS payload JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE webhook_deliveries DROP COLUMN IF EXISTS payload")
    op.execute("DROP TABLE IF EXISTS api_key_requests")
    op.execute("DROP INDEX IF EXISTS ix_api_keys_prev_hash")
    for column in ("prev_valid_until", "prev_key_hash", "user_tag", "user_squads", "allowed_ips"):
        op.execute(f"ALTER TABLE api_keys DROP COLUMN IF EXISTS {column}")
