# Remnawave Admin Bot (Telegram, Python)

Телеграм-бот для администрирования Remnawave панели. Поддерживает RU/EN локализацию, inline-кнопки, docker-compose запуск и автосборку образа в GHCR через GitHub Actions.

## Быстрый старт (локально)
1. Создай виртуальное окружение и установи зависимости:
   ```bash
   python -m venv .venv
   .venv/Scripts/activate  # Windows
   pip install -r requirements.txt
   ```
2. Скопируй `.env.example` в `.env` и заполни:
   - `BOT_TOKEN` - токен @BotFather
   - `API_BASE_URL` - URL Remnawave API (в docker-сети: `http://remnawave:3000`)
   - `API_TOKEN` - Bearer/JWT токен API
   - `ADMINS` - Telegram ID администраторов через запятую
   - `DEFAULT_LOCALE` - `ru` или `en`
3. Запусти:
   ```bash
   python -m src.main
   ```

## Docker Compose
```bash
cp .env.example .env
# Заполни .env, для docker-сети укажи API_BASE_URL=http://remnawave:3000
# Сеть remnawave-network должна существовать (создаётся панелью, либо вручную: docker network create remnawave-network)
docker compose pull
docker compose up -d
```
Образ публикуется в GHCR: `ghcr.io/<OWNER>/remnawave-admin-bot:latest` (OWNER берётся из GitHub репозитория). Workflow: `.github/workflows/docker.yml`.

> docker-compose.yml теперь сразу пробрасывает переменные окружения (BOT_TOKEN, API_BASE_URL обязательны) и упадёт при их отсутствии. Значения берутся из `.env` в корне или из переменных окружения хоста.

## Функциональность
- Общие: `/start`, `/help`, `/health`, `/stats`, `/bandwidth`.
- Пользователи: `/user <username|telegram_id>`, inline-действия enable/disable/reset/revoke, bulk-операции (сброс трафика, удаление, продление, статус, revoke).
- Ноды: список/детали, действия enable/disable/restart/reset, realtime и range статистика, bulk назначение профиля+inbounds.
- Хосты: список/детали, enable/disable, bulk enable/disable/delete.
- Подписки: `/sub <short_uuid>`, открытие ссылки.
- API токены: список, создание, удаление через кнопки.
- Шаблоны подписок: список/детали, создание, reorder, обновление JSON, удаление.
- Сниппеты: список/просмотр/создание/обновление/удаление (JSON).
- Конфиг-профили: список, computed config.
- Биллинг: история оплат (просмотр/добавление/удаление), провайдеры (создание/обновление/удаление), биллинг-ноды (создать/обновить дату оплаты/удалить).
- Логирование: stdout (pino-формат через `logger`), удобно смотреть в docker logs.

## Структура
- `src/main.py` — точка входа, aiogram 3, i18n middleware.
- `src/handlers/basic.py` — вся логика команд/колбэков и ожидание ввода.
- `src/services/api_client.py` — httpx-клиент Remnawave API.
- `src/keyboards/` — inline-клавиатуры.
- `src/utils/` — форматтеры, i18n, logger, ACL.
- `locales/ru|en/messages.json` — тексты.

## Полезные команды
- Перезапуск docker-стека: `docker compose restart`
- Проверка логов: `docker compose logs -f bot`
