"""Add Bedolaga integration cache tables.

Revision ID: 0036
Revises: 0035
Create Date: 2026-02-24

Tables for caching data synced from the Bedolaga bot API.
Static data (users, subscriptions, transactions, stats) is periodically
synced and stored locally for fast analytics queries.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Stats snapshots (periodic overview from /stats/overview) ──
    op.execute("""
        CREATE TABLE IF NOT EXISTS bedolaga_stats_snapshots (
            id SERIAL PRIMARY KEY,
            snapshot_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
            total_users INTEGER DEFAULT 0,
            active_subscriptions INTEGER DEFAULT 0,
            total_revenue NUMERIC(12, 2) DEFAULT 0,
            total_transactions INTEGER DEFAULT 0,
            open_tickets INTEGER DEFAULT 0,
            raw_data JSONB
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_stats_snapshot_at "
        "ON bedolaga_stats_snapshots(snapshot_at DESC)"
    )

    # ── Users cache (synced from /users) ─────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS bedolaga_users_cache (
            id INTEGER PRIMARY KEY,
            telegram_id BIGINT,
            username VARCHAR(255),
            first_name VARCHAR(255),
            last_name VARCHAR(255),
            status VARCHAR(50),
            balance_kopeks BIGINT DEFAULT 0,
            referral_code VARCHAR(100),
            referred_by_id INTEGER,
            has_had_paid_subscription BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP WITH TIME ZONE,
            last_activity TIMESTAMP WITH TIME ZONE,
            raw_data JSONB,
            synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_users_telegram_id "
        "ON bedolaga_users_cache(telegram_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_users_username "
        "ON bedolaga_users_cache(username)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_users_status "
        "ON bedolaga_users_cache(status)"
    )

    # ── Subscriptions cache (synced from /subscriptions) ─────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS bedolaga_subscriptions_cache (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            user_telegram_id BIGINT,
            plan_name VARCHAR(255),
            status VARCHAR(50),
            is_trial BOOLEAN DEFAULT FALSE,
            started_at TIMESTAMP WITH TIME ZONE,
            expires_at TIMESTAMP WITH TIME ZONE,
            traffic_limit_bytes BIGINT,
            traffic_used_bytes BIGINT,
            payment_amount NUMERIC(12, 2),
            payment_provider VARCHAR(100),
            raw_data JSONB,
            synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_subs_user_id "
        "ON bedolaga_subscriptions_cache(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_subs_status "
        "ON bedolaga_subscriptions_cache(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_subs_user_tg "
        "ON bedolaga_subscriptions_cache(user_telegram_id)"
    )

    # ── Transactions cache (synced from /transactions) ───────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS bedolaga_transactions_cache (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            user_telegram_id BIGINT,
            amount NUMERIC(12, 2),
            currency VARCHAR(10) DEFAULT 'RUB',
            provider VARCHAR(100),
            status VARCHAR(50),
            type VARCHAR(50),
            created_at TIMESTAMP WITH TIME ZONE,
            raw_data JSONB,
            synced_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_tx_user_id "
        "ON bedolaga_transactions_cache(user_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_tx_status "
        "ON bedolaga_transactions_cache(status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_tx_created "
        "ON bedolaga_transactions_cache(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_bedolaga_tx_provider "
        "ON bedolaga_transactions_cache(provider)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS bedolaga_transactions_cache")
    op.execute("DROP TABLE IF EXISTS bedolaga_subscriptions_cache")
    op.execute("DROP TABLE IF EXISTS bedolaga_users_cache")
    op.execute("DROP TABLE IF EXISTS bedolaga_stats_snapshots")
