# База данных ASN по РФ

Система использует локальную базу данных ASN (Autonomous System Number) для более точного определения местоположения и типа провайдера IP адресов из России.

## Описание

База данных ASN по РФ позволяет:
- **Точное определение местоположения**: Использование данных из RIPE Database для определения региона и города по ASN
- **Корректная классификация провайдеров**: Автоматическое определение типа провайдера (мобильный/домашний/датацентр/VPN)
- **Оптимизация запросов**: Снижение нагрузки на внешние GeoIP API за счёт использования локальной базы

## Структура базы данных

Таблица `asn_russia` содержит следующие поля:
- `asn` - номер ASN (первичный ключ)
- `org_name` - название организации
- `org_name_en` - название организации (английский)
- `provider_type` - тип провайдера: `mobile`/`residential`/`datacenter`/`vpn`/`isp`
- `region` - регион РФ
- `city` - город
- `country_code` - код страны (по умолчанию "RU")
- `description` - описание ASN
- `ip_ranges` - IP диапазоны (JSON)
- `is_active` - активен ли ASN
- `created_at`, `updated_at`, `last_synced_at` - временные метки

## Синхронизация базы данных

### Первоначальная синхронизация

Для первоначальной загрузки базы ASN по РФ выполните:

```bash
python scripts/sync_asn_database.py --full
```

Это загрузит все ASN из России из RIPE Database. Процесс может занять некоторое время (несколько часов для полной синхронизации).

### Тестовая синхронизация

Для тестирования можно ограничить количество ASN:

```bash
python scripts/sync_asn_database.py --limit 100
```

Это загрузит только первые 100 ASN для проверки работоспособности.

### Периодическая синхронизация

Рекомендуется настроить периодическую синхронизацию (например, раз в неделю) через cron или systemd timer:

```bash
# Добавить в crontab (синхронизация каждую неделю в воскресенье в 3:00)
0 3 * * 0 cd /path/to/remnawave-admin && python scripts/sync_asn_database.py --full
```

## Использование в системе

После синхронизации базы данных система автоматически использует её для:

1. **GeoIP Service** (`src/services/geoip.py`):
   - При определении геолокации IP адресов из России проверяет локальную базу ASN
   - Использует данные из базы для более точного определения региона и города
   - Классифицирует тип провайдера на основе данных из базы

2. **ASN Analyzer** (`src/services/violation_detector.py`):
   - Использует данные из базы ASN для более точной классификации провайдеров
   - Учитывает тип провайдера при анализе нарушений

## Миграция базы данных

Для создания таблицы `asn_russia` выполните миграцию:

```bash
alembic upgrade head
```

Миграция: `alembic/versions/20260128_0005_add_asn_russia_table.py`

## Источники данных

Система использует следующие источники:
- **RIPE Database REST API**: `https://rest.db.ripe.net` - для получения данных об ASN
- **RIPE Stat API**: `https://stat.ripe.net/data/country-resource-list` - для получения списка ASN по стране

## Классификация провайдеров

Система автоматически классифицирует провайдеров на основе ключевых слов в названии организации:

- **mobile**: МТС, Мегафон, Билайн, Теле2, Yota, Ростелеком Мобайл и другие мобильные операторы
- **datacenter**: Датацентры, хостинг-провайдеры
- **vpn**: VPN и прокси-сервисы
- **isp**: Интернет-провайдеры (домашние подключения)
- **residential**: По умолчанию для всех остальных

## API методы

### DatabaseService

- `get_asn_record(asn: int)` - получить запись ASN по номеру
- `get_asn_by_org_name(org_name: str)` - найти ASN по названию организации
- `get_asn_by_provider_type(provider_type: str)` - получить список ASN по типу провайдера
- `save_asn_record(asn_record)` - сохранить/обновить запись ASN
- `update_asn_sync_time()` - обновить время последней синхронизации

### ASNParser

- `sync_russian_asn_database(limit: Optional[int])` - синхронизировать базу ASN
- `fetch_asn_from_ripe(asn: int)` - получить данные об ASN из RIPE Database
- `fetch_russian_asn_list()` - получить список всех ASN в России
- `parse_and_save_asn(asn: int)` - распарсить и сохранить ASN

## Примеры использования

### Получить информацию об ASN

```python
from src.services.database import db_service

# Получить запись ASN
asn_record = await db_service.get_asn_record(12345)
if asn_record:
    print(f"ASN {asn_record['asn']}: {asn_record['org_name']}")
    print(f"Тип: {asn_record['provider_type']}")
    print(f"Регион: {asn_record['region']}, Город: {asn_record['city']}")
```

### Найти ASN по названию организации

```python
# Найти все ASN МТС
mts_asns = await db_service.get_asn_by_org_name("МТС")
for asn in mts_asns:
    print(f"ASN {asn['asn']}: {asn['org_name']}")
```

### Получить все мобильные операторы

```python
# Получить все ASN мобильных операторов
mobile_asns = await db_service.get_asn_by_provider_type("mobile")
print(f"Найдено {len(mobile_asns)} мобильных операторов")
```

## Примечания

- База данных ASN обновляется из RIPE Database, которая является официальным источником данных для европейского региона (включая Россию)
- Данные из базы ASN имеют приоритет над данными из внешних GeoIP API для IP адресов из России
- Система автоматически использует базу ASN при определении геолокации и типа провайдера через `GeoIPService`
