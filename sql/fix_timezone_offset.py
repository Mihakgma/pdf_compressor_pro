#!/usr/bin/env python3
"""
Скрипт для корректировки временных зон в базе данных PDF Compressor
Добавляет +7 часов ко всем существующим записям в столбцах с датами
"""

# scripts/fix_timezone_offset.py

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Добавляем путь к проекту для импорта модулей
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.database import get_db, create_tables
from models.models import Setting, ProcessedFile


def fix_timezone_offset():
    """
    Основная функция для корректировки временных зон
    Добавляет +7 часов ко всем существующим датам в базе
    """
    print("=== КОРРЕКТИРОВКА ВРЕМЕННЫХ ЗОН В БАЗЕ ДАННЫХ ===")

    try:
        # Получаем соединение с базой
        db = next(get_db())

        # 1. Корректируем таблицу Setting (столбец created_at)
        print("1. Корректируем таблицу Setting...")
        settings = db.query(Setting).all()
        settings_updated = 0

        for setting in settings:
            if setting.created_at:
                # Добавляем 7 часов к существующей дате
                new_time = setting.created_at + timedelta(hours=7)
                setting.created_at = new_time
                settings_updated += 1

        print(f"   Обновлено записей: {settings_updated}")

        # 2. Корректируем таблицу ProcessedFile (столбец processed_date)
        print("2. Корректируем таблицу ProcessedFile...")
        processed_files = db.query(ProcessedFile).all()
        files_updated = 0

        for file_record in processed_files:
            if file_record.processed_date:
                # Добавляем 7 часов к существующей дате
                new_time = file_record.processed_date + timedelta(hours=7)
                file_record.processed_date = new_time
                files_updated += 1

        print(f"   Обновлено записей: {files_updated}")

        # 3. Сохраняем изменения
        print("3. Сохраняем изменения в базе...")
        db.commit()

        # 4. Выводим статистику
        print("\n=== РЕЗУЛЬТАТЫ КОРРЕКТИРОВКИ ===")
        print(f"Таблица Setting: {settings_updated} записей обновлено")
        print(f"Таблица ProcessedFile: {files_updated} записей обновлено")
        print(f"Всего обновлено: {settings_updated + files_updated} записей")
        print("Корректировка завершена успешно! ✅")

        # 5. Показываем примеры изменений
        if settings_updated > 0:
            print("\nПример изменений (первые 3 записи из Setting):")
            sample_settings = db.query(Setting).limit(3).all()
            for i, setting in enumerate(sample_settings, 1):
                print(f"   {i}. ID {setting.id}: {setting.created_at}")

        if files_updated > 0:
            print("\nПример изменений (первые 3 записи из ProcessedFile):")
            sample_files = db.query(ProcessedFile).limit(3).all()
            for i, file_record in enumerate(sample_files, 1):
                print(f"   {i}. ID {file_record.id}: {file_record.processed_date}")

    except Exception as e:
        print(f"❌ Ошибка при корректировке временных зон: {e}")
        db.rollback()
        return False

    return True


def check_current_timezone():
    """
    Проверяет текущее состояние временных зон в базе
    """
    print("=== ПРОВЕРКА ТЕКУЩИХ ВРЕМЕННЫХ ЗОН ===")

    try:
        db = next(get_db())

        # Проверяем Setting
        settings_count = db.query(Setting).count()
        latest_setting = db.query(Setting).order_by(Setting.created_at.desc()).first()

        # Проверяем ProcessedFile
        files_count = db.query(ProcessedFile).count()
        latest_file = db.query(ProcessedFile).order_by(ProcessedFile.processed_date.desc()).first()

        print(f"Таблица Setting: {settings_count} записей")
        if latest_setting:
            print(f"   Последняя запись: {latest_setting.created_at}")

        print(f"Таблица ProcessedFile: {files_count} записей")
        if latest_file:
            print(f"   Последняя запись: {latest_file.processed_date}")

        print(f"Текущее системное время: {datetime.now()}")

    except Exception as e:
        print(f"Ошибка при проверке: {e}")


def main():
    """
    Главная функция скрипта
    """
    print("PDF Compressor - Корректор временных зон")
    print("=" * 50)

    # Проверяем существование базы данных
    db_path = project_root / "pdf_compressor.db"
    if not db_path.exists():
        print("❌ База данных не найдена!")
        print(f"   Ожидаемый путь: {db_path}")
        return

    print(f"База данных: {db_path}")
    print(f"Размер базы: {db_path.stat().st_size / 1024 / 1024:.2f} MB")

    # Показываем текущее состояние
    check_current_timezone()

    # Запрос подтверждения
    print("\n" + "=" * 50)
    response = input("Добавить +7 часов ко всем датам в базе? (y/N): ")

    if response.lower() in ['y', 'yes', 'д', 'да']:
        print("\nЗапуск корректировки...")
        success = fix_timezone_offset()

        if success:
            print("\n✅ Корректировка завершена успешно!")
            print("Теперь все даты отображаются в правильном часовом поясе (+7 часов).")
        else:
            print("\n❌ Корректировка не выполнена!")
    else:
        print("❌ Операция отменена пользователем.")

    input("\nНажмите Enter для выхода...")


if __name__ == "__main__":
    main()
