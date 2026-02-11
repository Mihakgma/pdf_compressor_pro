# main.py
import os
import traceback
from datetime import datetime
from compressor_app import main
from models.database import create_tables

def write_to_log(error_message):
    """Простая запись ошибки в текстовый файл"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # Простой текстовый файл без даты в имени
    log_file = os.path.join(log_dir, "errors.txt")
    
    with open(log_file, "a", encoding="utf-8") as f:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{timestamp}] {error_message}\n")

if __name__ == '__main__':
    try:
        create_tables()
        main()
    except Exception as e:
        # Формируем полное сообщение об ошибке
        error_msg = f"Ошибка: {str(e)}\nТрассировка: {traceback.format_exc()}"
        print(f"Возникла ошибка в основном файле программы!")
        print(error_msg)
        
        # Записываем в лог
        write_to_log(error_msg)
        
        # Выводим пользователю
        print(f"Произошла ошибка: {e}")
        print("Подробности записаны в logs/errors.txt")
        input('Нажмите Enter для выхода')