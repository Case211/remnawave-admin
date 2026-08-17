# Переменные окружения

Обязательных немного — всё остальное имеет разумные значения по умолчанию. Большинство настроек меняется прямо в интерфейсе панели без перезапуска; `.env` для них — начальное значение. Полный разбор того, что настраивается из интерфейса, — в [Настройках панели](/reference/settings).

Приоритет такой: **база данных → `.env` → значения по умолчанию**. То есть однажды изменённая в интерфейсе настройка перестаёт зависеть от `.env`.

## Основные

| Переменная | Обяз. | По умолчанию | Что задаёт |
|------------|-------|--------------|------------|
| `BOT_TOKEN` | да | — | токен бота из [@BotFather](https://t.me/BotFather) |
| `API_BASE_URL` | да | — | адрес API панели Remnawave |
| `API_TOKEN` | да | — | токен доступа к API панели |
| `ADMINS` | да | — | Telegram ID администраторов через запятую |
| `DEFAULT_LOCALE` | — | `ru` | язык интерфейса: `ru` или `en` |
| `LOG_LEVEL` | — | `INFO` | уровень логирования |
| `BOT_API_ROOT` | — | `https://api.telegram.org` | свой сервер Bot API |
| `BOT_PROXY_URL` | — | — | прокси до Telegram: `socks5://`, `socks4://`, `http://`, можно с логином и паролем. Схемы `socks5h://` и `https://` не поддерживаются |
| `PANEL_API_KEY` | — | — | дополнительный ключ, если панель закрыта им |

## База данных

| Переменная | Обяз. | По умолчанию | Что задаёт |
|------------|-------|--------------|------------|
| `POSTGRES_USER` | да | — | пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | да | — | его пароль |
| `POSTGRES_DB` | да | — | имя базы |
| `DATABASE_URL` | да | — | строка подключения целиком |
| `DB_POOL_MIN_SIZE` | — | `2` | нижняя граница пула соединений |
| `DB_POOL_MAX_SIZE` | — | `10` | верхняя граница пула |
| `SYNC_INTERVAL_SECONDS` | — | `300` | как часто синхронизироваться с панелью |

::: warning Три места, где легко разъехаться
Пароль в `DATABASE_URL` обязан совпадать с `POSTGRES_PASSWORD`. Это самая частая причина ошибки подключения к базе после установки.
:::

## Веб-панель

| Переменная | Обяз. | По умолчанию | Что задаёт |
|------------|-------|--------------|------------|
| `WEB_SECRET_KEY` | да | — | ключ подписи сессий, минимум 32 символа |
| `TELEGRAM_BOT_USERNAME` | да | — | username бота без `@`, нужен для входа через Telegram |
| `WEB_CORS_ORIGINS` | — | — | домены, которым разрешено обращаться к API |
| `WEB_JWT_EXPIRE_MINUTES` | — | `30` | время жизни access-токена |
| `WEB_JWT_REFRESH_HOURS` | — | `6` | время жизни refresh-токена |
| `WEB_BACKEND_PORT` | — | `8081` | порт бэкенда |
| `WEB_FRONTEND_PORT` | — | `3000` | порт фронтенда |
| `WEB_ALLOWED_IPS` | — | — | белый список адресов и сетей CIDR |
| `WEB_TRUSTED_PROXIES` | — | — | каким прокси верить в заголовках `X-Forwarded-For` |
| `WEB_SECRET_PATH` | — | — | секретный префикс адреса панели |
| `WEB_ADMIN_LOGIN` | — | — | запасной логин администратора |
| `WEB_ADMIN_PASSWORD` | — | — | запасной пароль |
| `APP_MODE` | — | `full` | `api` — вынести коллектор в отдельный контейнер |
| `REDIS_URL` | — | — | общий кэш и лимиты для нескольких экземпляров |
| `INTERNAL_API_SECRET` | — | — | ключ внутренних вызовов между ботом и бэкендом |
| `INTERNAL_API_BACKEND_URL` | — | `http://web-backend:8081` | адрес бэкенда для этих вызовов |

## Внешний API

| Переменная | По умолчанию | Что задаёт |
|------------|--------------|------------|
| `EXTERNAL_API_ENABLED` | `false` | включить [API v3](/reference/api) |
| `EXTERNAL_API_DOCS` | `false` | отдавать для него Swagger UI |

## Webhook от панели

| Переменная | По умолчанию | Что задаёт |
|------------|--------------|------------|
| `WEBHOOK_PORT` | `8080` | порт приёма |
| `WEBHOOK_SECRET` | — | ключ проверки подписи, тот же, что в панели |

Подробности — [Webhook от панели](/guide/webhook-setup).

## Уведомления

| Переменная | Что задаёт |
|------------|------------|
| `NOTIFICATIONS_CHAT_ID` | чат или канал для уведомлений |
| `NOTIFICATIONS_TOPIC_ID` | общий топик, если для события не задан свой |
| `NOTIFICATIONS_TOPIC_USERS` | пользователи |
| `NOTIFICATIONS_TOPIC_NODES` | ноды |
| `NOTIFICATIONS_TOPIC_SERVICE` | сервисные события |
| `NOTIFICATIONS_TOPIC_HWID` | устройства |
| `NOTIFICATIONS_TOPIC_CRM` | биллинг |
| `NOTIFICATIONS_TOPIC_FINANCE` | финансы |
| `NOTIFICATIONS_TOPIC_ERRORS` | ошибки |
| `NOTIFICATIONS_TOPIC_VIOLATIONS` | нарушения |

## GeoIP (MaxMind GeoLite2)

| Переменная | По умолчанию | Что задаёт |
|------------|--------------|------------|
| `MAXMIND_LICENSE_KEY` | — | ключ MaxMind; если задан, базы скачиваются и обновляются сами |
| `MAXMIND_CITY_DB` | `/app/geoip/GeoLite2-City.mmdb` | путь к базе городов |
| `MAXMIND_ASN_DB` | `/app/geoip/GeoLite2-ASN.mmdb` | путь к базе ASN |

Без MaxMind панель ходит в ip-api.com — бесплатно, но около тысячи запросов в сутки. С локальной базой поиск мгновенный и без лимитов.

Ключ берётся так: регистрация на [maxmind.com](https://www.maxmind.com/en/geolite2/signup) → Account → Manage License Keys → Generate New License Key. Базы скачаются при старте и будут обновляться раз в сутки.

## Почтовый сервер

| Переменная | По умолчанию | Что задаёт |
|------------|--------------|------------|
| `MAIL_SERVER_ENABLED` | `false` | включить [почтовый сервер](/guide/mail) |
| `MAIL_INBOUND_PORT` | `2525` | порт приёма писем |
| `MAIL_SUBMISSION_PORT` | `587` | порт submission |
| `MAIL_SERVER_HOSTNAME` | `0.0.0.0` | на каком адресе слушать |
| `MAIL_TLS_CERT_PATH` | — | сертификат для STARTTLS |
| `MAIL_TLS_KEY_PATH` | — | ключ к нему |

## Мониторинг

| Переменная | По умолчанию | Что задаёт |
|------------|--------------|------------|
| `METRICS_AUTH_TOKEN` | — | закрывает `/metrics` Bearer-токеном |
| `PROMETHEUS_PORT` | `9090` | порт встроенного Prometheus |
| `PROMETHEUS_RETENTION` | `30d` | сколько хранить метрики |

## Bedolaga Bot

| Переменная | Что задаёт |
|------------|------------|
| `BEDOLAGA_API_URL` | адрес API Bedolaga Bot |
| `BEDOLAGA_API_TOKEN` | токен доступа к нему |

## Node Agent

Переменные агента задаются на самой ноде и описаны отдельно: [Node Agent](/guide/node-agent#переменные-агента) и [Детект торрентов](/guide/torrents#тонкая-настройка).
