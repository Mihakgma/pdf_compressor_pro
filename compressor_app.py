# compressor_app.py
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import datetime
import threading
import shutil
import subprocess
import tempfile
import uuid
import glob
import time
import traceback

# Импорты для работы с БД
from models.database import get_db, create_tables
from models.models import ProcessedFile, CompressionMethod
from crud.operations import DBOperations
from stats_window import StatsWindow

# Импорт OCR процессора
try:
    from ocr_processor import OCRProcessor
    OCR_SUPPORT = True
except ImportError:
    OCR_SUPPORT = False
    print("OCRProcessor не доступен. OCR методы будут отключены.")


class PDFCompressor:
    def __init__(self, root):
        self.root = root
        self.root.title("PDF Compressor Pro")
        self.root.geometry("1100x800")

        # Инициализация БД
        create_tables()
        self.db = next(get_db())
        self.db_ops = DBOperations(self.db)
        self.db_ops.initialize_base_data()

        # Получаем активные настройки из БД
        self.active_setting = self.db_ops.get_active_setting()

        # Переменные для хранения настроек (инициализируем из БД)
        self.directory_path = tk.StringVar()
        self.depth_level = tk.IntVar(value=self.active_setting.nesting_depth_id if self.active_setting else 4)
        self.replace_original = tk.BooleanVar(
            value=self.active_setting.need_replace if self.active_setting else True)
        self.compression_level = tk.IntVar(value=self.active_setting.compression_level if self.active_setting else 2)
        self.compression_method_id = tk.IntVar(value=self.active_setting.compression_method_id if self.active_setting else 1)
        self.min_saving_threshold = tk.IntVar(
            value=self.active_setting.compression_min_boundary if self.active_setting else 1024)
        self.file_timeout = tk.IntVar(value=self.active_setting.procession_timeout if self.active_setting else 35)
        self.timeout_iterations = tk.IntVar(value=self.active_setting.timeout_iterations if self.active_setting else 350)
        self.timeout_interval_secs = tk.IntVar(value=self.active_setting.timeout_interval_secs if self.active_setting else 9)
        self.ocr_max_pages = tk.IntVar(value=self.active_setting.ocr_max_pages if self.active_setting else 120)
        
        # ✅ НОВОЕ: максимально допустимый размер страницы, КБ
        self.kbytes_per_page_border = tk.DoubleVar(value=(
            self.active_setting.kbytes_per_page_border if self.active_setting and 
            self.active_setting.kbytes_per_page_border is not None else 0.0
        ))

        # Инициализация OCR процессора - ОТЛОЖЕННАЯ
        self.ocr_processor = None
        self.ocr_available = False

        # Переменные для управления потоком
        self.currently_processing = False
        self.current_file_path = None
        self.stop_current_file = False
        self.processing_start_time = 0

        # Настройка системы логирования
        self.logs_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
        os.makedirs(self.logs_dir, exist_ok=True)
        self.current_log_file = None
        self.max_log_size = 10 * 1024 * 1024  # 10 MB

        # Журнал операций
        self.log_text = tk.Text(self.root, height=15, state=tk.DISABLED, wrap=tk.WORD)
        self.log_scrollbar = ttk.Scrollbar(self.root, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=self.log_scrollbar.set)

        # Статистика
        self.processed_files = 0
        self.skipped_files = 0
        self.failed_files = 0
        self.total_original_size = 0
        self.total_compressed_size = 0

        # Создаем метки для статистики
        self.files_count_label = ttk.Label(self.root, text="0")
        self.skipped_label = ttk.Label(self.root, text="0")
        self.failed_label = ttk.Label(self.root, text="0")
        self.saved_label = ttk.Label(self.root, text="0 MB")
        self.ratio_label = ttk.Label(self.root, text="0%")

        # Кнопка пропуска файла
        self.skip_button = ttk.Button(self.root, text="Пропустить файл", command=self.skip_current_file,
                                      state=tk.DISABLED)

        # Кнопка управления настройками
        self.settings_button = ttk.Button(self.root, text="Управление настройками", command=self.manage_settings)

        # Комбобокс для методов сжатия
        self.method_combo = None
        self.method_desc_label = None

        self.setup_ui()
        self.check_ghostscript()
        self.check_tools()  # Теперь OCR инициализируется здесь
        self.check_log_files()

    def check_tools(self):
        """Проверяет наличие всех необходимых инструментов"""
        gs_ok = self.check_ghostscript()
        
        # Инициализируем OCRProcessor только после создания UI
        if OCR_SUPPORT and self.ocr_processor is None:
            try:
                self.ocr_processor = OCRProcessor(self.db_ops, self.add_to_log)
                self.ocr_available = self.ocr_processor.ocr_available
            except Exception as e:
                self.add_to_log(f"Ошибка инициализации OCR: {e}", "warning")
                self.ocr_available = False
        elif not OCR_SUPPORT:
            self.ocr_available = False
            self.add_to_log("OCR модули не установлены. OCR методы будут отключены.", "warning")
        
        # Обновляем доступность методов в UI
        self.update_methods_availability()
        
        return gs_ok or self.ocr_available

    def update_methods_availability(self):
        """Обновляет доступность методов сжатия в UI"""
        if not self.method_combo:
            return
            
        # Получаем все методы
        methods = self.db_ops.get_all_compression_methods()
        combo_values = list(self.method_combo['values'])
        
        # Создаем новые значения с индикаторами доступности
        new_values = []
        for method in methods:
            ocr_mark = " (OCR)" if method.is_ocr_enabled else ""
            available = True
            
            # Проверяем доступность OCR методов
            if method.is_ocr_enabled and not self.ocr_available:
                available = False
                ocr_mark = " (OCR - НЕ ДОСТУПЕН)"
            
            method_text = f"{method.id}: {method.name}{ocr_mark}"
            new_values.append(method_text)
        
        self.method_combo['values'] = new_values
        
        # Устанавливаем первый доступный метод
        current_value = self.method_combo.get()
        if not current_value or "(OCR - НЕ ДОСТУПЕН)" in current_value:
            for value in new_values:
                if "(OCR - НЕ ДОСТУПЕН)" not in value:
                    self.method_combo.set(value)
                    break
        
        self.on_method_changed()

    def manage_settings(self):
        """Окно управления настройками"""
        settings_window = tk.Toplevel(self.root)
        settings_window.title("Управление настройками")
        settings_window.geometry("700x500")
        settings_window.transient(self.root)
        settings_window.grab_set()

        # Загрузка всех настроек
        all_settings = self.db_ops.get_all_settings()

        # Список настроек
        ttk.Label(settings_window, text="Сохраненные настройки:").pack(pady=5)

        # Фрейм для списка настроек с прокруткой
        list_frame = ttk.Frame(settings_window)
        list_frame.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        settings_listbox = tk.Listbox(list_frame, width=90, height=12, yscrollcommand=scrollbar.set)
        settings_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=settings_listbox.yview)

        for setting in all_settings:
            active_indicator = " [АКТИВНО]" if setting.is_active else ""
            border_text = f", Лимит стр: {setting.kbytes_per_page_border:.0f} КБ" if setting.kbytes_per_page_border else ", Лимит стр: выкл"
            settings_listbox.insert(
                tk.END,
                f"ID{setting.id}: Глубина={setting.nesting_depth.name}, "
                f"Замена={setting.need_replace}, Ур.сжатия={setting.compression_level}, "
                f"Метод={setting.compression_method.name}, Порог={setting.compression_min_boundary}Б, "
                f"Таймаут={setting.procession_timeout}, "
                f"Итерации={setting.timeout_iterations}шт, "
                f"Пауза={setting.timeout_interval_secs}с, "
                f"OCR стр={setting.ocr_max_pages}{border_text}"
                f"{active_indicator}"
            )

        # Фрейм для информации о настройке
        info_frame = ttk.LabelFrame(settings_window, text="Информация о настройке")
        info_frame.pack(pady=10, padx=10, fill=tk.X)

        info_text = tk.Text(info_frame, height=3, width=80)
        info_text.pack(pady=5, padx=5, fill=tk.X)

        def update_info_display():
            selection = settings_listbox.curselection()
            if selection:
                setting = all_settings[selection[0]]
                info_text.delete(1.0, tk.END)
                info_text.insert(1.0, setting.info or "Нет дополнительной информации")
            else:
                info_text.delete(1.0, tk.END)

        def save_setting_info():
            selection = settings_listbox.curselection()
            if selection:
                setting = all_settings[selection[0]]
                new_info = info_text.get(1.0, tk.END).strip()
                self.db_ops.update_setting_info(setting.id, new_info)
                messagebox.showinfo("Успех", "Информация сохранена!")
                settings_window.destroy()

        settings_listbox.bind('<<ListboxSelect>>', lambda e: update_info_display())

        # Фрейм для кнопок
        button_frame = ttk.Frame(settings_window)
        button_frame.pack(pady=10)

        def activate_selected():
            selection = settings_listbox.curselection()
            if selection:
                setting_id = all_settings[selection[0]].id
                self.db_ops.activate_setting(setting_id)
                self.load_active_settings()
                messagebox.showinfo("Успех", "Настройки активированы!")
                settings_window.destroy()
            else:
                messagebox.showwarning("Внимание", "Выберите настройку для активации!")

        def create_new_setting():
            try:
                selected_method = self.method_combo.get()
                if not selected_method:
                    messagebox.showerror("Ошибка", "Выберите метод сжатия!")
                    return
                    
                method_id = int(selected_method.split(':')[0])
                
                # Получаем значение лимита размера страницы (0 = None)
                kbytes_border = self.kbytes_per_page_border.get()
                if kbytes_border <= 0:
                    kbytes_border = None
                
                # Создание новой настройки на основе текущих значений UI
                new_setting = self.db_ops.create_setting(
                    nesting_depth_id=self.depth_level.get(),
                    need_replace=self.replace_original.get(),
                    compression_level=self.compression_level.get(),
                    compression_method_id=method_id,
                    compression_min_boundary=self.min_saving_threshold.get(),
                    procession_timeout=self.file_timeout.get(),
                    timeout_iterations=self.timeout_iterations.get(),
                    timeout_interval_secs=self.timeout_interval_secs.get(),
                    ocr_max_pages=self.ocr_max_pages.get(),
                    kbytes_per_page_border=kbytes_border,  # ✅ НОВОЕ
                    info=f"Создано {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    activate=True
                )
                messagebox.showinfo("Успех", f"Новая настройка создана (ID: {new_setting.id})!")
                self.load_active_settings()
                settings_window.destroy()
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать настройку: {str(e)}")

        def delete_selected():
            selection = settings_listbox.curselection()
            if selection:
                setting = all_settings[selection[0]]
                if setting.is_active:
                    messagebox.showerror("Ошибка", "Нельзя удалить активную настройку!")
                    return

                if messagebox.askyesno("Подтверждение", f"Удалить настройку ID{setting.id}?"):
                    # Проверяем, нет ли связанных записей
                    related_files = self.db.query(ProcessedFile).filter(
                        ProcessedFile.setting_id == setting.id
                    ).count()

                    if related_files > 0:
                        messagebox.showerror(
                            "Ошибка",
                            f"Нельзя удалить настройку, так как с ней связано {related_files} файлов!"
                        )
                        return

                    self.db.delete(setting)
                    self.db.commit()
                    messagebox.showinfo("Успех", "Настройка удалена!")
                    settings_window.destroy()

        ttk.Button(button_frame, text="Активировать выбранное", command=activate_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Создать новую настройку", command=create_new_setting).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Сохранить информацию", command=save_setting_info).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Удалить", command=delete_selected).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Закрыть", command=settings_window.destroy).pack(side=tk.LEFT, padx=5)

        # Показываем информацию о первой настройке, если есть
        if all_settings:
            settings_listbox.selection_set(0)
            update_info_display()

    def load_active_settings(self):
        """Загружает активные настройки из БД в UI"""
        self.active_setting = self.db_ops.get_active_setting()
        if self.active_setting:
            self.depth_level.set(self.active_setting.nesting_depth_id)
            self.replace_original.set(self.active_setting.need_replace)
            self.compression_level.set(self.active_setting.compression_level)
            self.min_saving_threshold.set(self.active_setting.compression_min_boundary)
            self.file_timeout.set(self.active_setting.procession_timeout)
            self.timeout_iterations.set(self.active_setting.timeout_iterations)
            self.timeout_interval_secs.set(self.active_setting.timeout_interval_secs)
            self.ocr_max_pages.set(self.active_setting.ocr_max_pages)
            
            # ✅ НОВОЕ
            if self.active_setting.kbytes_per_page_border is not None:
                self.kbytes_per_page_border.set(self.active_setting.kbytes_per_page_border)
            else:
                self.kbytes_per_page_border.set(0.0)  # 0 означает "не проверять"
            
            # Обновляем комбобокс метода сжатия
            if self.method_combo:
                methods = self.db_ops.get_all_compression_methods()
                for method in methods:
                    if method.id == self.active_setting.compression_method_id:
                        ocr_mark = " (OCR)" if method.is_ocr_enabled else ""
                        self.method_combo.set(f"{method.id}: {method.name}{ocr_mark}")
                        break

    def skip_current_file(self):
        """Пропускает текущий обрабатываемый файл"""
        if self.currently_processing and self.current_file_path:
            self.stop_current_file = True
            self.add_to_log(f"Пропуск файла по требованию пользователя: {os.path.basename(self.current_file_path)}",
                            "warning")

    def setup_log_file(self):
        """Создает или выбирает файл для логирования"""
        try:
            # Ищем существующие log-файлы
            log_files = glob.glob(os.path.join(self.logs_dir, "log_*.txt"))

            if log_files:
                # Берем последний файл
                latest_log = max(log_files, key=os.path.getctime)
                file_size = os.path.getsize(latest_log)

                if file_size < self.max_log_size:
                    self.current_log_file = latest_log
                    self.add_to_log(f"Продолжаем запись в журнал: {os.path.basename(latest_log)}")
                    return

            # Создаем новый файл
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            new_log_file = os.path.join(self.logs_dir, f"log_{timestamp}.txt")
            self.current_log_file = new_log_file

            # Записываем заголовок
            with open(self.current_log_file, 'w', encoding='utf-8') as f:
                f.write(f"PDF Compressor Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write("=" * 50 + "\n\n")

            self.add_to_log(f"Создан новый журнал: {os.path.basename(new_log_file)}")

        except Exception as e:
            self.add_to_log(f"Ошибка создания файла журнала: {e}", "error")
            self.current_log_file = None

    def save_to_log_file(self, message):
        """Сохраняет сообщение в файл журнала"""
        if not self.current_log_file:
            return

        try:
            # Проверяем размер файла
            if os.path.exists(self.current_log_file):
                file_size = os.path.getsize(self.current_log_file)
                if file_size >= self.max_log_size:
                    self.setup_log_file()  # Создаем новый файл

            # Записываем сообщение
            with open(self.current_log_file, 'a', encoding='utf-8') as f:
                f.write(message + "\n")

        except Exception as e:
            print(f"Ошибка записи в файл журнала: {e}")

    def check_log_files(self):
        """Проверяет количество файлов журналов и показывает предупреждение"""
        try:
            log_files = glob.glob(os.path.join(self.logs_dir, "log_*.txt"))
            if len(log_files) > 3:
                warning_text = f"Внимание! Количество журналов работы программы составляет {len(log_files)}.\nРекомендуется удалить лишние журналы, расположенные в директории:\n{self.logs_dir}"

                # Показываем предупреждение в интерфейсе
                warning_label = ttk.Label(self.root, text=warning_text, foreground="orange", wraplength=800)
                warning_label.grid(row=13, column=0, columnspan=3, pady=5, padx=5)

                self.add_to_log(warning_text, "warning")

        except Exception as e:
            self.add_to_log(f"Ошибка проверки журналов: {e}", "error")

    def check_ghostscript(self):
        """Проверяем установлен ли Ghostscript"""
        try:
            result = subprocess.run(['gs', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                self.add_to_log(f"Ghostscript найден: {result.stdout.strip()}")
                return True
        except:
            pass

        try:
            result = subprocess.run(['gswin64c', '--version'], capture_output=True, text=True)
            if result.returncode == 0:
                self.add_to_log(f"Ghostscript найден: {result.stdout.strip()}")
                return True
        except:
            pass

        self.add_to_log("⚠️  Ghostscript не найден! Установите его для работы программы", "warning")
        return False

    def on_method_changed(self, event=None):
        """Обновляет описание выбранного метода сжатия"""
        if not self.method_combo:
            return
            
        selected = self.method_combo.get()
        if selected:
            try:
                method_id = int(selected.split(':')[0])
                method = self.db_ops.get_compression_method_by_id(method_id)
                
                if method:
                    description = method.description or ""
                    
                    # Добавляем предупреждение для недоступных OCR методов
                    if method.is_ocr_enabled and not self.ocr_available:
                        description += " ⚠️ Tesseract не найден или не установлены зависимости!"
                        self.method_desc_label.config(foreground="orange")
                    else:
                        self.method_desc_label.config(foreground="gray")
                    
                    self.method_desc_label.config(text=description)
                    
                    # Отключаем/включаем уровень сжатия в зависимости от метода
                    if method_id in [4, 5]:  # OCR методы
                        if method_id == 5:
                            self.compression_level.set(2)
                    else:
                        if self.active_setting:
                            self.compression_level.set(self.active_setting.compression_level)
            except ValueError:
                pass

    def setup_ui(self):
        # Основной фрейм
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Настройка весов строк и столбцов для растягивания
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)

        # Выбор директории
        ttk.Label(main_frame, text="Директория:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.directory_path, width=50).grid(row=0, column=1, sticky=(tk.W, tk.E),
                                                                               pady=5, padx=5)
        ttk.Button(main_frame, text="Обзор", command=self.browse_directory).grid(row=0, column=2, pady=5, padx=5)

        # Глубина вложенности
        ttk.Label(main_frame, text="Глубина вложенности:").grid(row=1, column=0, sticky=tk.W, pady=5)
        depth_frame = ttk.Frame(main_frame)
        depth_frame.grid(row=1, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Radiobutton(depth_frame, text="Только текущая", variable=self.depth_level, value=1).pack(side=tk.LEFT)
        ttk.Radiobutton(depth_frame, text="1 уровень", variable=self.depth_level, value=2).pack(side=tk.LEFT)
        ttk.Radiobutton(depth_frame, text="2 уровня", variable=self.depth_level, value=3).pack(side=tk.LEFT)
        ttk.Radiobutton(depth_frame, text="Все поддиректории", variable=self.depth_level, value=4).pack(side=tk.LEFT)

        # Замена исходных файлов
        ttk.Checkbutton(main_frame, text="Заменять исходные файлы", variable=self.replace_original).grid(row=2,
                                                                                                         column=0,
                                                                                                         columnspan=2,
                                                                                                         sticky=tk.W,
                                                                                                         pady=5)

        # Уровень сжатия
        ttk.Label(main_frame, text="Уровень сжатия:").grid(row=3, column=0, sticky=tk.W, pady=5)
        compression_frame = ttk.Frame(main_frame)
        compression_frame.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Scale(compression_frame, from_=1, to=3, variable=self.compression_level, orient=tk.HORIZONTAL).pack(
            fill=tk.X)
        ttk.Label(compression_frame, textvariable=self.compression_level).pack()

        # Метод сжатия
        ttk.Label(main_frame, text="Метод сжатия:").grid(row=4, column=0, sticky=tk.W, pady=5)
        
        # Получаем все методы из БД
        methods = self.db_ops.get_all_compression_methods()
        method_frame = ttk.Frame(main_frame)
        method_frame.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5, columnspan=2)
        
        # Создаем выпадающий список
        self.method_combo = ttk.Combobox(method_frame, state="readonly", width=50)
        self.method_combo.grid(row=0, column=0, sticky=(tk.W, tk.E))
        
        # Заполняем значения
        method_values = []
        for method in methods:
            ocr_mark = " (OCR)" if method.is_ocr_enabled else ""
            method_values.append(f"{method.id}: {method.name}{ocr_mark}")
        
        self.method_combo['values'] = method_values
        
        # Устанавливаем активный метод или первый доступный
        if self.active_setting:
            for method in methods:
                if method.id == self.active_setting.compression_method_id:
                    ocr_mark = " (OCR)" if method.is_ocr_enabled else ""
                    self.method_combo.set(f"{method.id}: {method.name}{ocr_mark}")
                    break
        
        if not self.method_combo.get() and method_values:
            self.method_combo.set(method_values[0])
        
        # Добавляем описание метода
        self.method_desc_label = ttk.Label(method_frame, text="", foreground="gray", wraplength=600)
        self.method_desc_label.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        # Привязываем событие изменения выбора
        self.method_combo.bind('<<ComboboxSelected>>', self.on_method_changed)
        self.on_method_changed()

        # Порог минимального сжатия
        ttk.Label(main_frame, text="Минимальное сжатие (Б):").grid(row=5, column=0, sticky=tk.W, pady=5)
        threshold_frame = ttk.Frame(main_frame)
        threshold_frame.grid(row=5, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Spinbox(
            threshold_frame,
            from_=1,
            to=10000,
            increment=100,
            textvariable=self.min_saving_threshold,
            width=10
        ).pack(side=tk.LEFT)
        ttk.Label(threshold_frame, text="Б (1-10000)").pack(side=tk.LEFT, padx=5)

        # Таймаут обработки файла
        ttk.Label(main_frame, text="Таймаут файла (сек):").grid(row=6, column=0, sticky=tk.W, pady=5)
        timeout_frame = ttk.Frame(main_frame)
        timeout_frame.grid(row=6, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Spinbox(
            timeout_frame,
            from_=1,
            to=3600,
            increment=10,
            textvariable=self.file_timeout,
            width=10
        ).pack(side=tk.LEFT)
        ttk.Label(timeout_frame, text="сек (1-3600)").pack(side=tk.LEFT, padx=5)

        # Интервал итераций для таймаута
        ttk.Label(main_frame, text="Интервал итераций для таймаута (шт):").grid(row=7, column=0, sticky=tk.W, pady=5)
        iterations_frame = ttk.Frame(main_frame)
        iterations_frame.grid(row=7, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Spinbox(
            iterations_frame,
            from_=1,
            to=1000,
            increment=10,
            textvariable=self.timeout_iterations,
            width=10
        ).pack(side=tk.LEFT)
        ttk.Label(iterations_frame, text="шт (1-1000)").pack(side=tk.LEFT, padx=5)

        # Продолжительность интервального таймаута
        ttk.Label(main_frame, text="Продолжительность интервального таймаута (сек):").grid(row=8, column=0, sticky=tk.W, pady=5)
        interval_frame = ttk.Frame(main_frame)
        interval_frame.grid(row=8, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Spinbox(
            interval_frame,
            from_=1,
            to=60,
            increment=1,
            textvariable=self.timeout_interval_secs,
            width=10
        ).pack(side=tk.LEFT)
        ttk.Label(interval_frame, text="сек (1-60)").pack(side=tk.LEFT, padx=5)

        # Максимальное количество страниц для OCR
        ttk.Label(main_frame, text="Макс. страниц для OCR:").grid(row=9, column=0, sticky=tk.W, pady=5)
        ocr_pages_frame = ttk.Frame(main_frame)
        ocr_pages_frame.grid(row=9, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Spinbox(
            ocr_pages_frame,
            from_=1,
            to=1000,
            increment=10,
            textvariable=self.ocr_max_pages,
            width=10
        ).pack(side=tk.LEFT)
        ttk.Label(ocr_pages_frame, text="стр. (1-1000)").pack(side=tk.LEFT, padx=5)

        # ✅ НОВОЕ: Максимально допустимый размер страницы (КБ)
        ttk.Label(main_frame, text="Макс. размер страницы (КБ):").grid(row=10, column=0, sticky=tk.W, pady=5)
        border_frame = ttk.Frame(main_frame)
        border_frame.grid(row=10, column=1, sticky=(tk.W, tk.E), pady=5)

        kbytes_spinbox = ttk.Spinbox(
            border_frame,
            from_=0,
            to=10000,
            increment=50,
            textvariable=self.kbytes_per_page_border,
            width=10
        )
        kbytes_spinbox.pack(side=tk.LEFT)
        ttk.Label(border_frame, text="КБ (0 = не проверять)").pack(side=tk.LEFT, padx=5)

        # Пояснение
        border_hint = ttk.Label(
            border_frame, 
            text="Если размер страницы превышает лимит → файл пропускается",
            foreground="gray",
            font=("Arial", 8)
        )
        border_hint.pack(side=tk.LEFT, padx=10)

        # Кнопка запуска
        ttk.Button(main_frame, text="Начать сжатие", command=self.start_compression).grid(
            row=11, column=0, columnspan=3, pady=10
        )

        # Кнопка открытия папки с логами
        ttk.Button(main_frame, text="Открыть папку с журналами", command=self.open_logs_folder).grid(
            row=11, column=2, pady=10, sticky=tk.E
        )
        
        # Кнопка инструкции
        ttk.Button(main_frame, text="📖 ИНСТРУКЦИЯ",
                   command=self.show_instructions).grid(row=12, column=0, pady=10, sticky=tk.W)
        ttk.Button(main_frame, text="Статистика сжатия",
                   command=self.show_stats).grid(row=12, column=1, pady=10)

        # Кнопка управления настройками
        self.settings_button.grid(row=12, column=2, pady=10, sticky=tk.E)

        # Кнопка пропуска файла
        self.skip_button.grid(row=13, column=0, columnspan=2, pady=5)

        # Журнал операций
        ttk.Label(main_frame, text="Журнал операций:").grid(row=14, column=0, sticky=tk.W, pady=5)
        self.log_text.grid(row=15, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=5)
        self.log_scrollbar.grid(row=15, column=3, sticky=(tk.N, tk.S), pady=5)

        # Статистика
        stats_frame = ttk.Frame(main_frame)
        stats_frame.grid(row=16, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(stats_frame, text="Обработано:").grid(row=0, column=0, padx=5)
        self.files_count_label.grid(row=0, column=1, padx=5)

        ttk.Label(stats_frame, text="Пропущено:").grid(row=0, column=2, padx=5)
        self.skipped_label.grid(row=0, column=3, padx=5)

        ttk.Label(stats_frame, text="Ошибки:").grid(row=0, column=4, padx=5)
        self.failed_label.grid(row=0, column=5, padx=5)

        ttk.Label(stats_frame, text="Сэкономлено:").grid(row=0, column=6, padx=5)
        self.saved_label.grid(row=0, column=7, padx=5)

        ttk.Label(stats_frame, text="Степень сжатия:").grid(row=0, column=8, padx=5)
        self.ratio_label.grid(row=0, column=9, padx=5)

        # Информация о инструментах
        info_label = ttk.Label(main_frame, 
                              text="Для работы программы требуется установленный Ghostscript. Для OCR методов также нужен Tesseract.",
                              foreground="blue")
        info_label.grid(row=17, column=0, columnspan=3, pady=5)

        # Настройка весов для растягивания
        main_frame.rowconfigure(14, weight=1)

    def open_logs_folder(self):
        """Открывает папку с логами в проводнике"""
        try:
            if os.name == 'nt':  # Windows
                os.startfile(self.logs_dir)
            elif os.name == 'posix':  # macOS, Linux
                subprocess.run(
                    ['open', self.logs_dir] if os.uname().sysname == 'Darwin' else ['xdg-open', self.logs_dir])
            self.add_to_log(f"Открыта папка с журналами: {self.logs_dir}")
        except Exception as e:
            self.add_to_log(f"Ошибка открытия папки с журналами: {e}", "error")

    def browse_directory(self):
        directory = filedialog.askdirectory()
        if directory:
            self.directory_path.set(directory)
            self.add_to_log(f"Выбрана директория: {directory}")

    def add_to_log(self, message, level="info"):
        """Добавляет сообщение в лог и сохраняет в файл"""
        self.log_text.config(state=tk.NORMAL)
        timestamp = datetime.now().strftime("%H:%M:%S")

        if level == "warning":
            prefix = "⚠️  "
            tag = "warning"
        elif level == "error":
            prefix = "❌ "
            tag = "error"
        elif level == "success":
            prefix = "✅ "
            tag = "success"
        else:
            prefix = "ℹ️  "
            tag = "info"

        log_message = f"[{timestamp}] {prefix}{message}"
        self.log_text.insert(tk.END, log_message + "\n", tag)

        self.log_text.tag_config("warning", foreground="orange")
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.tag_config("info", foreground="blue")

        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

        # Сохраняем в файл
        file_message = f"[{timestamp}] {message}"
        self.save_to_log_file(file_message)

    def update_stats(self):
        self.files_count_label.config(text=str(self.processed_files))
        self.skipped_label.config(text=str(self.skipped_files))
        self.failed_label.config(text=str(self.failed_files))

        saved = self.total_original_size - self.total_compressed_size
        self.saved_label.config(text=f"{saved / (1024 * 1024):.2f} MB")

        if self.total_original_size > 0:
            ratio = (1 - self.total_compressed_size / self.total_original_size) * 100
            self.ratio_label.config(text=f"{ratio:.1f}%")

    def create_temp_file_path(self, extension=".pdf"):
        """Создает временный файл с ASCII-именем"""
        temp_dir = tempfile.gettempdir()
        temp_name = f"pdf_compress_{uuid.uuid4().hex}{extension}"
        return os.path.join(temp_dir, temp_name)

    def copy_network_file_to_local(self, network_path):
        """Копирует файл из сетевой папки на локальный диск"""
        try:
            local_temp_path = self.create_temp_file_path()
            shutil.copy2(network_path, local_temp_path)
            return local_temp_path
        except Exception as e:
            self.add_to_log(f"Ошибка копирования сетевого файла: {e}", "error")
            return None

    def compress_with_ghostscript(self, input_path, output_path, compression_level):
        """Сжатие с использованием Ghostscript - профессиональный метод"""
        temp_input = None
        temp_output = None

        try:
            # Проверяем, является ли путь сетевым
            if input_path.startswith('\\\\') or '://' in input_path:
                temp_input = self.copy_network_file_to_local(input_path)
                if not temp_input:
                    return False
            else:
                temp_input = self.create_temp_file_path()
                shutil.copy2(input_path, temp_input)

            temp_output = self.create_temp_file_path()

            gs_command = 'gswin64c' if os.name == 'nt' else 'gs'

            if compression_level == 1:
                settings = [
                    '-dPDFSETTINGS=/screen',
                    '-dDownsampleColorImages=true',
                    '-dColorImageResolution=72',
                    '-dGrayImageResolution=72',
                    '-dMonoImageResolution=72'
                ]
            elif compression_level == 2:
                settings = [
                    '-dPDFSETTINGS=/ebook',
                    '-dDownsampleColorImages=true',
                    '-dColorImageResolution=150',
                    '-dGrayImageResolution=150',
                    '-dMonoImageResolution=150'
                ]
            else:
                settings = [
                    '-dPDFSETTINGS=/prepress',
                    '-dDownsampleColorImages=true',
                    '-dColorImageResolution=300',
                    '-dGrayImageResolution=300',
                    '-dMonoImageResolution=300'
                ]

            command = [
                gs_command,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.4',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                *settings,
                '-sOutputFile=' + temp_output,
                temp_input
            ]

            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.file_timeout.get()
            )

            if result.returncode == 0:
                shutil.copy2(temp_output, output_path)
                return True
            else:
                self.add_to_log(f"Ошибка Ghostscript: {result.stderr}", "error")
                return False

        except subprocess.TimeoutExpired:
            self.add_to_log(f"Таймаут обработки файла: {input_path}", "error")
            return False
        except Exception as e:
            self.add_to_log(f"Ошибка сжатия Ghostscript: {e}", "error")
            return False
        finally:
            try:
                if temp_input and os.path.exists(temp_input):
                    os.remove(temp_input)
                if temp_output and os.path.exists(temp_output):
                    os.remove(temp_output)
            except Exception as e:
                self.add_to_log(f"Ошибка удаления временных файлов: {e}", "warning")

    def compress_pdf(self, input_path, output_path):
        """Основная функция сжатия PDF с поддержкой OCR"""
        try:
            original_size = os.path.getsize(input_path)
            
            selected_method = self.method_combo.get()
            if not selected_method:
                self.add_to_log("Метод сжатия не выбран!", "error")
                return False, 0
                
            method_id = int(selected_method.split(':')[0])
            
            success = False
            saving = 0
            
            if method_id == 4:  # Tesseract OCR
                if not self.ocr_available:
                    self.add_to_log("OCR недоступен. Установите Tesseract и зависимости.", "error")
                    return False, 0
                    
                success = self.ocr_processor.process_with_tesseract(input_path, output_path)
                
            elif method_id == 5:  # Tesseract + Ghostscript
                if not self.ocr_available:
                    self.add_to_log("OCR недоступен. Установите Tesseract и зависимости.", "error")
                    return False, 0
                    
                success = self.ocr_processor.process_with_tesseract_and_ghostscript(
                    input_path, 
                    output_path,
                    self.compression_level.get()
                )
                
            elif method_id in [1, 2, 3]:  # Стандартные методы Ghostscript
                success = self.compress_with_ghostscript(input_path, output_path, self.compression_level.get())
                
            else:
                self.add_to_log(f"Неизвестный метод сжатия: {method_id}", "error")
                return False, 0
            
            if success:
                compressed_size = os.path.getsize(output_path)
                saving = original_size - compressed_size
                min_saving = self.min_saving_threshold.get()
                
                if saving >= min_saving:
                    return True, saving
                else:
                    self.add_to_log(
                        f"Сжатие недостаточно: {saving} Б < {min_saving} Б (порог). Файл не будет заменен.",
                        "warning"
                    )
                    return False, saving
            else:
                return False, 0
                
        except Exception as e:
            self.add_to_log(f"Ошибка сжатия PDF: {e}", "error")
            return False, 0

    # ✅ НОВЫЙ МЕТОД: проверка размера страницы
    def check_page_size_limit(self, file_path):
        """
        Проверяет, не МЕНЬШЕ ли размер страницы установленного лимита.
        Если размер страницы НИЖЕ лимита - файл пропускается (он уже достаточно сжат).
        Возвращает (True, pages, size_kbytes, avg_page_size) если проверка пройдена,
        или (False, pages, size_kbytes, avg_page_size) если файл нужно пропустить.
        """
        border = self.kbytes_per_page_border.get()
        
        # Если лимит не установлен (0 или None) - пропускаем проверку
        if not border or border <= 0:
            return True, None, None, None
        
        try:
            # Получаем количество страниц
            try:
                from PyPDF2 import PdfReader
                PYPDF2_AVAILABLE = True
            except ImportError:
                PYPDF2_AVAILABLE = False
                self.add_to_log("PyPDF2 не установлен. Невозможно проверить размер страницы.", "warning")
                return True, None, None, None
            
            if PYPDF2_AVAILABLE:
                with open(file_path, 'rb') as f:
                    reader = PdfReader(f)
                    num_pages = len(reader.pages)
                
                # Получаем размер файла в КБ
                file_size_bytes = os.path.getsize(file_path)
                file_size_kbytes = file_size_bytes / 1024.0
                
                # Рассчитываем средний размер страницы
                if num_pages > 0:
                    avg_page_size = file_size_kbytes / num_pages
                    
                    self.add_to_log(
                        f"📄 Страниц: {num_pages}, размер: {file_size_kbytes:.1f} КБ, "
                        f"средний: {avg_page_size:.1f} КБ/стр, лимит: {border} КБ/стр",
                        "info"
                    )
                    
                    # ✅ ИСПРАВЛЕНО: Пропускаем, если размер страницы МЕНЬШЕ лимита
                    if avg_page_size < border:
                        self.add_to_log(
                            f"⏭️ Файл уже хорошо сжат: {avg_page_size:.1f} < {border} КБ/стр. "
                            f"Пропускаем (нецелесообразно сжимать).",
                            "warning"
                        )
                        return False, num_pages, file_size_kbytes, avg_page_size
                
                return True, num_pages, file_size_kbytes, avg_page_size
                
        except Exception as e:
            self.add_to_log(f"Не удалось проверить размер страницы: {e}", "warning")
        
        return True, None, None, None

    # compressor_app.py - фрагмент метода process_single_file

    def process_single_file(self, file_path):
        """Обрабатывает один файл"""
        self.current_file_path = file_path
        self.currently_processing = True
        self.stop_current_file = False
        self.processing_start_time = time.time()
        
        # Инициализируем переменные
        file_size_bytes = 0
        file_size_kbytes = 0
        num_pages = None
        avg_page_size = None

        try:
            # ===== ЗАЩИТА: проверяем доступность файла =====
            if not os.path.exists(file_path):
                self.failed_files += 1
                error_msg = f"Файл не найден или недоступен: {file_path}"
                self.add_to_log(f"❌ {error_msg}", "error")
                
                # Сохраняем в БД
                try:
                    # ВАЖНО: сначала проверяем, нет ли уже такой записи
                    existing = self.db_ops.get_processed_file_by_path(file_path)
                    if not existing:
                        fail_reason = self.db_ops.get_fail_reason_by_name("прочая причина")
                        active_setting = self.db_ops.get_active_setting()
                        setting_id = active_setting.id if active_setting else 1
                        
                        self.db_ops.create_processed_file(
                            file_full_path=file_path,
                            is_successful=False,
                            setting_id=setting_id,
                            file_compression_kbites=0.0,
                            fail_reason_id=fail_reason.id if fail_reason else None,
                            other_fail_reason=f"Файл недоступен: {error_msg}",
                            file_pages=None,
                            file_origin_size_kbytes=None
                        )
                    else:
                        self.add_to_log(f"⚠️ Запись уже существует в БД для: {os.path.basename(file_path)}", "warning")
                except Exception as e:
                    self.add_to_log(f"⚠️ Ошибка сохранения в БД: {e}", "warning")
                    # Важно! Откатываем сессию после ошибки
                    try:
                        self.db.rollback()
                    except:
                        pass
                
                self.update_stats()
                return

            # Получаем базовую информацию о файле...
            try:
                file_size_bytes = os.path.getsize(file_path)
                file_size_kbytes = file_size_bytes / 1024.0
            except Exception as e:
                self.failed_files += 1
                self.add_to_log(f"❌ Не удалось получить размер файла {os.path.basename(file_path)}: {e}", "error")
                
                # Сохраняем в БД...
                try:
                    existing = self.db_ops.get_processed_file_by_path(file_path)
                    if not existing:
                        fail_reason = self.db_ops.get_fail_reason_by_name("прочая причина")
                        active_setting = self.db_ops.get_active_setting()
                        setting_id = active_setting.id if active_setting else 1
                        
                        self.db_ops.create_processed_file(
                            file_full_path=file_path,
                            is_successful=False,
                            setting_id=setting_id,
                            file_compression_kbites=0.0,
                            fail_reason_id=fail_reason.id if fail_reason else None,
                            other_fail_reason=f"Ошибка получения размера файла: {str(e)}",
                            file_pages=None,
                            file_origin_size_kbytes=None
                        )
                except Exception as db_e:
                    self.add_to_log(f"⚠️ Ошибка сохранения в БД: {db_e}", "warning")
                    try:
                        self.db.rollback()
                    except:
                        pass
                
                self.update_stats()
                return

            # Проверяем, не обрабатывался ли файл ранее
            try:
                processed_file = self.db_ops.get_processed_file_by_path(file_path)
                if processed_file:
                    self.skipped_files += 1
                    self.add_to_log(f"⏭️ Файл уже обрабатывался ранее: {os.path.basename(file_path)}", "warning")
                    self.update_stats()
                    return
            except Exception as e:
                self.add_to_log(f"⚠️ Ошибка проверки дубликата для {os.path.basename(file_path)}: {e}", "warning")
                # Пробуем восстановить сессию
                try:
                    self.db.rollback()
                except:
                    pass
                # Продолжаем обработку, если не можем проверить дубликат

            # Проверяем минимальный размер файла (1 МБ)
            min_size_bytes = 1024 * 1024
            if file_size_bytes < min_size_bytes:
                self.skipped_files += 1
                file_size_mb = file_size_bytes / (1024 * 1024)
                self.add_to_log(
                    f"⏭️ Пропуск файла (меньше 1 МБ): {os.path.basename(file_path)} "
                    f"(размер: {file_size_mb:.2f} МБ)", 
                    "warning"
                )
                
                # Сохраняем в БД информацию о пропуске
                try:
                    existing = self.db_ops.get_processed_file_by_path(file_path)
                    if not existing:
                        active_setting = self.db_ops.get_active_setting()
                        setting_id = active_setting.id if active_setting else 1
                        
                        self.db_ops.create_processed_file(
                            file_full_path=file_path,
                            is_successful=False,
                            setting_id=setting_id,
                            file_compression_kbites=0.0,
                            fail_reason_id=None,
                            other_fail_reason=f"Файл меньше 1 МБ ({file_size_mb:.2f} МБ)",
                            file_pages=None,
                            file_origin_size_kbytes=file_size_kbytes
                        )
                except Exception as e:
                    self.add_to_log(f"⚠️ Ошибка сохранения в БД: {e}", "warning")
                    try:
                        self.db.rollback()
                    except:
                        pass
                
                self.update_stats()
                return

            # ===== ПРОВЕРКА 1: ЛИМИТ РАЗМЕРА СТРАНИЦЫ =====
            try:
                page_check_ok, num_pages, file_size_kbytes, avg_page_size = self.check_page_size_limit(file_path)
                if not page_check_ok:
                    self.skipped_files += 1
                    
                    # Сохраняем в БД с указанием причины
                    try:
                        existing = self.db_ops.get_processed_file_by_path(file_path)
                        if not existing:
                            fail_reason = self.db_ops.get_fail_reason_by_name("превышен лимит размера страницы")
                            active_setting = self.db_ops.get_active_setting()
                            setting_id = active_setting.id if active_setting else 1
                            
                            border = self.kbytes_per_page_border.get()
                            other_reason = f"Файл пропущен: размер страницы {avg_page_size:.2f} КБ/стр < лимита {border:.2f} КБ/стр (уже хорошо сжат)"
                            
                            self.db_ops.create_processed_file(
                                file_full_path=file_path,
                                is_successful=False,
                                setting_id=setting_id,
                                file_compression_kbites=0.0,
                                fail_reason_id=fail_reason.id if fail_reason else None,
                                other_fail_reason=other_reason,
                                file_pages=num_pages,
                                file_origin_size_kbytes=file_size_kbytes
                            )
                    except Exception as e:
                        self.add_to_log(f"⚠️ Ошибка сохранения в БД: {e}", "warning")
                        try:
                            self.db.rollback()
                        except:
                            pass
                    
                    self.update_stats()
                    return
            except Exception as e:
                self.add_to_log(f"⚠️ Ошибка проверки лимита страницы для {os.path.basename(file_path)}: {e}", "warning")
                try:
                    self.db.rollback()
                except:
                    pass
                page_check_ok = True

            # ===== ПРОВЕРКА 2: OCR МЕТОДЫ И МАКС. СТРАНИЦ =====
            try:
                selected_method = self.method_combo.get()
                method_id = int(selected_method.split(':')[0]) if selected_method else 0
                
                method = self.db_ops.get_compression_method_by_id(method_id)
                if method and method.is_ocr_enabled:
                    # Если еще не получили количество страниц
                    if num_pages is None:
                        try:
                            from PyPDF2 import PdfReader
                            with open(file_path, 'rb') as f:
                                reader = PdfReader(f)
                                num_pages = len(reader.pages)
                        except Exception as e:
                            self.add_to_log(f"⚠️ Не удалось определить количество страниц для OCR: {e}", "warning")
                            num_pages = 0
                    
                    max_pages = self.ocr_max_pages.get()
                    
                    if num_pages > max_pages:
                        self.skipped_files += 1
                        self.add_to_log(
                            f"⏭️ Пропуск OCR-файла (страниц: {num_pages} > {max_pages}): {os.path.basename(file_path)}",
                            "warning"
                        )
                        
                        try:
                            existing = self.db_ops.get_processed_file_by_path(file_path)
                            if not existing:
                                fail_reason = self.db_ops.get_fail_reason_by_name("прочая причина")
                                active_setting = self.db_ops.get_active_setting()
                                setting_id = active_setting.id if active_setting else 1
                                
                                self.db_ops.create_processed_file(
                                    file_full_path=file_path,
                                    is_successful=False,
                                    setting_id=setting_id,
                                    file_compression_kbites=0.0,
                                    fail_reason_id=fail_reason.id if fail_reason else None,
                                    other_fail_reason=f"{num_pages} fact pages in file > {max_pages}",
                                    file_pages=num_pages,
                                    file_origin_size_kbytes=file_size_kbytes
                                )
                        except Exception as e:
                            self.add_to_log(f"⚠️ Ошибка сохранения в БД: {e}", "warning")
                            try:
                                self.db.rollback()
                            except:
                                pass
                        
                        self.update_stats()
                        return
            except Exception as e:
                self.add_to_log(f"⚠️ Ошибка проверки OCR для {os.path.basename(file_path)}: {e}", "warning")
                try:
                    self.db.rollback()
                except:
                    pass

            # Создаем временный файл для результата...
            temp_output = None
            try:
                temp_dir = tempfile.gettempdir()
                temp_output = os.path.join(temp_dir, f"temp_compress_{uuid.uuid4().hex}.pdf")
            except Exception as e:
                self.failed_files += 1
                self.add_to_log(f"❌ Не удалось создать временный файл: {e}", "error")
                
                # Сохраняем в БД
                try:
                    existing = self.db_ops.get_processed_file_by_path(file_path)
                    if not existing:
                        fail_reason = self.db_ops.get_fail_reason_by_name("прочая причина")
                        active_setting = self.db_ops.get_active_setting()
                        setting_id = active_setting.id if active_setting else 1
                        
                        self.db_ops.create_processed_file(
                            file_full_path=file_path,
                            is_successful=False,
                            setting_id=setting_id,
                            file_compression_kbites=0.0,
                            fail_reason_id=fail_reason.id if fail_reason else None,
                            other_fail_reason=f"Ошибка создания временного файла: {str(e)}",
                            file_pages=num_pages,
                            file_origin_size_kbytes=file_size_kbytes
                        )
                except Exception as db_e:
                    self.add_to_log(f"⚠️ Ошибка сохранения в БД: {db_e}", "warning")
                    try:
                        self.db.rollback()
                    except:
                        pass
                
                self.update_stats()
                return

            # Сжимаем файл...
            try:
                self.add_to_log(f"🔄 Обработка: {os.path.basename(file_path)}")
                success, saving = self.compress_pdf(file_path, temp_output)
            except Exception as e:
                self.failed_files += 1
                self.add_to_log(f"❌ Критическая ошибка при сжатии {os.path.basename(file_path)}: {e}", "error")
                self.add_to_log(traceback.format_exc(), "error")
                success = False
                saving = 0

            if self.stop_current_file:
                self.add_to_log(f"⏹️ Обработка прервана пользователем: {os.path.basename(file_path)}", "warning")
                try:
                    if temp_output and os.path.exists(temp_output):
                        os.remove(temp_output)
                except:
                    pass
                return

            if success:
                # Заменяем исходный файл...
                if self.replace_original.get():
                    backup_path = None
                    try:
                        backup_path = file_path + '.backup'
                        shutil.copy2(file_path, backup_path)
                        shutil.move(temp_output, file_path)
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                    except Exception as e:
                        self.add_to_log(f"⚠️ Ошибка замены файла: {e}", "error")
                        if backup_path and os.path.exists(backup_path):
                            try:
                                shutil.move(backup_path, file_path)
                            except:
                                pass
                        success = False

                if success:
                    # Обновляем статистику
                    self.processed_files += 1
                    try:
                        self.total_original_size += os.path.getsize(file_path) + saving
                        self.total_compressed_size += os.path.getsize(file_path)
                    except:
                        pass

                    # Сохраняем в БД
                    try:
                        existing = self.db_ops.get_processed_file_by_path(file_path)
                        if not existing:
                            selected_method = self.method_combo.get()
                            method_id = int(selected_method.split(':')[0]) if selected_method else 1
                            
                            active_setting = self.db_ops.get_active_setting()
                            setting_id = active_setting.id if active_setting else 1

                            self.db_ops.create_processed_file(
                                file_full_path=file_path,
                                is_successful=True,
                                setting_id=setting_id,
                                file_compression_kbites=saving / 1024,
                                file_pages=num_pages,
                                file_origin_size_kbytes=file_size_kbytes
                            )
                    except Exception as e:
                        self.add_to_log(f"⚠️ Ошибка сохранения в БД: {e}", "warning")
                        try:
                            self.db.rollback()
                        except:
                            pass

                    self.add_to_log(f"✅ Успешно сжат: {os.path.basename(file_path)} (экономия: {saving / 1024:.2f} KB)",
                                    "success")
                else:
                    self.failed_files += 1
                    self.add_to_log(f"❌ Не удалось сжать: {os.path.basename(file_path)}", "error")
                    
                    # Сохраняем в БД
                    try:
                        existing = self.db_ops.get_processed_file_by_path(file_path)
                        if not existing:
                            active_setting = self.db_ops.get_active_setting()
                            setting_id = active_setting.id if active_setting else 1
                            
                            self.db_ops.create_processed_file(
                                file_full_path=file_path,
                                is_successful=False,
                                setting_id=setting_id,
                                file_compression_kbites=0.0,
                                fail_reason_id=None,
                                other_fail_reason="Ошибка сжатия",
                                file_pages=num_pages,
                                file_origin_size_kbytes=file_size_kbytes
                            )
                    except Exception as e:
                        self.add_to_log(f"⚠️ Ошибка сохранения в БД: {e}", "warning")
                        try:
                            self.db.rollback()
                        except:
                            pass

            else:
                self.failed_files += 1

                # Определяем причину ошибки
                fail_reason = None
                other_fail_reason = None

                try:
                    if saving > 0 and saving < self.min_saving_threshold.get():
                        fail_reason = self.db_ops.get_fail_reason_by_name("размер увеличился при сжатии")
                    elif time.time() - self.processing_start_time > self.file_timeout.get():
                        fail_reason = self.db_ops.get_fail_reason_by_name("превышен таймаут обработки файла")
                    else:
                        fail_reason = self.db_ops.get_fail_reason_by_name("прочая причина")
                        other_fail_reason = traceback.format_exc()
                except:
                    other_fail_reason = traceback.format_exc()

                # Сохраняем в БД
                try:
                    existing = self.db_ops.get_processed_file_by_path(file_path)
                    if not existing:
                        active_setting = self.db_ops.get_active_setting()
                        setting_id = active_setting.id if active_setting else 1

                        self.db_ops.create_processed_file(
                            file_full_path=file_path,
                            is_successful=False,
                            setting_id=setting_id,
                            file_compression_kbites=0.0,
                            fail_reason_id=fail_reason.id if fail_reason else None,
                            other_fail_reason=other_fail_reason,
                            file_pages=num_pages,
                            file_origin_size_kbytes=file_size_kbytes
                        )
                except Exception as e:
                    self.add_to_log(f"⚠️ Ошибка сохранения в БД: {e}", "warning")
                    try:
                        self.db.rollback()
                    except:
                        pass

                self.add_to_log(f"❌ Не удалось сжать: {os.path.basename(file_path)}", "error")

            # Удаляем временный файл
            try:
                if temp_output and os.path.exists(temp_output):
                    os.remove(temp_output)
            except Exception as e:
                self.add_to_log(f"⚠️ Ошибка удаления временного файла: {e}", "warning")

        except Exception as e:
            # Глобальная обработка ошибок
            self.failed_files += 1
            error_msg = f"Критическая ошибка обработки {os.path.basename(file_path)}: {str(e)}"
            self.add_to_log(f"❌ {error_msg}", "error")
            self.add_to_log(traceback.format_exc(), "error")

            # Сохраняем в БД с прочей причиной
            try:
                # ВАЖНО: Сначала пробуем восстановить сессию
                try:
                    self.db.rollback()
                except:
                    pass
                    
                existing = self.db_ops.get_processed_file_by_path(file_path)
                if not existing:
                    fail_reason = self.db_ops.get_fail_reason_by_name("прочая причина")
                    active_setting = self.db_ops.get_active_setting()
                    setting_id = active_setting.id if active_setting else 1

                    self.db_ops.create_processed_file(
                        file_full_path=file_path,
                        is_successful=False,
                        setting_id=setting_id,
                        file_compression_kbites=0.0,
                        fail_reason_id=fail_reason.id if fail_reason else None,
                        other_fail_reason=f"Критическая ошибка: {str(e)[:200]}",
                        file_pages=num_pages,
                        file_origin_size_kbytes=file_size_kbytes if file_size_kbytes > 0 else None
                    )
            except Exception as db_e:
                self.add_to_log(f"⚠️ Критическая ошибка БД: {db_e}", "error")
                try:
                    self.db.rollback()
                except:
                    pass

        finally:
            self.currently_processing = False
            self.current_file_path = None
            self.update_stats()


    def find_pdf_files(self, directory, depth):
        """Находит PDF файлы в директории с учетом глубины вложенности"""
        pdf_files = []
        current_depth = 0

        for root, dirs, files in os.walk(directory):
            # Вычисляем текущую глубину
            current_depth = root[len(directory):].count(os.sep)

            # Проверяем глубину в соответствии с настройками
            if depth == 1 and current_depth > 0:  # Только текущая
                continue
            elif depth == 2 and current_depth > 1:  # 1 уровень
                continue
            elif depth == 3 and current_depth > 2:  # 2 уровня
                continue
            # depth == 4: все поддиректории - не ограничиваем

            for file in files:
                if file.lower().endswith('.pdf'):
                    pdf_files.append(os.path.join(root, file))

        return pdf_files

    def start_compression(self):
        """Запускает процесс сжатия в отдельном потоке"""
        if not self.directory_path.get():
            messagebox.showerror("Ошибка", "Выберите директорию для обработки")
            return

        if not os.path.exists(self.directory_path.get()):
            messagebox.showerror("Ошибка", "Указанная директория не существует")
            return

        # Проверяем выбранный метод
        selected_method = self.method_combo.get()
        if not selected_method:
            messagebox.showerror("Ошибка", "Выберите метод сжатия")
            return
            
        method_id = int(selected_method.split(':')[0])
        
        # Проверяем доступность OCR методов
        if method_id in [4, 5] and not self.ocr_available:
            messagebox.showerror("Ошибка", 
                "OCR методы недоступны.\n\n"
                "Установите:\n"
                "1. pip install pytesseract pdf2image PyPDF2 Pillow\n"
                "2. apt install tesseract-ocr tesseract-ocr-rus poppler-utils\n"
                "3. Проверьте установку Tesseract: tesseract --version")
            return

        # Обновляем активные настройки
        self.load_active_settings()

        # Сбрасываем статистику
        self.processed_files = 0
        self.skipped_files = 0
        self.failed_files = 0
        self.total_original_size = 0
        self.total_compressed_size = 0
        self.update_stats()

        # Настраиваем файл журнала
        self.setup_log_file()

        # Активируем кнопку пропуска
        self.skip_button.config(state=tk.NORMAL)

        # Запускаем в отдельном потоке
        thread = threading.Thread(target=self.process_directory)
        thread.daemon = True
        thread.start()

    def process_directory(self):
        """Обрабатывает все PDF файлы в директории"""
        try:
            directory = self.directory_path.get()
            depth = self.depth_level.get()

            self.add_to_log(f"Начало обработки директории: {directory}")
            self.add_to_log(f"Глубина вложенности: {depth}")
            
            # Показываем выбранный метод
            selected_method = self.method_combo.get()
            self.add_to_log(f"Метод сжатия: {selected_method}")
            
            # Показываем лимит размера страницы
            border = self.kbytes_per_page_border.get()
            if border and border > 0:
                self.add_to_log(f"Лимит размера страницы: {border} КБ/стр (файлы с превышением будут пропущены)", "info")
            else:
                self.add_to_log("Лимит размера страницы: отключен", "info")

            # Находим все PDF файлы
            pdf_files = self.find_pdf_files(directory, depth)
            total_files = len(pdf_files)

            self.add_to_log(f"Найдено PDF файлов: {total_files}")

            # Обрабатываем каждый файл
            counter = 0
            for i, file_path in enumerate(pdf_files, 1):
                if counter % self.timeout_iterations.get() == 0:
                    time.sleep(self.timeout_interval_secs.get())
                counter += 1
                if self.stop_current_file:
                    break

                self.add_to_log(f"Прогресс: {i}/{total_files}")
                self.process_single_file(file_path)

            # Финальное сообщение
            if self.stop_current_file:
                self.add_to_log("Обработка прервана пользователем", "warning")
            else:
                self.add_to_log("Обработка завершена!", "success")

        except Exception as e:
            self.add_to_log(f"Ошибка обработки директории: {e}", "error")
        finally:
            # Деактивируем кнопку пропуска
            self.skip_button.config(state=tk.DISABLED)

    def show_stats(self):
        """Показать окно статистики"""
        StatsWindow(self.root)
    
    # Метод show_instructions(self) не включен - он остается без изменений

    def show_instructions(self):
        """Показать инструкцию по использованию программы"""
        instructions_text = """
        📖 ИНСТРУКЦИЯ ПО ИСПОЛЬЗОВАНИЮ PDF COMPRESSOR PRO
        (Версия 2.1 - с интеллектуальным анализом страниц)
        
        🎯 ОСНОВНЫЕ ВОЗМОЖНОСТИ:
        • Интеллектуальное сжатие PDF файлов с помощью Ghostscript
        • OCR обработка с помощью Tesseract (распознавание текста в сканах)
        • Обработка отдельных файлов и целых папок
        • Гибкие настройки сжатия с сохранением пресетов
        • Полная история обработки в базе данных
        • Защита от повторной обработки файлов
        • ✅ НОВОЕ: Анализ размера страницы и интеллектуальный пропуск
        • ✅ НОВОЕ: Детальная статистика по страницам и размеру
        
        🚀 БЫСТРЫЙ СТАРТ:

        1. ВЫБОР ДИРЕКТОРИИ
        • Нажмите кнопку "Обзор" и выберите папку с PDF файлами
        • Программа автоматически найдет все PDF файлы в выбранной директории

        2. НАСТРОЙКА ПАРАМЕТРОВ:

        МЕТОД СЖАТИЯ:
        • Ghostscript - профессиональное сжатие (рекомендуется для обычных PDF)
        • Стандартное - базовое сжатие
        • Только изображения - оптимизация изображений в PDF
        • Tesseract OCR - создание поисковых PDF из сканов (нужен Tesseract)
        • Tesseract + Ghostscript - OCR + последующее сжатие (нужен Tesseract)

        ⚠️ НОВАЯ ФУНКЦИЯ: МАКСИМАЛЬНЫЙ РАЗМЕР СТРАНИЦЫ (КБ)
        • Позволяет отсеивать "тяжелые" файлы, которые невыгодно сжимать
        • Рассчитывается как (размер файла в КБ) / (количество страниц)
        • Если средний размер страницы превышает лимит → файл пропускается
        • Значение 0 (ноль) = отключить проверку
        • Рекомендации:
            - Для обычных PDF (текст+графика): 50-100 КБ/стр
            - Для сканов в хорошем качестве: 200-300 КБ/стр
            - Для цветных сканов высокого разрешения: 500+ КБ/стр

        ЗАЧЕМ ЭТО НУЖНО:
        • Экономия времени - не тратим ресурсы на заведомо невыгодные файлы
        • Сбор статистики - программа запоминает размер и количество страниц
        • Аналитика - позже можно определить оптимальный порог для ваших документов
        • Прозрачность - видите реальную эффективность сжатия

        ГЛУБИНА ВЛОЖЕННОСТИ:
        • "Только текущая" - обрабатывает файлы только в выбранной папке
        • "1 уровень" - обрабатывает файлы в папке и ее непосредственных подпапках
        • "2 уровня" - обрабатывает файлы до 2 уровней вложенности
        • "Все поддиректории" - обрабатывает все файлы в подпапках любого уровня

        ЗАМЕНА ИСХОДНЫХ ФАЙЛОВ:
        • Включено - исходные файлы заменяются сжатыми версиями
        • Выключено - создаются копии файлов (не реализовано в текущей версии)

        УРОВЕНЬ СЖАТИЯ:
        • 1 (Экономный) - максимальное сжатие, подходит для веб-публикаций
        • 2 (Стандартный) - баланс качества и размера (рекомендуется)
        • 3 (Максимальный) - лучшее качество, умеренное сжатие

        МИНИМАЛЬНОЕ СЖАТИЕ (Б):
        • Укажите минимальный размер экономии в байтах
        • Файлы с меньшей экономией будут пропущены
        • По умолчанию: 1024 Б (1 КБ)

        ТАЙМАУТ ФАЙЛА (СЕК):
        • Максимальное время обработки одного файла
        • Защита от зависания на больших или поврежденных файлах
        • По умолчанию: 35 секунд

        ИНТЕРВАЛ ИТЕРАЦИЙ ДЛЯ ТАЙМАУТА (ШТ):
        • Количество файлов, после обработки которых делается перерыв
        • Помогает обойти ограничения антивирусного ПО
        • По умолчанию: 350 файлов

        ПРОДОЛЖИТЕЛЬНОСТЬ ИНТЕРВАЛЬНОГО ТАЙМАУТА (СЕК):
        • Длительность перерыва после заданного количества итераций
        • По умолчанию: 9 секунд

        3. ЗАПУСК ОБРАБОТКИ:
        • Нажмите "Начать сжатие" для запуска процесса
        • Следите за прогрессом в журнале операций
        • Используйте "Пропустить файл" если обработка зависла
        • Статистика отображается в реальном времени

        📊 НОВАЯ СТАТИСТИКА В БАЗЕ ДАННЫХ:

        Для КАЖДОГО обработанного файла теперь сохраняется:
        • Количество страниц (для анализа)
        • Исходный размер файла в КБ (для расчета эффективности)
        
        Это позволяет:
        • Рассчитывать реальную стоимость сжатия на страницу
        • Определять оптимальные пороги для разных типов документов
        • Строить графики эффективности по месяцам/дням
        • Выявлять проблемные форматы файлов

        ⚙️ УПРАВЛЕНИЕ НАСТРОЙКАМИ С НОВЫМИ ПОЛЯМИ:

        При создании новой настройки вы можете:
        • Установить лимит размера страницы (0 = отключено)
        • Все параметры сохраняются в уникальную комбинацию
        • Можно быстро переключаться между пресетами
        • История использования настроек отслеживается

        📈 АНАЛИТИКА И ОПТИМИЗАЦИЯ:

        Совет по настройке лимита размера страницы:
        1. Запустите обработку с выключенным лимитом (0 КБ)
        2. После обработки откройте "Статистику сжатия"
        3. Посмотрите средний размер страницы успешных файлов
        4. Установите лимит на 20-30% выше среднего
        5. Следующие запуски будут быстрее и эффективнее

        🔧 ТЕХНИЧЕСКИЕ ТРЕБОВАНИЯ:

        • Установленный Ghostscript (проверяется автоматически)
        • Для OCR: Tesseract OCR и зависимости
        • Python 3.8 или новее
        • Библиотека PyPDF2 (для подсчета страниц)
        • Права доступа к обрабатываемым файлам

        ⚠️ ВАЖНЫЕ ЗАМЕЧАНИЯ:

        • Закройте PDF файлы в других программах перед обработкой
        • Для больших файлов увеличьте таймаут обработки
        • Программа автоматически пропускает уже обработанные файлы
        • Рекомендуется делать бэкап важных файлов перед обработкой
        • Новые поля в БД заполняются автоматически при обработке

        📞 ПОДДЕРЖКА:

        • Журналы работы сохраняются в папке logs/
        • Для диагностики проблем используйте журналы операций
        • Проверьте установку Ghostscript и Tesseract при возникновении ошибок
        • Статистика в БД поможет оптимизировать настройки

        Для начала работы выберите директорию и нажмите "Начать сжатие"!
        """
        # ... (код создания окна остается без изменений)

        # Создаем окно с инструкцией
        instructions_window = tk.Toplevel(self.root)
        instructions_window.title("Инструкция по использованию PDF Compressor Pro")
        instructions_window.geometry("900x700")
        instructions_window.transient(self.root)
        instructions_window.grab_set()

        # Создаем текстовое поле с прокруткой
        frame = ttk.Frame(instructions_window)
        frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Прокрутка
        scrollbar = ttk.Scrollbar(frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Текстовое поле
        text_widget = tk.Text(frame, wrap=tk.WORD, yscrollcommand=scrollbar.set,
                              padx=10, pady=10, font=("Arial", 10))
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=text_widget.yview)

        # Вставляем текст инструкции
        text_widget.insert(1.0, instructions_text)
        text_widget.config(state=tk.DISABLED)  # Делаем текст только для чтения

        # Кнопка закрытия
        ttk.Button(instructions_window, text="Закрыть",
                   command=instructions_window.destroy).pack(pady=10)


    def safe_db_operation(self, operation, *args, **kwargs):
        """
        Безопасное выполнение операций с БД с автоматическим восстановлением сессии
        """
        max_retries = 3
        for attempt in range(max_retries):
            try:
                return operation(*args, **kwargs)
            except Exception as e:
                if "rolled back" in str(e).lower() or "transaction" in str(e).lower():
                    try:
                        self.db.rollback()
                        self.add_to_log(f"🔄 Восстановление сессии БД (попытка {attempt + 1}/{max_retries})", "warning")
                    except:
                        pass
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(0.5)  # Небольшая пауза перед повтором
                else:
                    raise


def main():
    root = tk.Tk()
    app = PDFCompressor(root)
    root.mainloop()


if __name__ == "__main__":
    main()
