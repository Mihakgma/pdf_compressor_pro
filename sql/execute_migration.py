# sql/execute_migration.py

import sqlite3
import os

def execute_migration():
    # Путь к БД в корне приложения
    db_path = os.path.join('..', 'pdf_compressor.db')
    
    # Проверяем существование БД
    if not os.path.exists(db_path):
        print(f"Ошибка: База данных не найдена по пути: {db_path}")
        return
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Читаем SQL файл
        with open('manual_migration.sql', 'r', encoding='utf-8') as f:
            sql_script = f.read()
        
        # Выполняем скрипт
        cursor.executescript(sql_script)
        conn.commit()
        print("Миграция успешно выполнена!")
        
        # Проверяем результат
        cursor.execute("PRAGMA table_info(setting)")
        columns = cursor.fetchall()
        print("\nСтруктура таблицы setting:")
        for col in columns:
            print(f"  {col[1]} ({col[2]})")
            
    except Exception as e:
        print(f"Ошибка: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    execute_migration()