"""Test fixtures for bot tests."""
import os
import sys
import unittest.mock
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("BOT_TOKEN", "123456:TEST-FAKE-TOKEN")
os.environ.setdefault("API_BASE_URL", "http://localhost:3000")

# Mock aiogram before any test module imports it
aiogram_mock = unittest.mock.MagicMock()
aiogram_mock.Bot = unittest.mock.AsyncMock
sys.modules["aiogram"] = aiogram_mock
sys.modules["aiogram.types"] = unittest.mock.MagicMock()
# aiogram.utils.i18n нужен src.utils.i18n; без явного мока submodule "aiogram" (MagicMock)
# не считается пакетом и `from aiogram.utils.i18n import I18n` падает «not a package».
sys.modules["aiogram.utils"] = unittest.mock.MagicMock()
sys.modules["aiogram.utils.i18n"] = unittest.mock.MagicMock()
# Роутеры бота тянут ещё несколько подмодулей. Каждый приходится объявлять
# отдельно по той же причине: MagicMock не пакет, и «from aiogram.X import Y»
# без этого падает на импорте тестируемого модуля.
for _submodule in ("filters", "enums", "exceptions", "fsm", "fsm.context",
                   "fsm.state", "fsm.storage", "fsm.storage.memory", "client",
                   "client.default"):
    sys.modules[f"aiogram.{_submodule}"] = unittest.mock.MagicMock()
