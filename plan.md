# Фаза 4 — Улучшение существующих функций: План реализации

## Порядок реализации

Реализация идёт снизу вверх: сначала фундамент (зависимости, базовые компоненты, RBAC-фикс), затем фичи, которые используются повсеместно (toast, breadcrumbs), и в конце — крупные фичи (bulk ops, export, command palette).

---

## Шаг 0 — Подготовка: зависимости, базовые компоненты, RBAC-фикс

### 0.1 Установка npm-зависимостей
```bash
cd web/frontend
npm install sonner cmdk @radix-ui/react-checkbox papaparse
npm install -D @types/papaparse
```

### 0.2 Добавление shadcn/ui компонентов
Создать новые UI-компоненты в `web/frontend/src/components/ui/`:
- `checkbox.tsx` — на базе `@radix-ui/react-checkbox` (для bulk select в таблицах)
- `command.tsx` — на базе `cmdk` (для Command Palette)
- `sonner.tsx` — обёртка для toast-уведомлений
- `breadcrumb.tsx` — компонент навигационных крошек
- `alert-dialog.tsx` — диалог подтверждения (замена `confirm()`)

### 0.3 Интеграция Sonner в корень приложения
- В `main.tsx` (или `App.tsx`) добавить `<Toaster />` от sonner
- Настроить тему (dark), позицию (bottom-right), стили под Remnawave

### 0.4 Обновление матрицы RBAC-прав

**Проблема:** Frontend permission gates есть только на 3 из 8 страниц. На 5 страницах кнопки действий видны всем, защита только на уровне backend (403).

#### 0.4.1 Backend: добавить action `bulk_operations`

**Файл:** `web/backend/core/rbac.py` — добавить `bulk_operations` в `AVAILABLE_ACTIONS`

**Файл:** Alembic миграция — добавить `bulk_operations` в permissions для ролей:
- `superadmin`: users.bulk_operations ✅
- `manager`: users.bulk_operations ✅
- `operator`: ❌ (нет доступа к массовым операциям)
- `viewer`: ❌

#### 0.4.2 Frontend: добавить PermissionGate на все страницы

**`Nodes.tsx`** — добавить гейты:
- Кнопка «Создать ноду» → `<PermissionGate resource="nodes" action="create">`
- Кнопки restart/enable/disable в строке → `useHasPermission('nodes', 'edit')`
- Кнопка delete → `useHasPermission('nodes', 'delete')`
- Кнопка agent-token → `useHasPermission('nodes', 'edit')`

**`Hosts.tsx`** — добавить гейты:
- Кнопка «Создать хост» → `<PermissionGate resource="hosts" action="create">`
- Кнопки edit/enable/disable → `useHasPermission('hosts', 'edit')`
- Кнопка delete → `useHasPermission('hosts', 'delete')`

**`Violations.tsx`** — добавить гейты:
- Кнопки Block/Warn/Dismiss → `useHasPermission('violations', 'resolve')`

**`Settings.tsx`** — добавить гейты:
- Все поля ввода и кнопки сохранения → `useHasPermission('settings', 'edit')`
- При отсутствии прав — показывать значения read-only

**`Dashboard.tsx`** — добавить гейты:
- Быстрые действия на карточках нод (restart, enable/disable) → `useHasPermission('nodes', 'edit')`

**`Fleet.tsx`** — проверить и добавить гейты при наличии мутирующих действий

---

## Шаг 1 — Toast-уведомления (4.4.1)

**Файлы:** все страницы с мутациями

### 1.1 Замена всех `confirm()` на `AlertDialog`
- `Users.tsx`: удаление пользователя, enable/disable — заменить `window.confirm()` на `<AlertDialog>` с описанием действия
- `Nodes.tsx`, `Hosts.tsx`: аналогичные замены

### 1.2 Добавление toast на все мутации
Паттерн для каждой `useMutation`:
```typescript
onSuccess: () => {
  toast.success('Пользователь включён')
  queryClient.invalidateQueries(...)
},
onError: (err) => {
  toast.error(`Ошибка: ${err.message}`)
}
```

