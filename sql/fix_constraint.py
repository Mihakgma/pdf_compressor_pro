# sql/fix_constraint.
import sqlite3
import os

def fix_database():
    # Путь к БД в корне приложения
    db_path = os.path.join('..', 'pdf_compressor.db')
    
    # Проверяем существование БД
    if not os.path.exists(db_path):
        print(f"Ошибка: База данных не найдена по пути: {db_path}")
        return
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    try:
        # Удаляем старый constraint
        cursor.execute("DROP INDEX IF EXISTS uq_setting_combination")
        print("Старый constraint удален")
        
        # Создаем новый constraint с новыми полями
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_setting_combination 
            ON setting (
                nesting_depth_id, need_replace, compression_level, 
                compression_method_id, compression_min_boundary, 
                procession_timeout, timeout_iterations, timeout_interval_secs
            )
        """)
        print("Новый constraint создан")
        
        conn.commit()
        print("База данных успешно обновлена!")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_database()