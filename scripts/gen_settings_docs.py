"""Генератор страницы «Настройки панели» для сайта документации.

Настроек около двухсот, и держать их описания вручную синхронными с кодом
невозможно: любая новая настройка через месяц окажется недокументированной,
а удалённая останется в тексте навсегда. Поэтому справочник собирается из
того же каталога, по которому панель строит интерфейс, и переводов, которыми
подписаны те же настройки во фронте.

Запуск (из корня репозитория):

    python scripts/gen_settings_docs.py

Пишет docs/reference/settings.md и docs/en/reference/settings.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from shared.config_service import DEFAULT_CONFIG_DEFINITIONS  # noqa: E402

LOCALES = ROOT / "web" / "frontend" / "src" / "locales"

# Порядок разделов на странице: сначала то, что настраивают в первый день,
# потом редкое. Порядок в самом каталоге настроек другой — он про интерфейс.
CATEGORY_ORDER = [
    "general",
    "notifications",
    "violations",
    "security",
    "mailserver",
    "backup",
    "reports",
    "finance",
    "performance",
    "sync",
]

INTRO = {
    "ru": {
        "general": "Базовые вещи: язык, логи, доступ к панели Remnawave, ключи внешних сервисов. Часть значений здесь — секреты, они правятся на своих страницах, а в списке настроек показываются только для справки.",
        "notifications": "Куда и о чём писать в Telegram. Топики раскладывают события по темам форума, типы уведомлений включают и выключают отдельные события.",
        "violations": "Самый большой раздел: анализаторы, пороги срабатывания, автоматические действия и сроки хранения. Что означают анализаторы и как разбирать инциденты — в разделе [Анти-абуз](/guide/anti-abuse).",
        "security": "Защита самой панели и детект атак на ноды: методы входа, ограничение перебора, чёрный список пользователей.",
        "mailserver": "Встроенный почтовый сервер: TLS, приём входящих, спам-оценка, сроки хранения. Как поднять — в разделе [Почтовый сервер](/guide/mail).",
        "backup": "Расписание, сроки хранения и «мёртвая рука» — алерт о том, что бэкапов давно не было. Подробнее в разделе [Бэкапы](/guide/backups).",
        "reports": "Периодические сводки: что присылать, когда и кому.",
        "finance": "Учёт расходов на инфраструктуру и доходов: валюта отчётов, курсы, напоминания о списаниях, синхронизация с API хостеров.",
        "performance": "Пулы соединений, кэш и интервалы фоновых задач. Трогать стоит, когда упёрлись в потолок, а не заранее.",
        "sync": "Синхронизация с панелью Remnawave.",
    },
    "en": {
        "general": "The basics: language, logs, access to the Remnawave panel, third-party service keys. Some values here are secrets managed on their own pages and shown in the list for reference only.",
        "notifications": "Where and what to write in Telegram. Topics spread events across forum threads, notification types switch individual events on and off.",
        "violations": "The largest section: analyzers, thresholds, automatic actions and retention. What the analyzers mean and how to review incidents is in [Anti-abuse](/en/guide/anti-abuse).",
        "security": "Protection of the panel itself plus node attack detection: login methods, brute-force limits, user blacklist.",
        "mailserver": "The built-in mail server: TLS, inbound mail, spam scoring, retention. Setup is described in [Mail server](/en/guide/mail).",
        "backup": "Schedule, retention and the dead-man switch that warns when backups have stopped happening. See [Backups](/en/guide/backups).",
        "reports": "Periodic summaries: what to send, when and to whom.",
        "finance": "Infrastructure spending and income: reporting currency, exchange rates, payment reminders, sync with provider APIs.",
        "performance": "Connection pools, cache and background task intervals. Worth touching when you hit a ceiling, not before.",
        "sync": "Synchronisation with the Remnawave panel.",
    },
}

PAGE_HEADER = {
    "ru": """# Настройки панели

Почти всё в панели настраивается из интерфейса, без правки файлов и перезапуска: **Настройки**. Изменение применяется сразу.

Значение берётся по цепочке **база данных → `.env` → значение по умолчанию**. Пока настройку не трогали в интерфейсе, работает то, что задано в `.env` или зашито в код; после первого изменения она живёт в базе, и `.env` на неё больше не влияет.

В списке настройки помечены: `В БД` — значение переопределено и хранится в базе, `.env` — взято из окружения, `По умолч.` — из кода. Отдельные значения только для чтения: они управляются со своих страниц, а здесь показаны для полноты.

::: tip Эта страница собрана из кода
Названия, описания и значения по умолчанию берутся прямо из каталога настроек панели, поэтому не расходятся с тем, что вы видите в интерфейсе. Обновляется командой `python scripts/gen_settings_docs.py`.
:::
""",
    "en": """# Panel settings

Almost everything is configured from the interface, with no file editing and no restart: the **Settings** page. Changes apply immediately.

