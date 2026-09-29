"""Ссылки уведомлений ведут на существующие страницы админки.

Неверная ссылка молча уводит клик в никуда: так уведомления о новых письмах
вели на /admin/mail-server, которого во фронте нет.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
APP = ROOT / "web" / "frontend" / "src" / "App.tsx"


def _routes():
    paths = re.findall(r'<Route path="([^"]+)"', APP.read_text(encoding="utf-8"))
    return [p for p in paths if p not in ("*", "/*")]


def _matches(link, routes):
    parts = link.split("?")[0].strip("/").split("/")
    for route in routes:
        rparts = route.strip("/").split("/")
        if len(rparts) == len(parts) and all(r.startswith(":") or r == p for r, p in zip(rparts, parts)):
            return True
    return False


def test_notification_links_point_to_real_pages():
    routes = _routes()
    links = set()
    for py in [*(ROOT / "web" / "backend").rglob("*.py"), *(ROOT / "shared").rglob("*.py")]:
        if "tests" in py.parts:
            continue
        for link in re.findall(r'\blink=f?"(/[^"]*)"', py.read_text(encoding="utf-8")):
            links.add(re.sub(r"\{[^}]+\}", "x", link))  # f-строка: /users/{uuid} → /users/x
    assert "/users/x" in links, "ссылки не нашлись — регэксп устарел"
    bad = sorted(link for link in links if not _matches(link, routes))
    assert not bad, f"ведут на несуществующие страницы: {bad}"
