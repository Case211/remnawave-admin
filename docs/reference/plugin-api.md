# Plugin API

Справочник по точкам расширения. Как собрать и поставить пакет — в [разработке плагинов](/reference/plugin-development).

Плагину разрешено импортировать два модуля панели:

- `web.backend.core.plugin_api` — фасад: контекст, уведомления, доступ к Panel API и GeoIP;
- `web.backend.core.plugins` — дата-классы манифеста: `PluginManifest`, `PluginParts`, `NavEntry`, `ScheduledTask`, `PluginUI`.

Всё остальное — внутренности панели: они меняются между релизами без предупреждения. Фасад расширяется по заявкам, а не впрок; если нужного не хватает, проще попросить, чем лезть в обход.

Текущая версия API — **1**. Манифест с другим `api_version` панель пропускает с записью `plugins.api_version_mismatch` в логе.

## PluginManifest

| Поле | Тип | Смысл |
| --- | --- | --- |
| `id` | `str` | Идентификатор плагина. Им же назван префикс роутов и, по соглашению, RBAC-ресурс. Двоеточий быть не должно. |
| `name` | `str` | Человеческое имя для страницы «Плагины». |
| `version` | `str` | Версия. Берите из метаданных пакета. |
| `api_version` | `int` | Только `1`. |
| `billing` | `"free" \| "subscription"` | `subscription` включает лицензионный гейт (см. ниже). Для стороннего плагина — `free`. |
| `build` | `(ctx) -> PluginParts` | Фабрика роутера и фоновых задач. Без неё плагин зарегистрируется пустым. |
| `rbac_resources` | `dict[str, list[str]]` | Ресурсы и действия, которые плагин добавляет в систему ролей. |
| `navigation` | `list[NavEntry]` | Пункты бокового меню. |
| `ui` | `PluginUI \| None` | Как рисовать страницу плагина. |

Манифест декларативный: панель читает его до того, как что-либо у плагина запустит. Поэтому не считайте в `manifest()` ничего тяжёлого и не ходите в базу — вся работа живёт в `build(ctx)`.

## PluginParts и фоновые задачи

```python
from web.backend.core.plugins import PluginParts, ScheduledTask

def _build(ctx):
    return PluginParts(
        router=build_router(ctx),
        scheduled_tasks=[
            ScheduledTask(
                name="collector",
                interval_seconds=300,
                coro=functools.partial(tick, ctx),
            ),
        ],
    )
```

`ScheduledTask.coro` — корутина без аргументов; контекст в неё удобно замкнуть через `functools.partial`. Панель крутит её вечным циклом: исключение на тике пишется в лог и цикл продолжается, интервал не меньше секунды. Задачи стартуют после регистрации всех плагинов и гасятся вместе с панелью.

Долго спать внутри тика не нужно — интервал уже задан. Соединения к базе берите через `ctx.db`, он возвращает их в общий пул.

## PluginContext

Панель собирает контекст сама и передаёт его в `build(ctx)`.

| Поле | Что это |
| --- | --- |
| `plugin_id` | Идентификатор из манифеста. |
| `logger` | `logging.Logger` с именем `plugin.<id>` — попадает в общий лог панели. |
| `db` | Вход в PostgreSQL панели. |
| `settings` | JSON-хранилище настроек плагина. |
| `license` | Состояние подписки (только для `billing="subscription"`). |
| `cloud` | Вызовы фирменного сервера лицензий. |
| `events` | Отправка событий в исходящие webhook. |
| `telemetry` | Анонимные продуктовые счётчики. |

### ctx.db

```python
rows = await ctx.db.fetch("SELECT uuid FROM users WHERE status = $1", "ACTIVE")
row  = await ctx.db.fetchrow("SELECT * FROM plugin_hello_items WHERE id = $1", item_id)
n    = await ctx.db.fetchval("SELECT count(*) FROM plugin_hello_items")
await ctx.db.execute("DELETE FROM plugin_hello_items WHERE id = $1", item_id)

async with ctx.db.acquire() as conn:      # своя транзакция
    async with conn.transaction():
        ...
```

Это asyncpg, плейсхолдеры `$1, $2, …`. Живой SQL никак не ограничен — плагин уже внутри панели, ограничивать нечего. Панельные хелперы (`get_user_by_uuid`, `get_user_by_telegram_id`, `get_user_by_short_uuid`, `get_user_uuid_by_email` и остальные методы `db_service`) доступны прямо на `ctx.db`.

::: warning Чужие таблицы — только на чтение
Панельные таблицы читайте сколько угодно, но пишите только в свои. Схема панели меняется между релизами, и запись в неё из плагина ломается первой.
:::

### ctx.settings

Общая таблица `plugin_settings (plugin_id, key, value jsonb)`, на плагин — свой неймспейс.

```python
await ctx.settings.set("threshold", {"warn": 10, "crit": 25})
cfg = await ctx.settings.get("threshold", default={})
await ctx.settings.delete("threshold")
```