A value is resolved through the chain **database → `.env` → built-in default**. Until a setting is touched in the interface, whatever is in `.env` or in the code applies; after the first change it lives in the database and `.env` no longer affects it.

The list marks each setting: `DB` — overridden and stored in the database, `.env` — taken from the environment, `Default` — from the code. A few values are read-only: they are managed from their own pages and listed here for completeness.

::: tip This page is generated from the code
Names, descriptions and defaults come straight from the panel settings catalogue, so they cannot drift from what you see in the interface. Regenerate with `python scripts/gen_settings_docs.py`.
:::
""",
}

TABLE_HEAD = {
    "ru": "| Настройка | Ключ | По умолчанию | Что делает |\n|---|---|---|---|",
    "en": "| Setting | Key | Default | What it does |\n|---|---|---|---|",
}

READONLY_NOTE = {"ru": "только чтение", "en": "read-only"}
EMPTY_DEFAULT = {"ru": "пусто", "en": "empty"}
NO_SUBCATEGORY = {"ru": "Основное", "en": "Main"}

FOOTER = {
    "ru": "\n## Настройки агента\n\nПеременные агента задаются на самой ноде и в этот список не попадают — см. [Node Agent](/guide/node-agent#переменные-агента).\n",
    "en": "\n## Agent settings\n\nAgent variables are set on the node itself and are not part of this list — see [Node Agent](/en/guide/node-agent#agent-variables).\n",
}


def load_translations(locale: str) -> Dict[str, Any]:
    data = json.loads((LOCALES / locale / "translation.json").read_text(encoding="utf-8"))
    return data.get("settings", {})


def cell(text: str) -> str:
    """Экранирование под ячейку таблицы.

    Перенос строки и вертикальная черта разваливают markdown-таблицу, а
    угловые и фигурные скобки VitePress разбирает как Vue-разметку: описание
    с «mail.<первый домен>» роняет сборку с «Element is missing end tag».
    """
    text = text.replace("|", "\\|").replace("\n", " ").strip()
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("{{", "&#123;&#123;").replace("}}", "&#125;&#125;")


def describe(item: Dict[str, Any], strings: Dict[str, Any], locale: str) -> tuple[str, str]:
    """Подпись и описание настройки: сначала перевод, иначе то, что в каталоге."""
    entry = strings.get("configItems", {}).get(item["key"], {})
    label = entry.get("label") or item.get("display_name") or item["key"]
    description = entry.get("description") or item.get("description") or ""

    notes = []
    if item.get("is_readonly"):
        notes.append(READONLY_NOTE[locale])
    if item.get("env_var_name"):
        notes.append(f"`{item['env_var_name']}`")
    if notes:
        description = f"{description} ({', '.join(notes)})" if description else f"({', '.join(notes)})"

    return label, description


def render(locale: str) -> str:
    strings = load_translations(locale)
    categories = strings.get("categories", {})
    subcategories = strings.get("subcategories", {})

    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for item in DEFAULT_CONFIG_DEFINITIONS:
        by_category.setdefault(item.get("category", "general"), []).append(item)

    # Категория, забытая в CATEGORY_ORDER, не должна исчезнуть со страницы.
    order = CATEGORY_ORDER + [c for c in by_category if c not in CATEGORY_ORDER]

    out = [PAGE_HEADER[locale]]
    for category in order:
        items = by_category.get(category)
        if not items:
            continue

        title = categories.get(category, category)
        out.append(f"\n## {title}\n")
        intro = INTRO[locale].get(category)
        if intro:
            out.append(f"{intro}\n")

        groups: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            groups.setdefault(item.get("subcategory") or "", []).append(item)

        multiple = len(groups) > 1
        for subcategory, group in groups.items():
            if multiple:
                name = subcategories.get(subcategory, subcategory) if subcategory else NO_SUBCATEGORY[locale]
                out.append(f"\n### {name}\n")

            out.append(TABLE_HEAD[locale])
            for item in sorted(group, key=lambda i: i.get("sort_order", 0)):
                label, description = describe(item, strings, locale)
                default = item.get("default_value")
                default = f"`{default}`" if default not in (None, "") else EMPTY_DEFAULT[locale]
                out.append(
                    f"| **{cell(label)}** | `{item['key']}` | {default} | {cell(description)} |"
                )
            out.append("")

    out.append(FOOTER[locale])
    return "\n".join(out)


def main() -> None:
    targets = {
        "ru": ROOT / "docs" / "reference" / "settings.md",
        "en": ROOT / "docs" / "en" / "reference" / "settings.md",
    }
    for locale, path in targets.items():
        path.write_text(render(locale), encoding="utf-8")
        print(f"{path.relative_to(ROOT)}: {len(DEFAULT_CONFIG_DEFINITIONS)} настроек")


if __name__ == "__main__":
    main()
