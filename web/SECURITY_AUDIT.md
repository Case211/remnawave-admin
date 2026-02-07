# Аудит безопасности — Remnawave Admin Web Panel

**Дата:** 2026-02-07
**Версия:** 2.0.0

---

## Критические проблемы

### 1. Нет инвалидации токенов при логауте
**Файл:** `web/backend/api/v2/auth.py:113-121`
**Уровень:** Высокий

Эндпоинт `/auth/logout` не инвалидирует JWT-токены на сервере. После логаута access и refresh токены остаются валидными до истечения срока.

**Рекомендация:** Реализовать серверный blacklist токенов (Redis или in-memory с TTL), проверять при каждом запросе через `get_current_admin()`.

### 2. JWT-токены хранятся в localStorage
**Файл:** `web/frontend/src/store/authStore.ts:116-123`
**Уровень:** Высокий

Access и refresh токены сохраняются в `localStorage` через Zustand persist. Это делает их уязвимыми для XSS-атак — любой внедрённый скрипт может прочитать токены.

**Рекомендация:** Перейти на HttpOnly cookies для хранения токенов. Если это невозможно — хотя бы не персистить access token, а хранить только в памяти (Zustand без persist для accessToken), а refresh token отправлять через HttpOnly cookie.

### 3. Нет rate limiting на аутентификацию
**Файлы:** `web/backend/api/v2/auth.py`, `web/backend/main.py`
**Уровень:** Высокий

Отсутствует ограничение частоты запросов на эндпоинтах `/auth/telegram`, `/auth/refresh`. Возможен brute-force по refresh токенам.

**Рекомендация:** Добавить `slowapi` или собственный middleware rate limiter:
- `/auth/telegram`: максимум 5 попыток в минуту на IP
- `/auth/refresh`: максимум 10 попыток в минуту на IP
- Глобально: 100 req/min на IP для API

---

## Средние проблемы

### 4. Раскрытие Telegram ID в ответах об ошибке
**Файл:** `web/backend/api/v2/auth.py:57`
**Уровень:** Средний

При неудачной авторизации в ответе возвращается Telegram ID пользователя: `"Not an admin. Your Telegram ID (12345) is not in the allowed list."`. Это раскрывает информацию о механизме авторизации.

**Рекомендация:** Заменить на общее сообщение `"Access denied"` без деталей. Детали логировать серверно.

### 5. CORS разрешает все методы и заголовки
**Файл:** `web/backend/main.py:197-203`
**Уровень:** Средний

```python
allow_methods=["*"],
allow_headers=["*"],
```

Разрешены все HTTP-методы и заголовки, что расширяет поверхность атаки.

**Рекомендация:** Ограничить:
```python
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
allow_headers=["Authorization", "Content-Type"],
```

### 6. Конфигурируемый JWT-алгоритм
**Файл:** `web/backend/core/config.py:28`
**Уровень:** Средний

JWT алгоритм задаётся через переменную окружения `WEB_JWT_ALGORITHM`. Теоретически можно установить `"none"` (хотя библиотека `python-jose` должна это отклонить).

**Рекомендация:** Использовать whitelist допустимых алгоритмов:
```python
@field_validator("jwt_algorithm")
def validate_algorithm(cls, v):
    allowed = {"HS256", "HS384", "HS512"}
    if v not in allowed:
        raise ValueError(f"Недопустимый алгоритм: {v}")
    return v
```

### 7. WebSocket токен передаётся в query string
**Файл:** `web/backend/api/deps.py:68-71`
**Уровень:** Средний

JWT передаётся как query parameter `?token=...` для WebSocket подключений. Это может быть залогировано в access logs сервера/proxy.

**Рекомендация:** Принимать токен через первое сообщение WebSocket (handshake message) вместо query parameter.

### 8. Настройки кешируются навсегда (lru_cache)
**Файл:** `web/backend/core/config.py:81-83`
**Уровень:** Средний

```python
@lru_cache()
def get_web_settings() -> WebSettings:
```

После первого вызова настройки кешируются навсегда. Изменение списка админов или секретного ключа требует перезапуска сервера.

**Рекомендация:** Использовать `functools.lru_cache(maxsize=1)` с TTL-обёрткой или вручную сбрасывать кеш при изменении конфигурации.

---

## Низкие проблемы

### 9. Внешний скрипт Telegram Login Widget
**Файл:** `web/frontend/src/pages/Login.tsx:43`
**Уровень:** Низкий

Загружается сторонний скрипт `https://telegram.org/js/telegram-widget.js` без SRI (Subresource Integrity). Если CDN Telegram скомпрометирован, возможна инъекция.

**Рекомендация:** Добавить `integrity` атрибут при загрузке скрипта или проксировать его через собственный сервер.

### 10. Нет Content Security Policy
**Файл:** `web/backend/main.py`
**Уровень:** Низкий

Не настроен заголовок `Content-Security-Policy`. Это снижает защиту от XSS.

**Рекомендация:** Добавить CSP middleware:
```python
@app.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response
```

### 11. Использование browser confirm() для деструктивных операций
**Файлы:** `Nodes.tsx:187`, `Hosts.tsx:134`
**Уровень:** Низкий

Удаление нод и хостов защищено только `window.confirm()`. Нет подтверждения на уровне API (ввод имени ресурса для подтверждения удаления).

**Рекомендация:** Заменить на модальный диалог с вводом имени ресурса для критических операций.

### 12. Dev bypass упоминается в документации
**Файл:** `web/backend/api/v2/auth.py:33`
**Уровень:** Низкий

Docstring эндпоинта `/auth/telegram` содержит описание dev bypass механизма: `"send hash="dev_bypass" when WEB_DEBUG=true"`. Это раскрывает информацию об отладочных функциях.

**Рекомендация:** Убрать описание dev bypass из docstring (оставить только в внутренней документации/README).

---

## Положительные аспекты

- HMAC-SHA256 верификация подписей Telegram с `hmac.compare_digest` (защита от timing attacks)
- Проверка `auth_date` для защиты от replay-атак (24h TTL + 1min clock skew)
- JWT access + refresh token pattern с отдельными типами (`type: "access"/"refresh"`)
- Проверка админ-списка при каждом запросе через `get_current_admin()` dependency
- Token refresh повторно проверяет статус админа
- Безопасное хранение localStorage с обработкой ошибок квоты
- API документация (`/api/docs`) доступна только при `WEB_DEBUG=true`
- Axios interceptor для автоматического обновления токенов
- Auto-upgrade HTTP→HTTPS для Mixed Content protection

---

## Приоритеты реализации

| Приоритет | Задача | Сложность | Статус |
|-----------|--------|-----------|--------|
| P0 | Rate limiting на auth эндпоинты | Низкая | ИСПРАВЛЕНО |
| P0 | Убрать Telegram ID из ответов ошибок | Низкая | ИСПРАВЛЕНО |
| P1 | Token blacklist при логауте | Средняя | ИСПРАВЛЕНО |
| P1 | HttpOnly cookies для JWT | Высокая | Открыто (требует рефакторинг фронта) |
| P1 | Whitelist JWT алгоритмов | Низкая | ИСПРАВЛЕНО |
| P2 | CSP и security headers | Низкая | ИСПРАВЛЕНО |
| P2 | Ограничить CORS методы/заголовки | Низкая | ИСПРАВЛЕНО |
| P2 | WebSocket token через handshake | Средняя | Открыто |
| P2 | Dev bypass в docstring | Низкая | ИСПРАВЛЕНО |
| P3 | SRI для Telegram widget | Низкая | Открыто |
| P3 | Кастомные модалки для удаления | Средняя | Открыто |
