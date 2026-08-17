# Разработка

## Локальный запуск

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m src.main
```

В `.env` достаточно указать `API_BASE_URL` на живую панель Remnawave и заполнить обязательные поля из [установки](/guide/installation#_2-заполнить-env).

Полный стенд в Docker:

```bash
docker network create remnawave-network
docker compose -f docker-compose.dev.yml up -d
```

## Фронтенд

```bash
cd web/frontend
npm install
npm run dev
```

React, TypeScript, Vite, Tailwind и shadcn/ui. Тесты — Vitest и Testing Library, сквозные — Playwright.

## Тесты

```bash
# бэкенд панели
python -m pytest web/backend/tests -q

# бот
python -m pytest src/tests -q

# фронтенд
cd web/frontend && npm test -- --run
```

::: warning Наборы гоняются раздельно
`web/backend/tests` и `src/tests` запускаются отдельными командами: у них разное окружение, и в одном прогоне они мешают друг другу.
:::

## Миграции

Alembic, каталог `alembic/versions/`. Применяются автоматически при старте — вручную ничего вызывать не нужно.

```bash
alembic revision -m "что делаем"
alembic upgrade head
```

Плагины приносят свои ветки миграций; они применяются вместе с основными.

## Структура репозитория

Разбор по каталогам — в [справочнике](/reference/project-layout).

## Соглашения

- Код и комментарии на английском, интерфейс — через i18n, обе локали сразу (`ru` и `en`)
- Новая настройка объявляется в `shared/config_service.py` — она сама появится в интерфейсе
- Изменения в API панели Remnawave сверяйте с исходниками панели на нужном теге, а не с чейнджлогом
- Агент версионируется двумя константами: `node-agent/src/version.py` и `shared/agent_version.py` — их поднимают вместе
