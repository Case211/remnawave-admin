# Решение проблем

## Бот не отвечает

```bash
docker compose ps                 # что вообще запущено
docker compose logs -f bot        # что говорит бот
docker compose config             # не сломан ли compose и .env
```

Если контейнер перезапускается по кругу — смотрите первые строки логов, там будет причина: обычно не заполнена обязательная переменная.

## Бот отвечает «отказано в доступе»

Ваш Telegram ID должен быть в `ADMINS`. Узнать его: [@userinfobot](https://t.me/userinfobot). После правки `.env` нужен `docker compose up -d`, чтобы контейнер перечитал переменные.

## Не работает связь с панелью Remnawave

- `API_BASE_URL` и `API_TOKEN` — актуальны? Токен в панели можно перевыпустить
- Сеть на месте: `docker network ls | grep remnawave-network`
- Если панель в другой сети или на другом сервере, адрес должен быть доступен из контейнера: `docker exec -it <бот> wget -qO- $API_BASE_URL/api/system/health`

## Потерян доступ к панели

Пароль сбрасывается CLI-утилитой — она ходит прямо в PostgreSQL и не требует работающей веб-панели.

```bash
# сгенерировать новый пароль
docker exec -it <контейнер> python3 scripts/admin_cli.py reset-password

# для конкретного администратора
docker exec -it <контейнер> python3 scripts/admin_cli.py reset-password --username myadmin

# со своим паролем
docker exec -it <контейнер> python3 scripts/admin_cli.py reset-password --password "MyNew$ecure1"

# завести нового суперадмина
docker exec -it <контейнер> python3 scripts/admin_cli.py create-superadmin --username newadmin

# посмотреть, кто вообще есть
docker exec -it <контейнер> python3 scripts/admin_cli.py list-admins
```

## Вход через Telegram не работает

1. `TELEGRAM_BOT_USERNAME` — без символа `@`
2. Домен панели прописан в BotFather: `/mybots` → бот → Bot Settings → Domain
3. Сайт открывается по HTTPS — виджет не работает по HTTP

## Агент ноды не подключается

`server rejected WebSocket connection: HTTP 404` — reverse proxy не пропускает `/api/v2/agent/ws`. Пример правильного конфига: [Веб-панель и reverse proxy](/guide/web-panel).

Прочие случаи разобраны в разделе [Node Agent](/guide/node-agent#если-данные-не-идут).

## Не приходят уведомления от панели

Проверьте [настройку webhook](/guide/webhook-setup#если-не-приходит): чаще всего дело в несовпадении секретов или в `https://` там, где нужен `http://`.

## Ошибка подключения к базе

`DATABASE_URL` должен совпадать с `POSTGRES_USER` и `POSTGRES_PASSWORD` — это три разных места, где легко разъехаться. Проверьте также, поднялся ли контейнер базы: `docker compose logs remnawave-admin-db`.

## Панель ругается на версию плагина

Плагин требует панель свежее, чем у вас. Обновите панель — [как](/guide/upgrade) — либо поставьте версию плагина постарше.

## Логи

Двухуровневые: файлы хранят всё, консоль — только предупреждения и ошибки.

| Файл | Уровень | Что внутри |
|------|---------|-----------|
| `adminbot_INFO.log` | INFO+ | вызовы API, синхронизация, действия |
| `adminbot_WARNING.log` | WARNING+ | таймауты и ошибки |
| `web_INFO.log` | INFO+ | веб-бэкенд |
| `web_WARNING.log` | WARNING+ | проблемы веб-бэкенда |

Ротация: 50 МБ на файл, пять архивов в gzip. Лежат в `./logs/`.

```bash
docker compose logs -f bot
tail -100 ./logs/adminbot_INFO.log
```

Уровень логирования, размер файлов и ротация меняются из настроек панели, без перезапуска.

## Куда идти дальше

Если ничего из перечисленного не подошло — [issues на GitHub](https://github.com/Case211/remnawave-admin/issues) или [чат в Telegram](https://t.me/remnawave_admin). К вопросу сразу приложите версию панели, кусок логов и то, что уже пробовали: это экономит один круг переписки.
