# Project layout

```
remnawave-admin/
├── src/                        # Telegram bot, aiogram
│   ├── handlers/               # users, nodes, hosts, billing, violations
│   ├── keyboards/              # inline keyboards
│   ├── services/               # webhook intake, reports, health checks
│   └── utils/                  # i18n, formatting, push
├── shared/                     # code shared by the bot and the web panel
│   ├── database.py             # PostgreSQL access
│   ├── api_client.py           # Remnawave panel API client
│   ├── config_service.py       # settings without a restart
│   ├── sync.py                 # panel to database sync
│   ├── analyzers/              # violation analyzers
│   ├── push_service.py         # push to the mobile app
│   └── metrics.py              # Prometheus metrics
├── web/
│   ├── frontend/               # React, TypeScript, Tailwind, shadcn/ui
│   ├── backend/                # FastAPI: RBAC, analytics, plugins, mail
│   └── cabinet/                # client cabinet (Bedolaga)
├── node-agent/                 # agent for nodes
├── monitoring/                 # Prometheus config and alert rules
├── alembic/                    # database migrations
├── locales/                    # translations (ru, en)
├── docs/                       # sources of this site
└── docker-compose.yml          # plus monitoring, collector and redis profiles
```

## Where to look

| Task | Where |
|------|-------|
| Add a setting to the interface | `shared/config_service.py` — it shows up by itself |
| Change Xray log parsing | `node-agent/src/collectors/xray_log.py` |
| Change violation detection | `shared/analyzers/` |
| Add a panel endpoint | `web/backend/api/v2/` |
| Add a metric | `web/backend/core/metrics.py` |
| Translate the interface | `locales/` and `web/frontend/src/locales/` |
