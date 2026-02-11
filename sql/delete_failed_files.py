# sql/delete_failed_files.py

#!/usr/bin/env python3

import os
import sys

# Добавляем путь к корню проекта
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Теперь можно импортировать
from models.database import SessionLocal
from models.models import ProcessedFile

def delete_failed_processed_files():
    """Удаляет записи о неудачно обработанных файлах"""
    db = SessionLocal()
    try:
        # Считаем сколько записей будет удалено
        failed_count = db.query(ProcessedFile).filter(ProcessedFile.is_successful == False).count()
        print(f"Найдено неудачных записей: {failed_count}")
        
        if failed_count > 0:
            # Удаляем записи
            deleted = db.query(ProcessedFile).filter(ProcessedFile.is_successful == False).delete()
            db.commit()
            print(f"Удалено записей: {deleted}")
        else:
            print("Неудачных записей не найдено")
            
        # Проверяем оставшиеся записи
        remaining_count = db.query(ProcessedFile).count()
        print(f"Осталось записей в базе: {remaining_count}")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    delete_failed_processed_files()
    