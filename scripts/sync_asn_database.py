#!/usr/bin/env python3
"""
Скрипт для синхронизации базы ASN по РФ из RIPE Database.

Использование:
    python scripts/sync_asn_database.py [--limit N] [--full]
    
Опции:
    --limit N    Ограничить количество ASN для обработки (для тестирования)
    --full       Полная синхронизация (все ASN)
"""
import asyncio
import sys
import argparse
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.services.database import DatabaseService
from src.services.asn_parser import ASNParser
from src.utils.logger import logger


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
        await db_service.close()
        logger.info("Database connection closed")


if __name__ == "__main__":
    asyncio.run(main())