Значение — что угодно, что переживёт `json.dumps`. Это место для конфигурации плагина, не для его данных: под данные заводите свои таблицы миграцией.

### ctx.events

```python
ctx.events.emit("item_created", {"id": item_id})
```

Событие уходит в общий диспатч исходящих webhook под именем `plugin.<id>.item_created`. Владелец подписывается на него как на любое [событие панели](/reference/webhook-events). Вызов синхронный и ничего не ждёт.

### ctx.license и ctx.cloud

Оба поля обслуживают платные плагины фирменного магазина: `license` — снапшот состояния подписки, `cloud` — вызовы сервера лицензий. Стороннему плагину они не нужны и работать на нём не будут: `cloud` уходит на сервер, который вашего плагина не знает.

У бесплатного плагина `ctx.license.state` вернёт `missing`, а `usable` — `False`. Это не признак беды: панель на них смотрит только при `billing="subscription"`, а для `free` отдаёт на фронт состояние `not_required`. Не стройте на `ctx.license` свою логику.

Разница между `billing="free"` и `billing="subscription"`: во втором случае панель вешает на каждый роут плагина зависимость, которая отвечает `402` при неактивной подписке, и пропускает тики фоновых задач. Для стороннего плагина это означает «ничего не работает», поэтому `billing="free"`.

### ctx.telemetry

```python
ctx.telemetry.count("report_built")
```

Счётчики копятся в памяти и уезжают на сервер лицензий ближайшим heartbeat. Смысл имеют только для плагинов магазина; в стороннем плагине вызов безвреден, но бесполезен.

## Роуты и права

Роутер монтируется под `/api/v2/plugins/<id>`, теги в OpenAPI — `plugin:<id>`.

Авторизационные зависимости панель отдаёт через фасад, импортировать `web.backend.api.deps` не нужно:

```python
from web.backend.core.plugin_api import auth_deps

AdminUser, require_permission = auth_deps()

@router.put("/settings")
async def put_settings(
    payload: SettingsIn,
    _admin: AdminUser = Depends(require_permission("hello", "edit")),
):
    ...
```

Объявленные в `rbac_resources` пары «ресурс — действие» попадают в общий реестр ролей и появляются на странице [Доступ и роли](/guide/access) как обычные права панели. Суперадмин получает их автоматически при старте, остальным ролям владелец выдаёт руками.

Если ресурс с таким именем у панели уже есть, ваши действия добавятся к его списку, а не затрут его. Чтобы не спорить с панелью за имя, называйте ресурс идентификатором плагина.

::: warning Аутентификация не подразумевается
Панель не вешает проверок на роуты плагина сама (кроме лицензионного гейта у платных). Роут без `require_permission` открыт любому, кто дотянется до API. Закрывайте каждый.
:::

## Навигация

```python
NavEntry(
    path="/plugins/hello",
    label_i18n="Hello",
    icon="Sparkles",
    permission=("hello", "view"),
    section_i18n="nav.sections.plugins",
)
```

- `path` — маршрут во фронте. Для внешней страницы он должен быть `/plugins/<id>`, где `id` — идентификатор плагина с подчёркиваниями, заменёнными на дефисы.
- `label_i18n` — ключ в словаре панели. У стороннего плагина такого ключа нет, и на экран выйдет сама строка; поэтому пишите туда готовый текст. Он будет одинаков в русской и английской локали.
- `permission` — пара «ресурс, действие». Пункт меню не покажется тому, у кого права нет.
- `section_i18n` — заголовок группы в меню. `nav.sections.plugins` переведён панелью («Расширения» / «Extensions») и подставляется сам, если поле опустить.
- `icon` — имя из списка ниже. Незнакомое имя даст `Sparkles`, ошибкой это не считается.

