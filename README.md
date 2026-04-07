# 🤖 Remnawave Admin Web + Bot

<div align="center">

<img src="remnawave-admin.webp" alt="Remnawave Admin" width="100%" />

**Telegram-бот и веб-панель для управления панелью Remnawave**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.11+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[English](README_EN.md) | [Русский](README.md)

</div>

---

## ✨ Возможности

### 🤖 Telegram-бот
- **👥 Пользователи** — поиск, создание, редактирование, HWID устройства, статистика, массовые операции
- **🛰 Ноды** — просмотр, включение/выключение, перезапуск, мониторинг трафика, статистика
- **🖥 Хосты** — просмотр, создание, редактирование, массовые операции
- **🧰 Ресурсы** — шаблоны подписок, сниппеты, API токены, конфиги
- **💰 Биллинг** — история платежей, провайдеры, биллинг-ноды
- **📊 Система** — здоровье системы, статистика, трафик

### 🌐 Веб-панель
- 📊 Дашборд с обзором системы, графиками нарушений и очередью коллектора
- 👥 Управление пользователями, нодами, хостами
- 🛡 Просмотр нарушений с IP Lookup, inline-действиями (блокировка, сброс трафика, whitelist)
- 🗺 Интерактивная гео-карта с детализацией по пользователям и городам
- 📈 Расширенная аналитика — топ юзеров, тренды, трафик по нодам, P2P/Torrent детекция
- ⚙️ Настройки с автосохранением (приоритет: БД > .env > по умолчанию)
- 🔐 Авторизация: Telegram Login Widget, пароль, 2FA (TOTP) + RBAC (роли и права)
- 🤖 Автоматизации — конструктор правил с шаблонами, расписанием и логами выполнения
- 🚫 Управление заблокированными IP — bulk-импорт/экспорт, срок действия
- 🖥 Терминал — удалённое выполнение команд на нодах через xterm.js
- 📜 Каталог скриптов — выполнение на нодах через Agent v2 WebSocket
- 🗄 Бэкапы базы данных — создание, восстановление, управление из UI
- 📋 Аудит-лог — полная история действий администраторов
- 🔑 API-ключи — генерация долгоживущих токенов для внешних интеграций
- 🎨 6 тёмных тем + 1 светлая, адаптивный дизайн
- 🌍 Полная интернационализация (русский / английский)
- 🔔 Система уведомлений с настраиваемой маршрутизацией по топикам

### 🛡 Anti-Abuse система
- 🔍 Многофакторный анализ подключений (временной, географический, ASN, профиль, устройства)
- 🌍 Детекция «невозможных путешествий», распознавание 60+ российских агломераций
- ⚡ Автоматические действия по порогам скоринга
- 🔥 Мониторинг скорости потребления трафика с настраиваемыми порогами
- 🧲 P2P/Torrent детекция и аналитика (интеграция с torrent-blocker)
- 📡 Интеграция с [Node Agent](node-agent/README.md) для сбора данных

### 📧 Встроенный почтовый сервер
- 📤 Прямая MX-доставка без внешних SMTP-провайдеров
- 🔏 DKIM-подпись (RSA-2048) + автоматическая проверка SPF/DKIM/DMARC
- 📥 Приём входящих писем (встроенный SMTP-сервер)
- 📊 Очередь отправки с повторами, rate limiting и мониторингом
- ✍️ Встроенный compose-редактор + inbox-просмотрщик

### 💰 Интеграция с Bedolaga Bot
- 📊 Дашборд с метриками CRM
- 👥 Управление клиентами и подписками
- 🎫 Промокоды и реферальная система
- 📈 Маркетинговая аналитика

### 🔧 Дополнительно
- 🏗 Поддержка ARM64 (aarch64) — Docker-образы для `linux/amd64` и `linux/arm64`
- ⚙️ Динамические настройки без перезапуска (Telegram и веб-панель)
- 🔔 Webhook-уведомления с маршрутизацией по топикам
- 📝 Динамическое логирование: смена уровня, ротация, настройка размера файлов
- 🌍 Русский и английский языки
- 🗄 PostgreSQL с graceful degradation (работает и без БД)
- 🧪 Тестовая инфраструктура: Playwright E2E, CI/CD workflows
- 🔌 Внешний API (`/api/v3`) для сторонних интеграций