**Страницы для обновления:**
- `Users.tsx` — create, enable, disable, delete, update (5 мутаций)
- `UserDetail.tsx` — update, reset-traffic, revoke, sync-hwid (4 мутации)
- `Nodes.tsx` — restart, enable, disable (3 мутации)
- `Hosts.tsx` — create, update, delete, enable, disable (5 мутаций)
- `Violations.tsx` — resolve (1 мутация)
- `Settings.tsx` — save settings (1 мутация)
- `Admins.tsx` — create, update, delete admin/role (6+ мутаций)

---

## Шаг 2 — Breadcrumbs (4.4.4)

**Файлы:** `Layout.tsx`, `Header.tsx`, страницы с вложенностью

### 2.1 Компонент `Breadcrumb`
Создать в `components/ui/breadcrumb.tsx` — цепочка ссылок с разделителем `/` или `>`.

### 2.2 Интеграция в Layout
- Добавить `<Breadcrumbs />` между Header и основным контентом
- Генерация из текущего `location.pathname` + React Router:
  - `/` → `Dashboard`
  - `/users` → `Dashboard / Users`
  - `/users/:uuid` → `Dashboard / Users / {username}`
  - `/violations` → `Dashboard / Violations`
  - `/admins` → `Dashboard / Admins`

### 2.3 Динамические названия
- Для `/users/:uuid` — показывать username (из React Query кеша или URL state)
- Для остальных — статические названия из маппинга путей

---

## Шаг 3 — Keyboard Shortcuts (4.4.3)

**Файлы:** `Layout.tsx`, страницы

### 3.1 Глобальные хоткеи (в Layout)
Использовать нативный `useEffect` + `keydown` (без дополнительных библиотек):
- `Cmd/Ctrl + K` — открыть Command Palette (Шаг 5)
- `Escape` — закрыть открытый модал/панель (уже работает через Radix Dialog)

### 3.2 Хоткеи на странице Users
- `Cmd/Ctrl + A` — выбрать все строки (когда в режиме bulk select)
- `Cmd/Ctrl + Shift + A` — снять выделение

### 3.3 Хоткеи в модалах
- `Enter` — подтвердить (submit формы / confirm dialog)
- Уже частично работает через Radix, дополнить где нужно

---

## Шаг 4 — Массовые операции (4.1)

### 4.1 Backend: batch endpoints

**Файл:** `web/backend/api/v2/users.py`

Добавить 4 новых эндпоинта:

```python
POST /api/v2/users/bulk/enable     # {"uuids": ["uuid1", "uuid2", ...]}
POST /api/v2/users/bulk/disable    # {"uuids": ["uuid1", "uuid2", ...]}
POST /api/v2/users/bulk/delete     # {"uuids": ["uuid1", "uuid2", ...]}
POST /api/v2/users/bulk/update     # {"uuids": [...], "changes": {"traffic_limit": ...}}
```

Каждый эндпоинт:
- Принимает список UUID (максимум 100 за раз)
- Проверяет RBAC: `require_permission("users", "bulk_operations")`
- Вызывает upstream Remnawave API для каждого пользователя
- Возвращает результат: `{"success": N, "failed": N, "errors": [...]}`
- Логирует в audit_log

Pydantic-схемы в `web/backend/schemas/`:
```python
class BulkUserRequest(BaseModel):
    uuids: list[str] = Field(..., max_length=100)

class BulkUserUpdateRequest(BaseModel):
    uuids: list[str] = Field(..., max_length=100)
    changes: dict  # traffic_limit, expire_at, etc.

class BulkOperationResult(BaseModel):
    success: int
    failed: int
    errors: list[dict]
```

### 4.2 Frontend: выбор строк в таблице Users

**Файл:** `web/frontend/src/pages/Users.tsx`

- Добавить state: `selectedUuids: Set<string>`
- В каждую строку таблицы — `<Checkbox>` в первом столбце
- В `<thead>` — `<Checkbox>` для "Выбрать все на странице"
- На мобильных карточках — тоже чекбокс

### 4.3 Frontend: панель массовых действий

При `selectedUuids.size > 0` показывать sticky-панель внизу экрана:
```
┌──────────────────────────────────────────────────┐
│ Выбрано: 12 пользователей  │ Включить │ Выключить │ Удалить │ Отмена │
└──────────────────────────────────────────────────┘
```