Доступные иконки (набор [Lucide](https://lucide.dev)):

`Activity`, `AlertTriangle`, `BarChart3`, `Bot`, `Bug`, `Globe`, `HardDrive`, `Heart`, `Key`, `LayoutDashboard`, `Mail`, `Search`, `Server`, `Settings`, `Shield`, `ShieldAlert`, `ShieldBan`, `ShieldCheck`, `Sparkles`, `Stethoscope`, `Terminal`, `Users`, `UsersRound`, `Wrench`, `Zap`.

Список намеренно короткий: иначе во фронт пришлось бы тянуть всю библиотеку ради одного плагина.

## Страница в интерфейсе

Плагин объявляет в манифесте, что у него есть своя страница:

```python
from web.backend.core.plugins import PluginUI

PluginManifest(
    ...,
    ui=PluginUI(kind="module", path="/app"),
)
```

Фронт грузит `api_prefix + path` (то есть `/api/v2/plugins/hello/app`) как обычный `<script>` и ждёт, что скрипт зарегистрирует себя:

```js
window.rwaPluginUI['hello'] = {
  mount(el) { /* нарисовать себя внутрь el */ },
  unmount() { /* прибраться при уходе со страницы */ },
}
```

Отдавать скрипт — задача вашего же роутера:

```python
from fastapi import Response

BUNDLE = (Path(__file__).parent / "static" / "app.js").read_text(encoding="utf-8")

@router.get("/app")
async def app_bundle(
    _admin: AdminUser = Depends(require_permission("hello", "view")),
) -> Response:
    return Response(BUNDLE, media_type="application/javascript")
```

Что стоит знать:

- Скрипт отдаётся с того же origin, что и панель, и проходит её CSP (`script-src 'self'`). Тянуть код с чужого домена нельзя — он будет заблокирован.
- Закрывать роут правами можно: веб-фронт держит сессию в HttpOnly-cookie, и браузер приложит её к загрузке скрипта сам.
- `kind` пока только `module`. Iframe не предлагается сознательно: панель ставит `X-Frame-Options: DENY` на все ответы, включая роуты плагинов, так что страница в рамке всё равно не открылась бы.
- Страница монтируется на общий маршрут `/plugins/:pluginId`. Встроенные страницы панели (у плагинов из репозитория) имеют приоритет над ним.
- Если скрипт не загрузился или не зарегистрировал себя, владелец увидит внятное сообщение об ошибке, а не пустой экран.
- Доступно с версии панели **4.5.4**.

Бандл собирайте чем угодно — важно лишь, чтобы получился один самодостаточный файл без внешних загрузок. Стили кладите туда же; тему панели можно читать из CSS-переменных документа.

## Миграции

Плагин везёт свои таблицы отдельной веткой Alembic. Второй entry point указывает на каталог с ревизиями:

```toml
[project.entry-points."rwa.plugin.migrations"]
hello = "rwa_plugin_hello.migrations:versions_path"

[tool.setuptools.package-data]
"rwa_plugin_hello" = ["migrations/versions/*.py"]
```

```python
# rwa_plugin_hello/migrations/__init__.py
import os

def versions_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "versions")
```

Первая ревизия обязана открывать собственную ветку:

```python
revision = "hello_001"
down_revision = None
branch_labels = ("plugin_hello",)
depends_on = None

def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS plugin_hello_items (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS plugin_hello_items")
```

Правила простые:

- `down_revision = None` и `branch_labels = ("plugin_<id>",)` у первой ревизии — иначе ваши ревизии столкнутся с панельными в одном графе.
- Идентификаторы ревизий уникальны глобально: берите префикс плагина, а не `0001`.
- Таблицы называйте `plugin_<id>_*` — так владелец видит в базе, чьё это.
- Не забудьте `package-data`: без него файлы ревизий не попадут в wheel, и панель найдёт пустой каталог.
- `CREATE TABLE IF NOT EXISTS` и `DROP TABLE IF EXISTS` — привычка полезная: миграции могут прогоняться повторно после установки wheel.

Ревизии применяются вместе с панельными при старте; вручную ничего звать не нужно.

## Уведомления

```python
from web.backend.core.plugin_api import panel_notify

await panel_notify(
    title="Порог превышен",
    body="Узел <b>de-1</b> держит 120% нормы час подряд",
    severity="warning",              # info | warning | critical
    plugin_id=ctx.plugin_id,
    link="/plugins/hello",
    group_key="hello:de-1",
)
```

Уведомление уходит разом в интерфейс панели, в Telegram (общий чат и личные каналы админов) и в push. Возвращает `bool` — отправка не бросает исключений, чтобы не ронять вызывающий код.

Тонкости: эмодзи по severity панель ставит сама, в `title` его класть не нужно; `body` — телеграм-HTML, строки с отступом в три пробела превращаются в список; `group_key` глушит повторы: уведомление с тем же ключом, пришедшее следом в ближайшие минуты, до адресата не дойдёт.

Параметр `actions` собирает кнопки под сообщением в Telegram из троек `{text, action, ref}`. Разметку панель построит, но нажатие обрабатывает бот, а его обработчики перечислены в коде панели — стороннему плагину эта часть недоступна, нажатие вернёт «неизвестный плагин».

## Прочее из фасада

| Функция | Зачем |
| --- | --- |
| `panel_api()` | Клиент Panel API Remnawave: мутации пользователей, сброс трафика, отзыв подписки. |
| `panel_user_from_api(uuid)` | Пользователь из Panel API, когда локального кэша не хватает. |
| `normalize_user(raw)` | Ответ Panel API в панельный вид (camelCase → snake_case). |
| `geoip_service()` | GeoIP панели: `lookup_batch` и кэш `ip_metadata`. |
| `panel_db` | Тот же вход в базу, что `ctx.db`, — для модулей, которым контекст не передали. |

## Что панель отдаёт о плагинах

`GET /api/v2/plugins` — список зарегистрированных плагинов для любого авторизованного админа: `id`, `name`, `version`, `license_state`, `api_prefix`, навигация и описание страницы. Отсюда фронт узнаёт, что рисовать.

Операции с кодом (`/api/v2/admin/plugins/...`: загрузка wheel, установка, удаление, перезапуск) — только для суперадмина.
