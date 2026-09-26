"""alembic/env.py не должен отбирать у приложения корневые хендлеры логов.

Бэкенд накатывает миграции сам, при старте (main.py → command.upgrade), и
env.py выполняется внутри живого процесса. fileConfig() из alembic.ini
заменяет корневые хендлеры своими — после миграции backend.log и
violations.log перестают писаться до перезапуска.
"""
import logging
from pathlib import Path

import pytest

# В образе web-backend alembic ставится из корневого requirements.txt. Там, где
# его нет, «import alembic» находит каталог миграций alembic/ в корне репозитория.
pytest.importorskip("alembic.config", reason="пакет alembic не установлен")

from alembic.config import Config  # noqa: E402
from alembic.runtime.environment import EnvironmentContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _run_env():
    """Выполнить alembic/env.py так, как это делают команды alembic: офлайн, без БД и без ревизий."""
    cfg = Config(str(PROJECT_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    cfg.set_main_option("sqlalchemy.url", "postgresql://user:pass@localhost/test")
    script = ScriptDirectory.from_config(cfg)
    with EnvironmentContext(cfg, script, fn=lambda rev, context: [], as_sql=True):
        script.run_env()


@pytest.fixture
def isolated_logging(monkeypatch):
    """Вернуть логгеры, которые трогает alembic.ini, в исходное состояние."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    names = ("", "sqlalchemy.engine", "alembic")
    saved = {n: (logging.getLogger(n).handlers[:], logging.getLogger(n).level) for n in names}
    yield
    for name, (handlers, level) in saved.items():
        logger = logging.getLogger(name)
        logger.handlers = handlers
        logger.setLevel(level)


def test_keeps_application_root_handlers(isolated_logging):
    root = logging.getLogger()
    app_handler = logging.NullHandler()
    root.addHandler(app_handler)

    _run_env()

    assert app_handler in root.handlers


def test_cli_run_still_configured_from_alembic_ini(isolated_logging):
    root = logging.getLogger()
    root.handlers = []

    _run_env()

    assert any(type(h) is logging.StreamHandler for h in root.handlers)
