"""Онлайн-лицензирование плагинов: license_link + plugin_settings.

Платформа платных плагинов переезжает с офлайн-JWT на keyless-модель
(сервер лицензирования, контракт v1.1): панель хранит связку с сервером
(instance_id + bearer-токен) и кэш entitlements в одиночной строке
``license_link``. Таблица ``plugin_licenses`` офлайн-схемы выпиливается —
платных инсталляций на ней не существовало.

``plugin_settings`` — общее JSON-хранилище настроек плагинов для фасада
``ctx.settings`` (Plugin API v1), чтобы плагины не плодили таблицы под
мелочи.

Revision ID: 0091
Revises: 0090
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0091"
down_revision: Union[str, None] = "0090"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plugin_licenses")
    op.execute(
        """
        CREATE TABLE license_link (
            id               integer PRIMARY KEY CHECK (id = 1),
            instance_id      uuid,
            instance_token   text,
            entitlements_jwt text,
            catalog_cache    jsonb,
            updated_at       timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE plugin_settings (
            plugin_id  text NOT NULL,
            key        text NOT NULL,
            value      jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (plugin_id, key)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plugin_settings")
    op.execute("DROP TABLE IF EXISTS license_link")
    op.execute(
        """
        CREATE TABLE plugin_licenses (
            plugin_id    text PRIMARY KEY,
            jwt_token    text NOT NULL,
            wheel_name   text,
            version      text,
            installed_at timestamptz NOT NULL DEFAULT now(),
            updated_at   timestamptz NOT NULL DEFAULT now()
        )
        """
    )
