"""Генератор графика роста звёзд — свой SVG вместо внешнего виджета.

Публичные генераторы (star-history.com, starchart.cc) регулярно лежат, а
битая картинка в шапке README выглядит хуже, чем её отсутствие. Поэтому
график рисуется здесь и коммитится в репозиторий: он всегда доступен,
не тянет сторонние домены и переживает любые их падения.

    python scripts/star_history.py [--repo owner/name] [--out путь.svg]

Даты звёзд берутся через GitHub API (заголовок star+json). Токен — из
GITHUB_TOKEN/GH_TOKEN, без него хватит и анонимного лимита на небольшом
репозитории, но с токеном надёжнее.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone

API = "https://api.github.com"
PER_PAGE = 100
# Больше 30 страниц не читаем: 3000 звёзд — уже достаточно для формы кривой,
# а лимит защищает от бесконечного цикла на большом репозитории.
MAX_PAGES = 30

W, H = 800, 280
PAD_L, PAD_R, PAD_T, PAD_B = 56, 20, 24, 36


def fetch_star_dates(repo: str, token: str | None) -> list[datetime]:
    dates: list[datetime] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{API}/repos/{repo}/stargazers?per_page={PER_PAGE}&page={page}"
        req = urllib.request.Request(url)
        req.add_header("Accept", "application/vnd.github.star+json")
        req.add_header("User-Agent", "remnawave-admin-star-history")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                batch = json.load(resp)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"GitHub API {e.code}: {e.reason}") from e
        if not batch:
            break
        for item in batch:
            raw = item.get("starred_at") if isinstance(item, dict) else None
            if raw:
                dates.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
        if len(batch) < PER_PAGE:
            break
    dates.sort()
    return dates


def _nice_step(span: int) -> int:
    """Шаг сетки, дающий 4-6 подписей на осях без дробей."""
    for step in (1, 2, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000):
        if span / step <= 5:
            return step
    return 10000


def render_svg(dates: list[datetime], repo: str) -> str:
    if not dates:
        raise SystemExit("нет данных о звёздах")

    total = len(dates)
    t0, t1 = dates[0].timestamp(), dates[-1].timestamp()
    span = max(t1 - t0, 1.0)
    plot_w = W - PAD_L - PAD_R
    plot_h = H - PAD_T - PAD_B

    def x_of(ts: float) -> float:
        return PAD_L + (ts - t0) / span * plot_w

    def y_of(count: int) -> float:
        return PAD_T + plot_h - (count / total) * plot_h

    points = [(x_of(d.timestamp()), y_of(i + 1)) for i, d in enumerate(dates)]
    # Прореживаем: на 255 точках это незаметно, но на тысячах спасает размер файла.
    if len(points) > 400:
        keep = max(1, len(points) // 400)
        points = points[::keep] + [points[-1]]

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    area = f"{PAD_L},{PAD_T + plot_h} {line} {points[-1][0]:.1f},{PAD_T + plot_h}"

    y_step = _nice_step(total)
    y_ticks = list(range(0, total + y_step, y_step))
    grid = []
    for value in y_ticks:
        y = y_of(value)
        grid.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" '
            f'class="grid"/>'
            f'<text x="{PAD_L - 10}" y="{y + 4:.1f}" class="tick" '
            f'text-anchor="end">{value}</text>'
        )

    x_labels = []
    for frac in (0.0, 0.5, 1.0):
        ts = t0 + span * frac
        label = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%b %Y")
        anchor = "start" if frac == 0 else "end" if frac == 1 else "middle"
        x_labels.append(
            f'<text x="{x_of(ts):.1f}" y="{H - 12}" class="tick" '
            f'text-anchor="{anchor}">{label}</text>'
        )

    updated = datetime.now(timezone.utc).strftime("%d.%m.%Y")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="История звёзд {repo}: {total}">
  <style>
    .bg {{ fill: #0d1117; }}
    .grid {{ stroke: #21262d; stroke-width: 1; }}
    .tick {{ fill: #7d8590; font: 11px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .title {{ fill: #e6edf3; font: 600 13px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .total {{ fill: #f5c518; font: 700 20px -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
    .curve {{ fill: none; stroke: url(#stroke); stroke-width: 2.5; stroke-linejoin: round; stroke-linecap: round; }}
    @media (prefers-color-scheme: light) {{
      .bg {{ fill: #ffffff; }}
      .grid {{ stroke: #e6e8eb; }}
      .tick {{ fill: #6e7781; }}
      .title {{ fill: #1f2328; }}
    }}
  </style>
  <defs>
    <linearGradient id="stroke" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%" stop-color="#8957e5"/>
      <stop offset="100%" stop-color="#f5c518"/>
    </linearGradient>
    <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#f5c518" stop-opacity="0.28"/>
      <stop offset="100%" stop-color="#f5c518" stop-opacity="0"/>
    </linearGradient>
  </defs>

  <rect class="bg" width="{W}" height="{H}" rx="10"/>
  {"".join(grid)}
  <polygon points="{area}" fill="url(#fill)"/>
  <polyline class="curve" points="{line}"/>
  {"".join(x_labels)}

  <text x="{PAD_L}" y="18" class="title">★ История звёзд · {repo}</text>
  <text x="{W - PAD_R}" y="20" class="total" text-anchor="end">{total}</text>
  <text x="{W - PAD_R}" y="{H - 12}" class="tick" text-anchor="end">обновлено {updated}</text>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="Case211/remnawave-admin")
    parser.add_argument("--out", default="docs/star-history.svg")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    dates = fetch_star_dates(args.repo, token)
    svg = render_svg(dates, args.repo)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"{args.out}: {len(dates)} звёзд, {len(svg)} байт")


if __name__ == "__main__":
    main()
