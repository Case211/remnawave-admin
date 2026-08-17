# Установка

Минимальный рабочий набор — бот и веб-панель с общей базой. Почта, мониторинг и агент на нодах подключаются потом и по отдельности.

Перед началом проверьте [требования](/guide/requirements): понадобятся токен бота, API-токен Remnawave и ваш Telegram ID.

## 1. Клонировать репозиторий

```bash
git clone https://github.com/Case211/remnawave-admin.git
cd remnawave-admin
```

## 2. Заполнить `.env`

```bash
cp .env.example .env
nano .env
```

Без этих полей бот не поднимется:

```ini
# Токен из @BotFather
BOT_TOKEN=1234567890:ABCdefGHIjklmNOPqrstUVWxyz

# Адрес API панели Remnawave.
# В одной Docker-сети:
API_BASE_URL=http://remnawave:3000
# На другом сервере:
# API_BASE_URL=https://panel.example.com

API_TOKEN=токен_из_панели

# Telegram ID администраторов через запятую
ADMINS=123456789
```

База поднимается вместе с остальным, но пароль придумываете вы:

```ini
POSTGRES_USER=remnawave
POSTGRES_PASSWORD=надёжный_пароль
POSTGRES_DB=remnawave_bot

# Пароль здесь обязан совпадать с POSTGRES_PASSWORD выше
DATABASE_URL=postgresql://remnawave:надёжный_пароль@remnawave-admin-db:5432/remnawave_bot
```

Для веб-панели добавьте:

```ini
# Ключ подписи сессий: openssl rand -hex 32
WEB_SECRET_KEY=сгенерированный_ключ

# Username бота без @ — нужен для входа через Telegram
TELEGRAM_BOT_USERNAME=your_bot_username

# Домен панели, иначе браузер отобьёт запросы по CORS
WEB_CORS_ORIGINS=https://admin.example.com

# По желанию: панель откроется только по адресу /секретный-путь/
# WEB_SECRET_PATH=my-secret-path
```

Полный список — в [справочнике переменных](/reference/env).

## 3. Запустить

```bash
# Сеть создаётся один раз
docker network create remnawave-network

docker compose up -d
docker compose logs -f bot
```

Откройте бота в Telegram и отправьте `/start`. Веб-панель поднимается тем же compose: фронтенд на `:3000`, бэкенд на `:8081`.

Дальше поставьте перед ней [reverse proxy и разберитесь с доступом](/guide/web-panel) — наружу порты выставлять не нужно.

::: warning Первый вход
При первом входе создаётся аккаунт администратора. Если позже потеряете доступ — пароль сбрасывается [через CLI](/guide/troubleshooting#потерян-доступ-к-панели), без переустановки.
:::

## 4. Уведомления от панели

Чтобы бот присылал события панели (продление подписки, изменение пользователя), добавьте:

```ini
NOTIFICATIONS_CHAT_ID=-1001234567890
WEBHOOK_SECRET=ключ_из_openssl_rand_-hex_64
```

И укажите в самой панели Remnawave `WEBHOOK_URL` и тот же секрет. Подробно, с примерами для Caddy и nginx — в разделе [Webhook от панели](/guide/webhook-setup).

Если группа в Telegram сделана форумом, уведомления раскладываются по топикам — см. [переменные `NOTIFICATIONS_TOPIC_*`](/reference/env#уведомления).

## 5. Агент на нодах

Нужен для анти-абуза, метрик хоста, терминала и детекта торрентов. Ставится одной командой, которую панель собирает сама: **Ноды → нода → Токен агента → Установить агент**.

Подробности и ручная установка — [Node Agent](/guide/node-agent).

## Что дальше

- [Анти-абуз](/guide/anti-abuse) — пороги и автоматические действия
- [Почтовый сервер](/guide/mail) — если нужна своя отправка писем
- [Мониторинг](/guide/monitoring) — Prometheus и дашборды Grafana
- [Бэкапы](/guide/backups) — расписание и проверка восстановления