- Кнопки защищены `<PermissionGate resource="users" action="bulk_operations">`
- Каждое действие открывает `<AlertDialog>` с подтверждением:
  - «Вы уверены? Будет затронуто N пользователей»
  - Предпросмотр: список затронутых usernames (первые 5 + "и ещё N")
- Прогресс через toast: «Обработка... 12/12 выполнено»
- Сброс выделения после успешной операции

### 4.4 Frontend API клиент

**Файл:** `web/frontend/src/api/users.ts` (новый или расширение существующего)

```typescript
export const bulkEnableUsers = (uuids: string[]) =>
  client.post('/users/bulk/enable', { uuids })
export const bulkDisableUsers = (uuids: string[]) =>
  client.post('/users/bulk/disable', { uuids })
export const bulkDeleteUsers = (uuids: string[]) =>
  client.post('/users/bulk/delete', { uuids })
```

---

## Шаг 5 — Глобальный поиск / Command Palette (4.3.1)

### 5.1 Компонент `CommandPalette`

**Файл:** `web/frontend/src/components/CommandPalette.tsx`

На базе `cmdk` (shadcn Command component):
- Открывается по `Cmd/Ctrl + K` или клику на поиск в Header
- Группы:
  - **Навигация:** Dashboard, Users, Nodes, Hosts, Violations, Admins, Settings
  - **Быстрые действия:** Создать пользователя, Перезапустить ноду, Экспорт
  - **Поиск:** Ввод текста → поиск пользователей по username/email (debounce 300ms, запрос к `/users?search=...`)
- Результаты кликабельны → `navigate()` к нужной странице
- Закрытие: `Escape` или клик вне

### 5.2 Подключение поиска в Header
- Связать существующий Input в `Header.tsx` с CommandPalette
- Клик на Input → открыть CommandPalette
- Показать подсказку `⌘K` справа в Input

### 5.3 Backend: поисковый эндпоинт (опционально)
Если текущий `/users?search=` слишком медленный для автокомплита — добавить легковесный:
```python
GET /api/v2/search?q=query&limit=5
```
Возвращает: `[{type: "user", label: "username", uuid: "..."}]`

---

## Шаг 6 — Расширенный поиск нарушений (4.3.3)

**Файл:** `web/frontend/src/pages/Violations.tsx`

### 6.1 Дополнительные фильтры
Расширить панель фильтров:
- **По IP адресу** — текстовое поле, поиск в списке IP нарушений
- **По стране** — Select с флагами, фильтр по `country_code`
- **По ASN** — текстовое поле
- **По диапазону дат** — Date range picker (два Input type="date")

### 6.2 Backend: расширенный фильтр
**Файл:** `web/backend/api/v2/violations.py`

Расширить `GET /violations` параметрами:
```python
ip: Optional[str] = None           # фильтр по IP
country: Optional[str] = None      # фильтр по country_code
asn: Optional[str] = None          # фильтр по ASN
date_from: Optional[datetime] = None
date_to: Optional[datetime] = None
```

---

## Шаг 7 — Экспорт данных (4.2)

### 7.1 Экспорт пользователей (4.2.1)

**Frontend** (`Users.tsx`):
- Кнопка «Экспорт» рядом с фильтрами
- Dropdown: CSV / JSON
- Опции: "Текущая выборка (с фильтрами)" / "Все пользователи"
- Генерация CSV на клиенте через `papaparse`:
  - Данные берутся из текущего React Query кеша (если "текущая выборка")
  - Или запрос всех данных с `/users?per_page=10000` (если "все")
- Скачивание файла через `Blob` + `URL.createObjectURL` + `<a download>`

**Колонки CSV:**
username, status, traffic_used, traffic_limit, hwid_count, hwid_limit, online_at, expire_at, created_at, email, telegram_id, description

### 7.2 Экспорт нарушений (4.2.2)

**Frontend** (`Violations.tsx`):
- Аналогичная кнопка «Экспорт CSV»
- Колонки: date, username, score, severity, reasons, countries, ips, recommendation, status

### 7.3 Экспорт дашборда (4.2.3)

**Frontend** (`Dashboard.tsx`):
- Кнопка «Экспорт PNG» на дашборде
- Используем `html-to-image` или `html2canvas` для скриншота секции с графиками
- Скачивание как PNG-файл

> **Примечание:** Экспорт в PDF — отложить, т.к. требует тяжёлую библиотеку (`jspdf` + `html2canvas`). PNG покрывает основные кейсы для отчётов.