---

## 💻 Системные требования

| Параметр | До 1 000 юзеров | 1 000–5 000 | 5 000–20 000 | 20 000+ |
|----------|----------------|-------------|--------------|---------|
| **CPU** | 1 vCPU | 2 vCPU | 4 vCPU | 4–8 vCPU |
| **RAM** | 1 GB | 2 GB | 4 GB | 8+ GB |
| **Диск** | 10 GB SSD | 20 GB SSD | 40 GB NVMe | 80+ GB NVMe |
| **PostgreSQL** | По умолч. | Tuning рекомендуется | Tuning обязателен | Dedicated DB |

> **Примечания:**
> - Указаны требования для бота + веб-панели + PostgreSQL на одном сервере
> - При 5 000+ юзерах рекомендуется включить MaxMind GeoIP (локальная БД вместо ip-api.com)
> - При 20 000+ юзерах рекомендуется вынести PostgreSQL на отдельный сервер
> - Node Agent на каждой ноде потребляет ~50 MB RAM

---

## 🚀 Быстрый старт

### 📋 Что понадобится перед началом

| Что | Где взять |
|-----|-----------|
| 🐳 **Docker** + **Docker Compose** | [docker.com](https://www.docker.com/) |
| 🤖 **Токен Telegram-бота** | Создайте бота у [@BotFather](https://t.me/BotFather) → `/newbot` → скопируйте токен |
| 🔑 **API-токен Remnawave** | Панель Remnawave → Настройки → API → скопируйте токен |
| 🆔 **Ваш Telegram ID** | Напишите [@userinfobot](https://t.me/userinfobot) → он пришлёт ваш числовой ID |
| 🆔 **2 A-записи** | Запись для Webhook (Bot) + Запись для Web |

---

### Шаг 1️⃣ — Клонируйте репозиторий

```bash
git clone https://github.com/case211/remnawave-admin.git
cd remnawave-admin
```

### Шаг 2️⃣ — Создайте файл `.env`

```bash
cp .env.example .env
nano .env          # или vim, или любой редактор
```

Заполните **обязательные** поля (без них бот не запустится):

```env
# 🤖 Токен бота (из @BotFather)
BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVWxyz

# 🌐 Адрес API Remnawave
# Если бот и панель в одной Docker-сети:
API_BASE_URL=http://remnawave:3000
# Если панель на другом сервере:
# API_BASE_URL=https://panel.yourdomain.com

# 🔑 API-токен из панели Remnawave
API_TOKEN=ваш_токен_из_панели

# 👤 Telegram ID администраторов (через запятую)
ADMINS=123456789
```

Настройте **базу данных** (PostgreSQL поднимается автоматически в Docker):

```env
# 🗄 PostgreSQL — придумайте пароль
POSTGRES_USER=remnawave
POSTGRES_PASSWORD=придумайте_надёжный_пароль
POSTGRES_DB=remnawave_bot

# ⚠️ Пароль тут должен совпадать с POSTGRES_PASSWORD выше!
DATABASE_URL=postgresql://remnawave:придумайте_надёжный_пароль@remnawave-admin-db:5432/remnawave_bot
```

### Шаг 3️⃣ — Запустите бота

```bash
# Создайте Docker-сеть (один раз)
docker network create remnawave-network

# Скачайте образы и запустите
docker compose up -d

# Проверьте, что всё работает
docker compose logs -f bot
```

✅ **Готово!** Откройте бота в Telegram и отправьте `/start`.

---

### Шаг 4️⃣ — Веб-панель

Добавьте в `.env`:

```env
# 🌐 Веб-панель
# Секретный ключ для JWT-сессий (сгенерируйте: openssl rand -hex 32)
WEB_SECRET_KEY=сгенерированный_ключ_минимум_32_символа

# Username бота (без @) — нужен для Telegram Login Widget
TELEGRAM_BOT_USERNAME=your_bot_username

# Домен веб-панели (для CORS)
WEB_CORS_ORIGINS=https://admin.yourdomain.com

# (Опционально) Секретный путь — панель будет доступна по /ваш-путь/
# WEB_SECRET_PATH=my-secret-path
```

> 💡 **Авторизация**: При первом входе создайте аккаунт администратора. Поддерживается вход через Telegram Login Widget и по паролю. Можно включить 2FA (TOTP). Система RBAC позволяет создавать роли с гранулярными правами доступа.

Веб-панель запускается вместе с ботом:

```bash
docker compose up -d
```

Порты: **frontend :3000**, **backend :8081**.

> 📖 Подробнее о настройке домена и реверс-прокси: [web/README.md](web/README.md)

---

### Шаг 5️⃣ — Webhook-уведомления (опционально)

Чтобы бот присылал уведомления при изменениях в панели — добавьте в `.env`:

```env
# 🔔 Чат для уведомлений
NOTIFICATIONS_CHAT_ID=-1001234567890    # ID вашей группы/канала

# 🔐 Секрет для webhook (сгенерируйте: openssl rand -hex 64)
WEBHOOK_SECRET=ваш_секретный_ключ
```

Затем в **панели Remnawave** укажите:
- **WEBHOOK_URL** = `http://bot:8080/webhook` (если в одной Docker-сети)
- **WEBHOOK_SECRET_HEADER** = тот же ключ, что и `WEBHOOK_SECRET` в `.env` бота

> 📖 Подробная инструкция с примерами nginx/Caddy: [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

---

### Шаг 6️⃣ — Уведомления по топикам (опционально)

Если у вас группа-форум в Telegram, можно разделить уведомления по топикам:

```env
NOTIFICATIONS_TOPIC_USERS=456       # 👥 События пользователей
NOTIFICATIONS_TOPIC_NODES=789       # 🛰 События нод
NOTIFICATIONS_TOPIC_SERVICE=101     # ⚙️ Сервисные события
NOTIFICATIONS_TOPIC_HWID=102        # 💻 HWID устройства
NOTIFICATIONS_TOPIC_CRM=103         # 💰 Биллинг
NOTIFICATIONS_TOPIC_ERRORS=104      # ❌ Ошибки
NOTIFICATIONS_TOPIC_VIOLATIONS=105  # 🛡 Нарушения
```

> 💡 Если топик не указан — уведомление уйдёт в `NOTIFICATIONS_TOPIC_ID` (общий fallback).

---

### Шаг 7️⃣ — Встроенный почтовый сервер (опционально)

Веб-панель включает встроенный почтовый сервер с DKIM-подписью, прямой MX-доставкой и приёмом входящих писем — без внешних SMTP-провайдеров.

#### Включение

Перейдите в **Settings** в веб-панели → секция **"Почтовый сервер"** → включите **"Почтовый сервер включён"**. Перезапустите контейнер.

Или через `.env`:

```env
MAIL_SERVER_ENABLED=true
MAIL_INBOUND_PORT=2525          # Порт приёма входящих (по умолчанию 2525)
MAIL_SERVER_HOSTNAME=0.0.0.0    # IP для SMTP-сервера
```

> 💡 Все настройки можно менять из веб-интерфейса (Settings), `.env` — как fallback.

#### Добавление домена

1. Перейдите в **Mail Server** → вкладка **Domains** → **Add Domain**
2. Введите ваш домен (например `example.com`)
3. Система автоматически сгенерирует DKIM-ключи (RSA-2048)

#### Настройка DNS

Нажмите **"DNS Records"** у домена — система покажет 4 записи для добавления у DNS-провайдера:

| Тип | Хост | Назначение |
|-----|------|-----------|
| **MX** | `example.com` | Направляет входящую почту на ваш сервер |
| **TXT** | `example.com` | SPF — разрешает вашему IP отправлять почту |
| **TXT** | `rw._domainkey.example.com` | DKIM — подпись для верификации |
| **TXT** | `_dmarc.example.com` | DMARC — политика для неверифицированных писем |

Значения можно скопировать из интерфейса. После добавления нажмите **"Check DNS"** для проверки.

#### Сетевые порты

```
Порт 25  — исходящий (для прямой доставки на MX-серверы получателей)
Порт 2525 — входящий (приём писем, настраивается)
```

В `docker-compose.yml` добавьте:

```yaml
ports:
  - "25:2525"    # входящая почта
```

> ⚠️ Многие облачные хостинги (AWS, GCP, Azure) блокируют порт 25. Используйте VPS с открытым портом 25 (Hetzner, OVH, DigitalOcean).

#### За reverse proxy (nginx, Caddy, Traefik)

Веб-панель (HTTP API) проходит через reverse proxy как обычно — эндпоинты `/api/v2/mailserver/*` работают без дополнительных настроек.

**SMTP — отдельный протокол**, он **не может** проксироваться через HTTP reverse proxy. Два варианта:

**Вариант 1 — Прямой проброс порта (рекомендуется):**

```yaml
# docker-compose.yml — SMTP-порт минует proxy
services:
  remnawave-admin:
    ports:
      - "25:2525"    # входящая почта напрямую
```

**Вариант 2 — nginx stream proxy (TCP):**

```nginx
# Отдельный блок stream {}, НЕ внутри http {}
stream {
    server {
        listen 25;
        proxy_pass remnawave-admin:2525;
    }
}
```

**Вариант 3 — Caddy L4 (TCP proxy):**

Для TCP-проксирования Caddy нужен плагин [caddy-l4](https://github.com/mholt/caddy-l4):

```json
{
  "apps": {
    "layer4": {
      "servers": {
        "smtp": {
          "listen": [":25"],
          "routes": [{
            "handle": [{
              "handler": "proxy",
              "upstreams": [{"dial": ["remnawave-admin:2525"]}]
            }]
          }]
        }
      }
    }
  }
}
```

Или через Caddyfile (с `caddy-l4`):

```caddyfile
:25 {
    route {
        proxy remnawave-admin:2525
    }
}
```

**Схема подключения:**

```
Интернет
  │
  ├── :443 (HTTPS) → nginx/Caddy → :8081 (веб-панель API)
  │                              → :3000 (веб-панель frontend)
  │
  └── :25  (SMTP)  → напрямую   → :2525 (встроенный SMTP-сервер)
```

**Важно:**
- MX, SPF, PTR записи должны указывать на **публичный IP** вашего сервера
- PTR-запись (reverse DNS) настраивается у хостера — улучшает доставляемость
- Если proxy и приложение на одной машине — просто пробросьте порт 25/2525 в docker-compose мимо nginx

#### Проверка

1. Активируйте домен (переключатель в карточке домена)
2. Перейдите на вкладку **Compose** → выберите домен → введите адрес → **Send Test**
3. Проверьте вкладку **Queue** — статус должен стать `sent`

> 📬 Если настроен активный домен, система уведомлений автоматически использует встроенный сервер (fallback на SMTP relay).

---

### Шаг 8️⃣ — Node Agent (опционально)

Для работы Anti-Abuse системы необходимо установить **Node Agent** на каждую ноду. Агент собирает данные о подключениях из логов Xray и отправляет их в Web Backend. Также поддерживает Command Channel (удалённый терминал и выполнение скриптов).

**Быстрая установка (одна команда):**

1. Откройте веб-панель → **Ноды** → выберите ноду → **Токен агента** → **Установить агент**
2. Скопируйте готовую команду и выполните на ноде:

```bash
curl -sSL https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/install.sh | bash -s -- --uuid UUID --url URL --token TOKEN
```

Скрипт автоматически создаст директорию, скачает `docker-compose.yml`, сгенерирует `.env` и запустит агент.

**Ручная установка:**

```bash
mkdir -p /opt/remnawave-node-agent && cd /opt/remnawave-node-agent
curl -sLO https://raw.githubusercontent.com/Case211/remnawave-admin/main/node-agent/docker-compose.yml
nano .env  # Вставьте переменные из веб-панели
docker compose up -d
```

> 📖 Подробная документация: [node-agent/README.md](node-agent/README.md) — режимы парсинга, Command Channel (терминал/скрипты), миграция, troubleshooting.

---

## 💻 Локальная разработка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Отредактируйте .env: API_BASE_URL=https://ваш-домен-панели.com
python -m src.main
```

---

## ⚙️ Справочник переменных окружения

### Основные

| Переменная | Обяз. | По умолч. | Описание |
|------------|-------|-----------|----------|
| `BOT_TOKEN` | ✅ | — | Токен Telegram-бота |
| `API_BASE_URL` | ✅ | — | URL API Remnawave |
| `API_TOKEN` | ✅ | — | Токен аутентификации API |
| `ADMINS` | ✅ | — | ID администраторов через запятую |
| `DEFAULT_LOCALE` | — | `ru` | Язык (`ru` / `en`) |
| `LOG_LEVEL` | — | `INFO` | Уровень логирования |

### 🗄 База данных

| Переменная | Обяз. | По умолч. | Описание |
|------------|-------|-----------|----------|
| `POSTGRES_USER` | ✅ | — | Пользователь PostgreSQL |
| `POSTGRES_PASSWORD` | ✅ | — | Пароль PostgreSQL |
| `POSTGRES_DB` | ✅ | — | Имя базы данных |
| `DATABASE_URL` | ✅ | — | URL подключения к PostgreSQL |
| `SYNC_INTERVAL_SECONDS` | — | `300` | Интервал синхронизации с API (сек) |

### 🔔 Уведомления

| Переменная | Описание |
|------------|----------|
| `NOTIFICATIONS_CHAT_ID` | ID группы/канала |
| `NOTIFICATIONS_TOPIC_ID` | Общий топик (fallback) |
| `NOTIFICATIONS_TOPIC_USERS` | Топик для пользователей |
| `NOTIFICATIONS_TOPIC_NODES` | Топик для нод |
| `NOTIFICATIONS_TOPIC_SERVICE` | Сервисные уведомления |
| `NOTIFICATIONS_TOPIC_HWID` | HWID уведомления |
| `NOTIFICATIONS_TOPIC_CRM` | Биллинг уведомления |
| `NOTIFICATIONS_TOPIC_ERRORS` | Ошибки |
| `NOTIFICATIONS_TOPIC_VIOLATIONS` | Нарушения |

### 🔗 Webhook

| Переменная | По умолч. | Описание |
|------------|-----------|----------|
| `WEBHOOK_SECRET` | — | Ключ проверки webhook (HMAC-SHA256) |
| `WEBHOOK_PORT` | `8080` | Порт webhook сервера |

### 🌍 GeoIP (MaxMind GeoLite2)

| Переменная | Обяз. | По умолч. | Описание |
|------------|-------|-----------|----------|
| `MAXMIND_LICENSE_KEY` | — | — | Лицензионный ключ MaxMind (бесплатно). Если указан — базы скачиваются автоматически |
| `MAXMIND_CITY_DB` | — | `/app/geoip/GeoLite2-City.mmdb` | Путь к базе GeoLite2-City |
| `MAXMIND_ASN_DB` | — | `/app/geoip/GeoLite2-ASN.mmdb` | Путь к базе GeoLite2-ASN |

> **Без MaxMind** — используется ip-api.com (бесплатный, но ограничен ~1000 запросов/день).
> **С MaxMind** — локальная база, мгновенные lookup'ы, без лимитов.
>
> Как подключить:
> 1. Зарегистрируйтесь на [maxmind.com/en/geolite2/signup](https://www.maxmind.com/en/geolite2/signup) (бесплатно)
> 2. Account → Manage License Keys → Generate New License Key
> 3. Добавьте в `.env`: `MAXMIND_LICENSE_KEY=ваш_ключ`
> 4. Базы скачаются автоматически при старте и обновляются каждые 24 часа

### 🌐 Веб-панель

| Переменная | Обяз.* | По умолч. | Описание |
|------------|--------|-----------|----------|
| `WEB_SECRET_KEY` | ✅ | — | Секретный ключ JWT |
| `TELEGRAM_BOT_USERNAME` | ✅ | — | Username бота (без @) |
| `WEB_CORS_ORIGINS` | — | — | Разрешённые домены (CORS) |
| `WEB_JWT_EXPIRE_MINUTES` | — | `30` | Время жизни access token (мин) |
| `WEB_JWT_REFRESH_HOURS` | — | `6` | Время жизни refresh token (ч) |
| `WEB_BACKEND_PORT` | — | `8081` | Порт бэкенда |
| `WEB_FRONTEND_PORT` | — | `3000` | Порт фронтенда |
| `WEB_ALLOWED_IPS` | — | — | Белый список IP (CIDR) |
| `WEB_SECRET_PATH` | — | — | Секретный префикс URL панели |
| `WEB_ADMIN_LOGIN` | — | — | Логин администратора (fallback) |
| `WEB_ADMIN_PASSWORD` | — | — | Пароль администратора (fallback) |
| `EXTERNAL_API_ENABLED` | — | `false` | Включить внешний API (`/api/v3`) |
| `EXTERNAL_API_DOCS` | — | `false` | Swagger UI для внешнего API |

### 💰 Bedolaga Bot (опционально)

| Переменная | По умолч. | Описание |
|------------|-----------|----------|
| `BEDOLAGA_API_URL` | — | URL API Bedolaga Bot |
| `BEDOLAGA_API_TOKEN` | — | Токен аутентификации Bedolaga |

*\* Обязательно для работы веб-панели*

### 📧 Почтовый сервер

| Переменная | По умолч. | Описание |
|------------|-----------|----------|
| `MAIL_SERVER_ENABLED` | `false` | Включить встроенный почтовый сервер |
| `MAIL_INBOUND_PORT` | `2525` | Порт входящего SMTP-сервера |
| `MAIL_SUBMISSION_PORT` | `587` | Порт SMTP submission |
| `MAIL_SERVER_HOSTNAME` | `0.0.0.0` | IP для SMTP-сервера |

> 💡 Эти переменные — fallback. Настройки можно менять из веб-панели (Settings → Почтовый сервер).

---

## 🤖 Команды бота

| Команда | Описание |
|---------|----------|
| `/start` | Главное меню |
| `/help` | Справка |
| `/health` | Статус системы |
| `/stats` | Статистика панели |
| `/bandwidth` | Статистика трафика |
| `/config` | Динамические настройки |
| `/user <username\|id>` | Информация о пользователе |
| `/node <uuid>` | Информация о ноде |
| `/host <uuid>` | Информация о хосте |

---

## 📝 Логирование

Двухуровневая система: **файлы** (полная история) и **консоль** (только WARNING+).

| Файл | Уровень | Содержимое |
|------|---------|------------|
| `adminbot_INFO.log` | INFO+ | Всё: API-вызовы, синхронизация, действия |
| `adminbot_WARNING.log` | WARNING+ | Проблемы: таймауты, ошибки |
| `web_INFO.log` | INFO+ | Логи веб-бэкенда |
| `web_WARNING.log` | WARNING+ | Проблемы веб-бэкенда |

Ротация: 50 MB на файл, 5 бэкапов (gzip). Файлы в `./logs/`.

```bash
docker compose logs -f bot                    # Live-логи
tail -100 ./logs/adminbot_INFO.log            # Последние 100 строк
```

---

## 📂 Структура проекта

```
remnawave-admin/
├── src/                        # Telegram-бот
│   ├── handlers/               # Обработчики (users, nodes, hosts, billing, violations, blocked_ips, ...)
│   ├── keyboards/              # Inline-клавиатуры
│   ├── services/               # Webhook, report scheduler, health check
│   └── utils/                  # i18n, логирование, форматирование
├── shared/                     # Общий код (бот + веб)
│   ├── database.py             # AsyncPG, все DB-операции
│   ├── api_client.py           # HTTP-клиент Panel API
│   ├── config_service.py       # Динамическая конфигурация
│   ├── sync.py                 # Фоновая синхронизация Panel → DB
│   ├── violation_detector.py   # Многофакторный анализ нарушений
│   └── connection_monitor.py   # Мониторинг подключений
├── web/                        # Веб-панель
│   ├── frontend/               # React + TypeScript + Tailwind + shadcn/ui
│   └── backend/                # FastAPI бэкенд (RBAC, аналитика, автоматизации)
├── node-agent/                 # Агент сбора данных с нод (Command Channel, скрипты)
├── alembic/                    # Миграции БД
├── locales/                    # Локализация (ru, en)
└── docker-compose.yml          # Docker Compose (бот + веб-панель + БД)
```

---

## 📚 Документация

| Документ | Описание |
|----------|----------|
| [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md) | Настройка webhook |
| [web/README.md](web/README.md) | Веб-панель: настройка, реверс-прокси, API |
| [web/SECURITY_AUDIT.md](web/SECURITY_AUDIT.md) | Аудит безопасности веб-панели |
| [node-agent/README.md](node-agent/README.md) | Node Agent: установка, настройка, troubleshooting |

---

## 🔧 Решение проблем

### Бот не отвечает

```bash
docker compose ps                    # Статус контейнеров
docker compose logs -f bot           # Логи
docker compose config                # Проверка конфигурации
```

### Проблемы с API

- Проверьте `API_BASE_URL` и `API_TOKEN`
- Docker-сеть существует: `docker network ls | grep remnawave-network`

### Отказано в доступе

- Telegram ID в `ADMINS`? Проверьте через [@userinfobot](https://t.me/userinfobot)

### Webhook не работает

- `WEBHOOK_SECRET` совпадает с `WEBHOOK_SECRET_HEADER` в панели?
- URL webhook доступен из панели?
- Подробнее: [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

### Потерян доступ к веб-панели

Если вы забыли пароль, а Telegram-вход не работает — используйте CLI-утилиту `scripts/admin_cli.py`.

**Сбросить пароль** (будет сгенерирован новый):

```bash
docker exec -it <container_name> python3 scripts/admin_cli.py reset-password
```

Для конкретного пользователя или с указанием пароля:

```bash
docker exec -it <container_name> python3 scripts/admin_cli.py reset-password --username myadmin
docker exec -it <container_name> python3 scripts/admin_cli.py reset-password --password 'MyNew$ecure1'
```

**Создать нового суперадмина:**

```bash
docker exec -it <container_name> python3 scripts/admin_cli.py create-superadmin --username newadmin
```

**Посмотреть список всех администраторов:**

```bash
docker exec -it <container_name> python3 scripts/admin_cli.py list-admins
```

> Утилита подключается напрямую к PostgreSQL (читает `DATABASE_URL` из `.env`), не требует запущенной веб-панели.

---

## 🤝 Вклад в проект

1. Fork репозитория
2. Создайте ветку: `git checkout -b feature/amazing-feature`
3. Commit и push
4. Откройте Pull Request

---

## 📄 Лицензия

MIT License — см. [LICENSE](LICENSE).

---

## 💖 Поддержка

- [Issues на GitHub](https://github.com/case211/remnawave-admin/issues)
- [Telegram-чат](https://t.me/remnawave_admin)

Поддержать автора:
- TON: `UQDDe-jyFTbQsPHqyojdFeO1_m7uPF-q1w0g_MfbSOd3l1sC`
- USDT TRC20: `TGyHJj2PsYSUwkBbWdc7BFfsAxsE6SGGJP`
- BTC: `1J6Zz7XcrpFkchwFmuU5WTFYTxziBdSwRz`

---

<div align="center">

Сделано с ❤️ для сообщества Remnawave

</div>
