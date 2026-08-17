# Webhook от панели Remnawave

Панель Remnawave умеет сообщать о том, что у неё происходит: продлилась подписка, добавилось устройство, отвалилась нода. Remnawave Admin принимает эти события и превращает в уведомления в Telegram.

Не путайте с [исходящими webhook](/reference/webhooks) — там наоборот, Remnawave Admin сам рассылает события во внешние системы.

## Настройка

### Со стороны Remnawave Admin

```ini
WEBHOOK_PORT=8080
# openssl rand -hex 64
WEBHOOK_SECRET=длинный_случайный_ключ
```

### Со стороны панели Remnawave

```ini
WEBHOOK_ENABLED=true
WEBHOOK_URL=http://bot:8080/webhook
WEBHOOK_SECRET_HEADER=тот_же_самый_ключ
```

`WEBHOOK_SECRET_HEADER` панели и `WEBHOOK_SECRET` бота обязаны совпадать: панель подписывает тело запроса HMAC-SHA256 и кладёт подпись в заголовок `X-Remnawave-Signature`, а бот её проверяет.

Имя хоста в `WEBHOOK_URL` — это имя сервиса из вашего `docker-compose.yml`. Если бот и панель в разных сетях или на разных серверах, поставьте перед ботом reverse proxy и укажите его адрес.

::: danger Самая частая ошибка — HTTPS на внутренний адрес
Webhook-сервер бота слушает **HTTP**. Адрес вида `https://bot:8080/webhook` даёт в логах панели `write EPROTO ... tlsv1 alert internal error`.

Внутри Docker-сети всегда `http://`. Если нужен HTTPS снаружи — терминируйте его на reverse proxy, а до бота идите по HTTP.
:::

## Проверка

```bash
curl http://localhost:8080/webhook/health
# {"status":"ok","service":"webhook"}
```

В логах бота при старте должно быть `Webhook server will be started on port 8080`. Дальше измените что-нибудь у тестового пользователя в панели и посмотрите, пришло ли уведомление.

## Какие события приходят

::: details Пользователи (`user.*`)
`created`, `modified`, `deleted`, `revoked`, `disabled`, `enabled`, `limited`, `expired`, `traffic_reset`, `first_connected`, `not_connected`, `bandwidth_usage_threshold_reached`, а также предупреждения об истечении: `expires_in_72_hours`, `expires_in_48_hours`, `expires_in_24_hours`, `expired_24_hours_ago`.

В уведомлении видно, что именно изменилось: лимит трафика, дата истечения, лимит устройств — старое значение и новое, ссылка на подписку, сквад.
:::

::: details Устройства (`user_hwid_devices.*`)
`added`, `deleted` — пользователь, HWID устройства, дата.
:::

::: details Ноды (`node.*`)
`created`, `modified`, `deleted`, `disabled`, `enabled`, `connection_lost`, `connection_restored`, `traffic_notify` — название, UUID, адрес, страна, статус, лимит трафика.
:::

::: details Сервис и ошибки (`service.*`, `errors.*`)
`panel_started`, `login_attempt_failed`, `login_attempt_success` — с адресом и User-Agent. Плюс `errors.bandwidth_usage_threshold_reached_max_notifications`.
:::

::: details Биллинг инфраструктуры (`crm.*`)
Напоминания об оплате нод: за 7 дней, 48 и 24 часа, в день оплаты, и просрочки на 24 часа, 48 часов и 7 дней — нода, провайдер, сумма, дата следующего платежа.
:::

Куда какое уведомление попадёт, решают [топики](/guide/bot#раскладка-по-топикам).

## Если не приходит

1. `WEBHOOK_ENABLED=true` в панели?
2. Адрес в `WEBHOOK_URL` резолвится с той стороны? Проверьте `docker exec <панель> wget -qO- http://bot:8080/webhook/health`
3. Порт 8080 доступен между контейнерами — в одной ли они сети?
4. Секреты совпадают? Различие даст отказ по подписи, и в логах бота будет об этом запись
5. Схема `http://`, а не `https://`, если идёте напрямую до контейнера
