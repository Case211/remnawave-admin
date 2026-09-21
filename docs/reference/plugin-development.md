# Разработка плагинов

Плагин — обычный Python-пакет, который панель ставит себе `pip install`-ом и поднимает в своём процессе. Он приносит свои HTTP-роуты, права в общей системе ролей, пункт в боковом меню, страницу в интерфейсе, таблицы в базе и фоновые задачи.

Доступ к репозиторию панели для этого не нужен: всё держится на двух entry point и одном модуле-фасаде — [Plugin API](/reference/plugin-api).

::: danger Плагин — это код внутри панели
Wheel ставится в тот же процесс, что и бэкенд, и получает живой доступ к базе, к Panel API и к настройкам. Технических песочниц нет. Владелец панели ставит чужой плагин на тех же основаниях, на которых обновляет саму панель, — только из источника, которому доверяет.
:::

## Минимальный плагин

```
rwa-plugin-hello/
├── pyproject.toml
└── rwa_plugin_hello/
    └── __init__.py
```

### pyproject.toml

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "rwa-plugin-hello"
version = "0.1.0"
description = "Hello — пример плагина remnawave-admin"
requires-python = ">=3.11"
# Нужны для сборки и тестов у себя: на панели wheel ставится с --no-deps
dependencies = ["fastapi>=0.110", "pydantic>=2.5"]

[project.entry-points."rwa.plugin"]
hello = "rwa_plugin_hello:manifest"

[tool.setuptools.packages.find]
where = ["."]
include = ["rwa_plugin_hello*"]
```

Entry point в группе `rwa.plugin` — единственное, по чему панель узнаёт о плагине. Имя точки входа значения не имеет, значение имеет то, что за ней: функция, возвращающая `PluginManifest`.

::: warning Имя дистрибутива
Назовите пакет `rwa-plugin-<id>` либо начните с `rwa-plugin-<id>-`. По этому префиксу панель ищет файлы плагина, когда его удаляют. Пакет с произвольным именем поставится и заработает, но кнопка «Удалить» его wheel не найдёт — придётся чистить каталог руками.
:::

### \_\_init\_\_.py

```python
"""Hello — пример плагина remnawave-admin (Plugin API v1)."""
from __future__ import annotations


def _own_version() -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("rwa-plugin-hello")
    except PackageNotFoundError:   # запуск из исходников, не из wheel
        return "0.0.0"


def _build(ctx):
    from fastapi import APIRouter, Depends

    from web.backend.core.plugin_api import auth_deps
    from web.backend.core.plugins import PluginParts

    AdminUser, require_permission = auth_deps()
    router = APIRouter()

    @router.get("/greeting")
    async def greeting(
        _admin: AdminUser = Depends(require_permission("hello", "view")),
    ) -> dict:
        who = await ctx.settings.get("who", "мир")
        ctx.logger.info("hello.greeting", extra={"who": who})
        return {"hello": who}

    return PluginParts(router=router)


def manifest():
    from web.backend.core.plugins import NavEntry, PluginManifest

    return PluginManifest(
        id="hello",
        name="Hello",
        version=_own_version(),
        api_version=1,
        billing="free",
        build=_build,
        rbac_resources={"hello": ["view", "edit"]},
        navigation=[
            NavEntry(
                path="/plugins/hello",
                label_i18n="Hello",
                icon="Sparkles",
                permission=("hello", "view"),
                section_i18n="nav.sections.plugins",
            ),
        ],
    )