---

## Шаг 8 — Сохранённые фильтры (4.3.2)

**Файл:** `web/frontend/src/pages/Users.tsx`, `Violations.tsx`

### 8.1 Модель сохранённого фильтра
```typescript
interface SavedFilter {
  id: string
  name: string
  page: 'users' | 'violations'
  filters: Record<string, any>
}
```

### 8.2 Хранение
- `localStorage` (без бэкенда) — ключ `saved_filters`
- Zustand store `useFiltersStore` с persist middleware

### 8.3 UI
- Кнопка "Сохранить фильтр" рядом с панелью фильтров (появляется когда есть активные фильтры)
- Dropdown "Загрузить фильтр" со списком сохранённых
- Возможность удалить сохранённый фильтр

---

## Итого: порядок выполнения и зависимости

```
Шаг 0 (Подготовка + RBAC-фикс)
  ├─→ 0.1-0.3 (npm, компоненты, sonner)
  └─→ 0.4 (RBAC: bulk_operations action + PermissionGate на 5 страницах)
       └─→ Шаг 1 (Toast) — используется во всех последующих шагах
            ├─→ Шаг 2 (Breadcrumbs) — независим
            ├─→ Шаг 3 (Keyboard shortcuts) — частично зависит от Шага 5
            ├─→ Шаг 4 (Bulk operations) — использует toast, alert-dialog, checkbox, RBAC bulk_operations
            ├─→ Шаг 5 (Command Palette) — использует command.tsx
            ├─→ Шаг 6 (Поиск нарушений) — независим
            ├─→ Шаг 7 (Экспорт) — независим
            └─→ Шаг 8 (Сохранённые фильтры) — независим
```

## Файлы для создания (новые)

| Файл | Описание |
|------|----------|
| `components/ui/checkbox.tsx` | shadcn Checkbox |
| `components/ui/command.tsx` | shadcn Command (cmdk) |
| `components/ui/sonner.tsx` | Обёртка Sonner Toaster |
| `components/ui/breadcrumb.tsx` | shadcn Breadcrumb |
| `components/ui/alert-dialog.tsx` | shadcn AlertDialog |
| `components/CommandPalette.tsx` | Глобальный поиск Cmd+K |
| `store/useFiltersStore.ts` | Сохранённые фильтры |
| `web/backend/schemas/bulk.py` | Pydantic-схемы для bulk ops |
| `alembic/versions/xxxx_add_bulk_operations_permission.py` | Миграция: добавить bulk_operations |

## Файлы для модификации

| Файл | Изменения |
|------|-----------|
| `App.tsx` / `main.tsx` | `<Toaster />` |
| `Layout.tsx` | Breadcrumbs, keyboard listener для Cmd+K |
| `Header.tsx` | Связать поиск с CommandPalette |
| `pages/Users.tsx` | Checkboxes, bulk toolbar, export, saved filters, toast |
| `pages/UserDetail.tsx` | Toast на мутации, breadcrumbs data |
| `pages/Violations.tsx` | Расширенные фильтры, export, toast, PermissionGate на resolve |
| `pages/Dashboard.tsx` | Export PNG, PermissionGate на быстрые действия нод |
| `pages/Nodes.tsx` | Toast на мутации, PermissionGate на create/edit/delete |
| `pages/Hosts.tsx` | Toast на мутации, PermissionGate на create/edit/delete |
| `pages/Settings.tsx` | Toast на мутации, PermissionGate на edit (read-only fallback) |
| `pages/Fleet.tsx` | PermissionGate (проверить и добавить) |
| `pages/Admins.tsx` | Toast на мутации |
| `backend/core/rbac.py` | Добавить `bulk_operations` в AVAILABLE_ACTIONS |
| `backend/api/v2/users.py` | Batch endpoints с require_permission("users", "bulk_operations") |
| `backend/api/v2/violations.py` | Расширенные фильтры |
| `package.json` | Новые зависимости |

## Оценка объёма

- **Новый код:** ~2500-3000 строк (frontend) + ~400-500 строк (backend)
- **Модификации:** ~600-800 строк изменений в существующих файлах (включая RBAC-гейты)
- **Новые файлы:** 9
- **Модифицированные файлы:** 16
