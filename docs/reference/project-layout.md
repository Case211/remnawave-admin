# Структура проекта

```
remnawave-admin/
├── src/                        # Telegram-бот на aiogram
│   ├── handlers/               # пользователи, ноды, хосты, биллинг, нарушения
│   ├── keyboards/              # inline-клавиатуры
│   ├── services/               # приём webhook, отчёты, проверка здоровья
│   └── utils/                  # i18n, форматирование, push
├── shared/                     # общий код бота и веб-панели
│   ├── database.py             # доступ к PostgreSQL
│   ├── api_client.py           # клиент API панели Remnawave
│   ├── config_service.py       # настройки без перезапуска
│   ├── sync.py                 # синхронизация панель → база
│   ├── analyzers/              # анализаторы нарушений
│   ├── push_service.py         # push в мобильное приложение
│   └── metrics.py              # метрики Prometheus
├── web/
│   ├── frontend/               # React, TypeScript, Tailwind, shadcn/ui
│   ├── backend/                # FastAPI: RBAC, аналитика, плагины, почта
│   └── cabinet/                # кабинет клиента (Bedolaga)
├── node-agent/                 # агент для нод
├── monitoring/                 # конфиг Prometheus и правила алертов
├── alembic/                    # миграции базы
├── locales/                    # переводы (ru, en)
├── docs/                       # исходники этого сайта
└── docker-compose.yml          # плюс профили monitoring, collector, redis
```

## Где что искать

| Задача | Куда смотреть |
|--------|---------------|
| Добавить настройку в интерфейс | `shared/config_service.py` — она появится сама |
| Поправить разбор логов Xray | `node-agent/src/collectors/xray_log.py` |
| Изменить логику детекта нарушений | `shared/analyzers/` |
| Добавить эндпоинт панели | `web/backend/api/v2/` |
| Добавить метрику | `web/backend/core/metrics.py` |
| Перевести интерфейс | `locales/` и `web/frontend/src/locales/` |
