"""Бот и shared не импортируют пакет web: в образе бота его нет.

Так уже ломались кнопки «⚠️ Предупредить» и «Закрыть обращение»: код бота
импортировал web.backend…, а в контейнере это «No module named 'web'» —
предупреждение клиенту не уходило, закрытие отвечало «Bedolaga не настроен».
"""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _web_imports(base: str) -> list[str]:
    found = []
    for path in (ROOT / base).rglob("*.py"):
        if "tests" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            else:
                continue
            found += [
                f"{path.relative_to(ROOT)}:{node.lineno} {name}"
                for name in names if name == "web" or name.startswith("web.")
            ]
    return found


def test_bot_and_shared_do_not_import_web():
    assert _web_imports("src") + _web_imports("shared") == []