```

Роутер окажется на `/api/v2/plugins/hello`, метод выше — на `/api/v2/plugins/hello/greeting`.

::: tip Импорты панели — внутри функций
Пакет `web.backend.*` существует только там, где запущена панель. Держите эти импорты в теле функций: тогда ваш пакет собирается, импортируется и тестируется на машине без панели — в том числе в CI.
:::

::: tip Версия — из метаданных пакета
Константа с версией рядом с `pyproject.toml` рано или поздно разъедется с ним, и владелец увидит в панели не ту версию, что работает. Единственный источник правды — сам wheel, `importlib.metadata.version()`.
:::

## Сборка

```bash
python -m build --wheel
# либо без отдельной зависимости:
pip wheel . --no-deps -w dist/
```

На выходе `dist/rwa_plugin_hello-0.1.0-py3-none-any.whl`.

Панель принимает файл, чьё имя разбирается как `<имя>-<версия>[-...].whl`, где имя — только буквы, цифры и подчёркивания; setuptools так и называет wheel. Загрузка через интерфейс вдобавок ограничена 50 МБ.

::: warning Своих зависимостей не будет
Wheel ставится с `--no-deps`: ничего, кроме вашего пакета, на панель не приедет. Секция `dependencies` в `pyproject.toml` работает только у вас — при локальной установке и в тестах.

Рассчитывать можно на то, что панель держит сама: `fastapi`, `pydantic`, `asyncpg`, `sqlalchemy`, `alembic`, `aiohttp`, `httpx`, `structlog`, `redis`, `prometheus-client`, `cryptography`, `geoip2`. Точный список — в `requirements.txt` и `web/backend/requirements.txt` того релиза панели, под который вы целитесь.
:::

## Установка

Два пути, оба ведут в один и тот же каталог плагинов.

**Через интерфейс.** Раздел **Плагины** → **Загрузить wheel** → выбрать файл. Панель сохранит его, сразу поставит pip-ом и уберёт из каталога прежние версии того же пакета. Действие только для суперадмина.

**Файлом.** Положить `.whl` в каталог `plugins` рядом с `docker-compose.yml` — внутри контейнера это `/app/plugins`, путь переопределяется переменной `RWA_PLUGINS_DIR`. При следующем старте панель поставит его сама.

::: warning Нужен перезапуск
Python не перечитывает entry point на лету, поэтому контракт — «поставили и перезапустили». Панель об этом пишет в ответе, кнопка перезапуска есть на той же странице.
:::

Что делает панель при старте:

1. Смотрит каталог плагинов, берёт по одному — самому новому — wheel на пакет и ставит те, чей дистрибутив в текущем окружении отсутствует или стоит другой версии.
2. Если что-то поставилось — прогоняет миграции повторно, уже видя ветку нового плагина.
3. Читает манифесты, монтирует роутеры, добавляет права плагина в реестр ролей и выдаёт их суперадмину, поднимает фоновые задачи.

Проверка `pip`-ом, а не отметкой об установке, сделана намеренно: каталог плагинов переживает пересоздание контейнера, а его `site-packages` — нет. После `docker compose pull` wheel остаётся на месте, и панель ставит его заново, без ручных действий.

Загрузчик молчаливо-устойчив: если фабрика упала, `api_version` не совпал или два плагина заявили один `id` — запись в лог и пропуск. Панель от сломанного плагина не падает.

## Разработка без сборки

Чтобы не собирать wheel на каждый чих, панель умеет поднимать плагин прямо из исходников:

```bash
RWA_DEV_PLUGINS=rwa_plugin_hello:manifest
RWA_DEV_PLUGIN_MIGRATIONS=/src/rwa_plugin_hello/migrations/versions
```

`RWA_DEV_PLUGINS` — список `модуль:фабрика` через запятую; модуль должен быть импортируем из процесса панели (проще всего примонтировать исходники в контейнер и добавить путь в `PYTHONPATH`). `RWA_DEV_PLUGIN_MIGRATIONS` — каталоги с ревизиями Alembic, разделённые системным разделителем путей.

Живой скелет для проверки, что загрузчик вообще работает, лежит в репозитории панели — `scripts/plugin_noop.py`:

```bash
RWA_DEV_PLUGINS=scripts.plugin_noop:manifest
# GET /api/v2/plugins        → в списке есть id=noop
# GET /api/v2/plugins/noop/ping → {"pong": true}
```

## Удаление

Кнопка **Удалить** на карточке плагина: панель сносит его wheel из каталога и делает `pip uninstall`, после перезапуска роуты и пункты меню пропадают.

Таблицы плагина при этом остаются. Это осознанно: удаление кода не должно уносить данные владельца, если плагин вернут. Если ваш плагин хочет уметь «удалить всё о себе» — сделайте это отдельной ручкой в своём интерфейсе.

## Чек-лист перед публикацией

- [ ] Дистрибутив называется `rwa-plugin-<id>`, `id` в манифесте совпадает с ним
- [ ] `api_version=1`
- [ ] Версия берётся из `importlib.metadata`, а не из константы
- [ ] Импорты `web.backend.*` — внутри функций; пакет импортируется без панели
- [ ] Никаких зависимостей сверх тех, что уже есть у панели
- [ ] Каждый роут закрыт `require_permission`, ресурс объявлен в `rbac_resources`
- [ ] Таблицы названы с префиксом `plugin_<id>_`, первая ревизия несёт `branch_labels`
- [ ] Фоновая задача переживает исключение и не копит незакрытые соединения
- [ ] Указана минимальная версия панели, если используете что-то новое (страница плагина — с 4.5.4)

## Чего плагин не может

- **Привезти свои зависимости.** `--no-deps`, и это не обойти.
- **Подхватиться без перезапуска.** Установка и удаление требуют рестарта бэкенда.
- **Добавить переводы в интерфейс панели.** Словари локалей лежат во фронте; сторонний плагин в них не попадает. Пишите в `label_i18n` готовый текст — он покажется как есть, но одинаково в обеих локалях. Внутри своей страницы переводите чем хотите.
- **Добавить свою кнопку под уведомлением в Telegram.** Разметку панель соберёт (см. `panel_notify`), но нажатие обрабатывает бот, а его обработчики перечислены в коде панели — `src/handlers/plugin_actions.py`. Для чужого `plugin_id` нажатие вернёт «неизвестный плагин».
- **Отрисоваться в iframe.** Панель штампует `X-Frame-Options: DENY` на каждый ответ, включая роуты плагинов. Страница подключается скриптом — см. [Plugin API](/reference/plugin-api#страница-в-интерфеисе).
