#!/usr/bin/env python3
"""
Скрипт для синхронизации базы ASN по РФ из RIPE Database.

Использование:
    python3 scripts/sync_asn_database.py [--limit N] [--full]
    
    Или из корня проекта:
    python3 -m scripts.sync_asn_database [--limit N] [--full]
    
Опции:
    --limit N    Ограничить количество ASN для обработки (для тестирования)
    --full       Полная синхронизация (все ASN)
"""
import asyncio
import sys
import os
import argparse
from pathlib import Path

# Добавляем корневую директорию проекта в путь
# Получаем абсолютный путь к директории скрипта
script_dir = Path(__file__).resolve().parent
project_root = script_dir.parent

# Добавляем корневую директорию в начало sys.path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Устанавливаем рабочую директорию на корень проекта
os.chdir(project_root)

# Проверяем наличие необходимых директорий
src_dir = project_root / "src"
if not src_dir.exists():
    print(f"Ошибка: директория src не найдена в {project_root}")
    sys.exit(1)

# Проверяем наличие необходимых зависимостей
try:
    import httpx
except ImportError:
    print("Ошибка: модуль 'httpx' не установлен")
    print("\nУстановите зависимости проекта:")
    print(f"  cd {project_root}")
    print(f"  pip3 install -r requirements.txt")
    print("\nИли установите httpx отдельно:")
    print("  pip3 install httpx")
    sys.exit(1)

# Теперь импортируем модули
try:
    from src.services.database import DatabaseService
    from src.services.asn_parser import ASNParser
    from src.utils.logger import logger
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print(f"Корневая директория проекта: {project_root}")
    print(f"Текущая рабочая директория: {os.getcwd()}")
    print(f"sys.path (первые 3 элемента):")
    for i, path in enumerate(sys.path[:3], 1):
        print(f"  {i}. {path}")
    print(f"\nПроверьте:")
    print(f"  1. Что файл {src_dir / '__init__.py'} существует")
    print(f"  2. Что файл {src_dir / 'services' / '__init__.py'} существует")
    print(f"  3. Что файл {src_dir / 'services' / 'database.py'} существует")
    print(f"\nУстановите зависимости проекта:")
    print(f"  cd {project_root}")
    print(f"  pip3 install -r requirements.txt")
    sys.exit(1)


async def main():
    """Основная функция синхронизации."""
    parser = argparse.ArgumentParser(description='Синхронизация базы ASN по РФ')
    parser.add_argument('--limit', type=int, help='Ограничить количество ASN для обработки')
    parser.add_argument('--full', action='store_true', help='Полная синхронизация')
    
    args = parser.parse_args()
    
    logger.info("Starting ASN database synchronization...")
    
    # Инициализируем сервисы
    db_service = DatabaseService()
    
    try:
        # Подключаемся к БД
        await db_service.connect()
        logger.info("Connected to database")
        
        # Создаём парсер
        parser_service = ASNParser(db_service)
        
        try:
            # Запускаем синхронизацию
            limit = args.limit if args.limit else None
            if not args.full and not limit:
                # По умолчанию ограничиваем 100 ASN для тестирования
                limit = 100
                logger.info("Using default limit of 100 ASN (use --full for complete sync)")
            
            stats = await parser_service.sync_russian_asn_database(limit=limit)
            
            logger.info("=" * 60)
            logger.info("ASN Database Sync Results:")
            logger.info("  Total ASN processed: %d", stats['total'])
            logger.info("  Successfully synced: %d", stats['success'])
            logger.info("  Failed: %d", stats['failed'])
            logger.info("  Skipped (already exists): %d", stats['skipped'])
            logger.info("=" * 60)
            
        finally:
            await parser_service.close()
    
    except Exception as e:
        logger.error("Error during ASN sync: %s", e, exc_info=True)
        sys.exit(1)
    
    finally:
        await db_service.disconnect()
        logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
