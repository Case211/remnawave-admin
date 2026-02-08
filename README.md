# Remnawave Admin Bot

<div align="center">

**Telegram-бот и веб-панель для управления панелью Remnawave**

[![Docker](https://img.shields.io/badge/Docker-Ready-blue)](https://www.docker.com/)
[![Python](https://img.shields.io/badge/Python-3.12+-green)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

[English](README_EN.md) | [Русский](README.md)

</div>

---

## Возможности

### Telegram-бот
- **Пользователи** — поиск, создание, редактирование, HWID устройства, статистика, массовые операции
- **Ноды** — просмотр, включение/выключение, перезапуск, мониторинг трафика, статистика
- **Хосты** — просмотр, создание, редактирование, массовые операции
- **Ресурсы** — шаблоны подписок, сниппеты, API токены, конфиги
- **Биллинг** — история платежей, провайдеры, биллинг-ноды
- **Система** — здоровье системы, статистика, трафик

### Веб-панель
- Дашборд с обзором системы и графиками нарушений
- Управление пользователями, нодами, хостами
- Просмотр нарушений с IP Lookup (провайдер, город, тип подключения)
- Настройки с автосохранением (приоритет: БД > .env > по умолчанию)
- Авторизация через Telegram Login Widget + JWT
- Тёмная тема, адаптивный дизайн

### Anti-Abuse система
- Многофакторный анализ подключений (временной, географический, ASN, профиль, устройства)
- Детекция «невозможных путешествий», распознавание 60+ российских агломераций
- Автоматические действия по порогам скоринга
- Интеграция с [Node Agent](node-agent/README.md) для сбора данных

### Дополнительно
- Динамические настройки без перезапуска (Telegram и веб-панель)
- Webhook-уведомления с маршрутизацией по топикам
- Русский и английский языки
- PostgreSQL с graceful degradation (работает и без БД)

---

## Быстрый старт

### Требования

- **Docker** и **Docker Compose** (рекомендуется) или **Python 3.12+**
- Токен Telegram-бота от [@BotFather](https://t.me/BotFather)
- Токен доступа к API Remnawave

### 1. Клонируйте и настройте

```bash
git clone https://github.com/case211/remnawave-admin.git
cd remnawave-admin
cp .env.example .env
nano .env
```

**Обязательные переменные:**

```env
BOT_TOKEN=ваш_токен_telegram_бота
API_BASE_URL=http://remnawave:3000       # Docker-сеть
API_TOKEN=ваш_токен_api
ADMINS=123456789,987654321               # ID администраторов
```

**Опциональные (уведомления, webhook):**

```env
NOTIFICATIONS_CHAT_ID=-1001234567890
WEBHOOK_SECRET=ваш_секретный_ключ        # Совпадает с WEBHOOK_SECRET_HEADER в панели
WEBHOOK_PORT=8080
```

> Получите Telegram ID: [@userinfobot](https://t.me/userinfobot)

### 2. Запустите

```bash
docker network create remnawave-network

# Только бот
docker compose up -d

# Бот + веб-панель
docker compose --profile web up -d
```

### 3. Настройте webhook (опционально)

Подробная инструкция: [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md)

Кратко: в панели Remnawave укажите URL `http://bot:8080/webhook` и установите `WEBHOOK_SECRET_HEADER` равным `WEBHOOK_SECRET` бота.

---

## Локальная разработка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Отредактируйте .env: API_BASE_URL=https://ваш-домен-панели.com/api
python -m src.main
```

---

## Конфигурация

### Основные переменные окружения

| Переменная | Обяз. | По умолч. | Описание |
|------------|-------|-----------|----------|
| `BOT_TOKEN` | Да | — | Токен Telegram-бота |
| `API_BASE_URL` | Да | — | URL API Remnawave |
| `API_TOKEN` | Да | — | Токен аутентификации API |
| `ADMINS` | Да | — | ID администраторов через запятую |
| `DEFAULT_LOCALE` | — | `ru` | Язык (`ru` / `en`) |
| `LOG_LEVEL` | — | `INFO` | Уровень логирования |
| `DATABASE_URL` | — | — | URL подключения к PostgreSQL |
| `SYNC_INTERVAL_SECONDS` | — | `300` | Интервал синхронизации с API (сек) |

### Уведомления

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

### Webhook

| Переменная | По умолч. | Описание |
|------------|-----------|----------|
| `WEBHOOK_SECRET` | — | Ключ проверки webhook (HMAC-SHA256) |
| `WEBHOOK_PORT` | `8080` | Порт webhook сервера |

---

## Команды бота

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

## Логирование

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

## Структура проекта

```
remnawave-admin/
├── src/                        # Telegram-бот
│   ├── handlers/               # Обработчики (users, nodes, hosts, billing, ...)
│   ├── keyboards/              # Inline-клавиатуры
│   ├── services/               # API client, database, violation detector, webhook, ...
│   └── utils/                  # i18n, логирование, форматирование
├── web/                        # Веб-панель
│   ├── frontend/               # React + TypeScript + Tailwind
│   └── backend/                # FastAPI бэкенд
├── node-agent/                 # Агент сбора данных с нод
├── alembic/                    # Миграции БД
├── locales/                    # Локализация (ru, en)
└── docker-compose.yml          # Docker Compose (профили: bot, web)
```

---

## Документация

| Документ | Описание |
|----------|----------|
| [CHANGELOG.md](CHANGELOG.md) | История версий |
| [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md) | Настройка webhook |
| [docs/anti-abuse.md](docs/anti-abuse.md) | Anti-Abuse система, база ASN, классификация провайдеров |
| [web/README.md](web/README.md) | Веб-панель: настройка, реверс-прокси, API |
| [web/SECURITY_AUDIT.md](web/SECURITY_AUDIT.md) | Аудит безопасности веб-панели |
| [node-agent/README.md](node-agent/README.md) | Node Agent: установка, настройка, troubleshooting |

---

## Решение проблем

### Бот не отвечает

```bash
docker compose ps                    # Статус контейнеров
docker compose logs -f bot           # Логи (WARNING+)
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

---

## Вклад в проект

1. Fork репозитория
2. Создайте ветку: `git checkout -b feature/amazing-feature`
3. Commit и push
4. Откройте Pull Request

---

## Лицензия

MIT License — см. [LICENSE](LICENSE).

## Поддержка

- [Issues на GitHub](https://github.com/case211/remnawave-admin/issues)
- [Telegram-чат](https://t.me/remnawave_admin)

Поддержать автора:
- TON: `UQDDe-jyFTbQsPHqyojdFeO1_m7uPF-q1w0g_MfbSOd3l1sC`
- USDT TRC20: `TGyHJj2PsYSUwkBbWdc7BFfsAxsE6SGGJP`
- BTC: `bc1qusrj5rxd3kv6eepzpdn0muy6zsl3c24xunz2xn`
