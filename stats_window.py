# stats_window.py

import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from sqlalchemy import func, case
from models.database import get_db
from models.models import ProcessedFile, Setting


class StatsWindow:
    def __init__(self, parent):
        self.parent = parent
        self.window = tk.Toplevel(parent)
        self.window.title("Статистика сжатия PDF файлов")
        self.window.geometry("1200x700")
        self.window.transient(parent)
        self.window.grab_set()

        # Переменные
        self.group_by_var = tk.StringVar(value="month")
        self.stats_data = None

        self.setup_ui()
        self.load_data()

    def setup_ui(self):
        """Настройка интерфейса"""
        # Заголовок
        header_frame = ttk.Frame(self.window)
        header_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(
            header_frame,
            text="Статистика сжатия PDF файлов",
            font=("Arial", 16, "bold")
        ).pack(side=tk.LEFT)

        # Кнопка справки
        ttk.Button(
            header_frame,
            text="📋 Справка",
            command=self.show_help
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            header_frame,
            text="📊 Расширенная статистика",
            command=self.show_extended_stats
        ).pack(side=tk.RIGHT, padx=5)

        # Описание
        desc_frame = ttk.LabelFrame(self.window, text="Описание")
        desc_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(
            desc_frame,
            text="В этом окне отображается статистика обработки PDF файлов. "
                 "Вы можете группировать данные по месяцам или дням для анализа эффективности сжатия.",
            wraplength=1000
        ).pack(padx=5, pady=5)

        # Панель управления
        control_frame = ttk.Frame(self.window)
        control_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(control_frame, text="Группировать по:").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(control_frame, text="Месяцам", variable=self.group_by_var,
                        value="month", command=self.refresh_data).pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(control_frame, text="Дням", variable=self.group_by_var,
                        value="day", command=self.refresh_data).pack(side=tk.LEFT, padx=5)

        ttk.Button(control_frame, text="🔄 Обновить",
                   command=self.refresh_data).pack(side=tk.RIGHT, padx=5)

        # Таблица
        table_frame = ttk.LabelFrame(self.window, text="Сводная таблица")
        table_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # Создаем Treeview с прокруткой
        self.setup_table(table_frame)

        # Краткая статистика
        self.setup_quick_stats()

    def setup_table(self, parent):
        """Настройка таблицы"""
        # Создаем фрейм для таблицы и прокрутки
        table_container = ttk.Frame(parent)
        table_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Прокрутка
        scrollbar_y = ttk.Scrollbar(table_container)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)

        scrollbar_x = ttk.Scrollbar(table_container, orient=tk.HORIZONTAL)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)

        # Таблица
        columns = ("№", "date", "total", "success_count", "success_ratio",
                   "fail_count", "fail_ratio", "saved_space", "start_time", "end_time")

        self.tree = ttk.Treeview(
            table_container,
            columns=columns,
            show="headings",
            yscrollcommand=scrollbar_y.set,
            xscrollcommand=scrollbar_x.set
        )

        # Настройка колонок
        self.setup_columns()

        self.tree.pack(fill=tk.BOTH, expand=True)
        scrollbar_y.config(command=self.tree.yview)
        scrollbar_x.config(command=self.tree.xview)

        # Подсказки при наведении
        self.setup_tooltips()

    def setup_columns(self):
        """Настройка колонок таблицы"""
        columns_config = {
            "№": {"text": "№пп", "width": 50, "anchor": tk.CENTER},
            "date": {"text": "Дата", "width": 120, "anchor": tk.CENTER},
            "total": {"text": "N", "width": 80, "anchor": tk.CENTER},
            "success_count": {"text": "+n, шт.", "width": 80, "anchor": tk.CENTER},
            "success_ratio": {"text": "+доля,%", "width": 80, "anchor": tk.CENTER},
            "fail_count": {"text": "-n, шт.", "width": 80, "anchor": tk.CENTER},
            "fail_ratio": {"text": "-доля,%", "width": 80, "anchor": tk.CENTER},
            "saved_space": {"text": "Экономия, Мб", "width": 100, "anchor": tk.CENTER},
            "start_time": {"text": "Начало", "width": 80, "anchor": tk.CENTER},
            "end_time": {"text": "Окончание", "width": 80, "anchor": tk.CENTER}
        }

        for col, config in columns_config.items():
            self.tree.heading(col, text=config["text"])
            self.tree.column(col, width=config["width"], anchor=config["anchor"])

    def setup_tooltips(self):
        """Настройка подсказок для колонок"""
        tooltips = {
            "№": "Порядковый номер",
            "date": "Дата обработки файлов (группировка по месяцам или дням)",
            "total": "Всего обработано файлов за период",
            "success_count": "Количество успешно сжатых файлов",
            "success_ratio": "Доля успешно сжатых файлов в процентах",
            "fail_count": "Количество файлов с ошибкой сжатия",
            "fail_ratio": "Доля файлов с ошибкой сжатия в процентах",
            "saved_space": "Объем сэкономленного дискового пространства в МБ",
            "start_time": "Время начала обработки первого файла",
            "end_time": "Время окончания обработки последнего файла"
        }

        def show_tooltip(event):
            item = self.tree.identify_column(event.x)
            col_index = int(item.replace('#', '')) - 1
            columns = list(tooltips.keys())
            if col_index < len(columns):
                col_name = columns[col_index]
                messagebox.showinfo("Подсказка", tooltips[col_name])

        # Привязываем двойной клик для показа подсказки
        self.tree.bind("<Double-1>", show_tooltip)

    def setup_quick_stats(self):
        """Настройка блока краткой статистики"""
        stats_frame = ttk.LabelFrame(self.window, text="Краткая статистика")
        stats_frame.pack(fill=tk.X, padx=10, pady=5)

        self.stats_text = tk.Text(stats_frame, height=6, wrap=tk.WORD)
        self.stats_text.pack(fill=tk.X, padx=5, pady=5)
        self.stats_text.config(state=tk.DISABLED)

    def load_data(self):
        """Загрузка данных из базы"""
        try:
            db = next(get_db())

            # Получаем данные для таблицы
            self.load_table_data(db)

            # Загружаем краткую статистику
            self.load_quick_stats(db)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить данные: {e}")

    def calculate_saved_space_for_period(self, db, period, group_by):
        """Расчет сэкономленного места за период"""
        try:
            # Получаем все успешно обработанные файлы за период
            if group_by == "month":
                date_filter = func.strftime("%Y-%m", ProcessedFile.processed_date) == period
            else:  # day
                date_filter = func.strftime("%Y-%m-%d", ProcessedFile.processed_date) == period

            successful_files = db.query(ProcessedFile).filter(
                ProcessedFile.is_successful == True,
                date_filter
            ).all()

            total_saved_mb = 0

            for pf in successful_files:
                compressed_size_kb = pf.file_compression_kbites
                if compressed_size_kb > 0:
                    saved_mb = compressed_size_kb / 1024
                    total_saved_mb += saved_mb

            return total_saved_mb

        except Exception as e:
            print(f"Ошибка расчета экономии для периода {period}: {e}")
            return 0

    def load_table_data(self, db):
        """Загрузка данных для таблицы"""
        # Определяем формат группировки
        if self.group_by_var.get() == "month":
            date_format = "%Y-%m"
            date_display = func.strftime("%Y-%m", ProcessedFile.processed_date)
        else:  # day
            date_format = "%Y-%m-%d"
            date_display = func.strftime("%Y-%m-%d", ProcessedFile.processed_date)

        # Запрос для группировки данных
        query = db.query(
            date_display.label("period"),
            func.count(ProcessedFile.id).label("total"),
            func.sum(case((ProcessedFile.is_successful == True, 1), else_=0)).label("success_count"),
            func.sum(case((ProcessedFile.is_successful == False, 1), else_=0)).label("fail_count"),
            func.min(ProcessedFile.processed_date).label("first_time"),
            func.max(ProcessedFile.processed_date).label("last_time")
        ).group_by("period").order_by("period")

        results = query.all()

        # Очищаем таблицу
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Заполняем таблицу
        for i, row in enumerate(results, 1):
            total = row.total
            success_count = row.success_count or 0
            fail_count = row.fail_count or 0

            success_ratio = (success_count / total * 100) if total > 0 else 0
            fail_ratio = (fail_count / total * 100) if total > 0 else 0

            # Расчет сэкономленного места
            saved_space_mb = self.calculate_saved_space_for_period(db, row.period, self.group_by_var.get())

            # Форматируем время
            start_time = row.first_time.strftime("%H:%M:%S") if row.first_time else "N/A"
            end_time = row.last_time.strftime("%H:%M:%S") if row.last_time else "N/A"

            # Форматируем дату для отображения
            if self.group_by_var.get() == "month":
                display_date = datetime.strptime(row.period, "%Y-%m").strftime("%m.%Y")
            else:
                display_date = datetime.strptime(row.period, "%Y-%m-%d").strftime("%d.%m.%Y")

            self.tree.insert("", tk.END, values=(
                i,
                display_date,
                total,
                success_count,
                f"{success_ratio:.1f}%",
                fail_count,
                f"{fail_ratio:.1f}%",
                f"{saved_space_mb:.2f}",
                start_time,
                end_time
            ))

    def load_quick_stats(self, db):
        """Загрузка краткой статистики"""
        # Основные метрики
        total_files = db.query(ProcessedFile).count()
        success_files = db.query(ProcessedFile).filter(ProcessedFile.is_successful == True).count()
        settings_count = db.query(Setting).count()

        # Расчет общей экономии места
        total_saved_mb = 0
        successful_files = db.query(ProcessedFile).filter(ProcessedFile.is_successful == True).all()

        for pf in successful_files:
            compressed_size_kb = pf.file_compression_kbites
            if compressed_size_kb > 0:
                saved_mb = compressed_size_kb / 1024
                total_saved_mb += saved_mb

        # Временные метрики
        first_record = db.query(ProcessedFile).order_by(ProcessedFile.processed_date).first()
        last_record = db.query(ProcessedFile).order_by(ProcessedFile.processed_date.desc()).first()

        usage_period = "N/A"
        if first_record and last_record:
            delta = last_record.processed_date - first_record.processed_date
            years = delta.days // 365
            months = (delta.days % 365) // 30
            days = (delta.days % 365) % 30
            usage_period = f"{years} лет, {months} месяцев, {days} дней"

        # Самая популярная настройка
        popular_setting = db.query(
            ProcessedFile.setting_id,
            func.count(ProcessedFile.id).label("usage_count")
        ).group_by(ProcessedFile.setting_id).order_by(func.count(ProcessedFile.id).desc()).first()

        popular_setting_info = "N/A"
        if popular_setting:
            setting = db.query(Setting).filter(Setting.id == popular_setting.setting_id).first()
            if setting:
                ratio = (popular_setting.usage_count / total_files * 100) if total_files > 0 else 0
                popular_setting_info = f"ID{setting.id} ({popular_setting.usage_count} использований, {ratio:.1f}%)"

        # Формируем текст статистики
        stats_text = f"""📊 ОБЩАЯ СТАТИСТИКА:

• Всего файлов в базе: {total_files}
• Успешно сжато: {success_files} ({success_files / total_files * 100:.1f}% если total_files > 0 else 0%)
• Общая экономия места: {total_saved_mb:.2f} МБ ({total_saved_mb / 1024:.2f} ГБ)
• Количество настроек: {settings_count}
• Срок использования: {usage_period}
• Популярная настройка: {popular_setting_info}

Для подробной статистики нажмите кнопку "Расширенная статистика" """

        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)
        self.stats_text.insert(1.0, stats_text)
        self.stats_text.config(state=tk.DISABLED)

    def refresh_data(self):
        """Обновление данных"""
        self.load_data()

    def show_help(self):
        """Показать справку"""
        help_text = """
📋 СПРАВКА ПО СТАТИСТИКЕ

СВОДНАЯ ТАБЛИЦА:
• №пп - порядковый номер записи
• Дата - период группировки (месяц или день)
• N - общее количество обработанных файлов за период
• +n, шт. - количество успешно сжатых файлов
• +доля,% - процент успешных сжатий от общего числа
• -n, шт. - количество неудачных сжатий
• -доля,% - процент неудачных сжатий
• Экономия, Мб - объем сэкономленного дискового пространства
• Начало - время обработки первого файла в периоде
• Окончание - время обработки последнего файла

ГРУППИРОВКА:
• По месяцам - статистика агрегируется по месяцам
• По дням - детальная статистика по каждому дню

КРАТКАЯ СТАТИСТИКА:
Показывает общие метрики использования программы
        """
        messagebox.showinfo("Справка", help_text)

    def show_extended_stats(self):
        """Показать расширенную статистику"""
        try:
            db = next(get_db())

            # Расширенные метрики
            total_files = db.query(ProcessedFile).count()
            success_files = db.query(ProcessedFile).filter(ProcessedFile.is_successful == True).count()

            # Расчет общей экономии места
            total_saved_mb = 0
            successful_files_list = db.query(ProcessedFile).filter(ProcessedFile.is_successful == True).all()

            for pf in successful_files_list:
                compressed_size_kb = pf.file_compression_kbites
                if compressed_size_kb > 0:
                    saved_mb = compressed_size_kb / 1024
                    total_saved_mb += saved_mb

            # Статистика по настройкам
            settings_stats = db.query(
                Setting.id,
                Setting.compression_level,
                Setting.need_replace,
                func.count(ProcessedFile.id).label("usage_count")
            ).join(ProcessedFile).group_by(Setting.id).all()

            # Статистика по ошибкам
            error_stats = db.query(
                ProcessedFile.fail_reason_id,
                func.count(ProcessedFile.id).label("error_count")
            ).filter(ProcessedFile.is_successful == False).group_by(ProcessedFile.fail_reason_id).all()

            # Формируем расширенную статистику
            extended_text = "📈 РАСШИРЕННАЯ СТАТИСТИКА\n\n"
            extended_text += f"📁 ОБРАБОТКА ФАЙЛОВ:\n"
            extended_text += f"• Всего обработано: {total_files} файлов\n"
            extended_text += f"• Успешных сжатий: {success_files} ({success_files / total_files * 100:.1f}%)\n"
            extended_text += f"• Ошибок сжатия: {total_files - success_files} ({(total_files - success_files) / total_files * 100:.1f}%)\n"
            extended_text += f"• Общая экономия места: {total_saved_mb:.2f} МБ ({total_saved_mb / 1024:.2f} ГБ)\n\n"

            extended_text += f"⚙️ СТАТИСТИКА НАСТРОЕК:\n"
            for stat in settings_stats:
                ratio = (stat.usage_count / total_files * 100) if total_files > 0 else 0
                replace_text = "замена" if stat.need_replace else "копия"
                extended_text += f"• Настройка ID{stat.id}: ур.{stat.compression_level}, {replace_text} - {stat.usage_count} использований ({ratio:.1f}%)\n"

            extended_text += f"\n❌ СТАТИСТИКА ОШИБОК:\n"
            for error in error_stats:
                ratio = (error.error_count / (total_files - success_files) * 100) if (
                                                                                             total_files - success_files) > 0 else 0
                extended_text += f"• Ошибка ID{error.fail_reason_id}: {error.error_count} случаев ({ratio:.1f}% от всех ошибок)\n"

            # Показываем в отдельном окне
            self.show_extended_window(extended_text)

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить расширенную статистику: {e}")

    def show_extended_window(self, text):
        """Показать окно с расширенной статистикой"""
        ext_window = tk.Toplevel(self.window)
        ext_window.title("Расширенная статистика")
        ext_window.geometry("800x600")

        text_widget = tk.Text(ext_window, wrap=tk.WORD, padx=10, pady=10)
        text_widget.pack(fill=tk.BOTH, expand=True)

        text_widget.insert(1.0, text)
        text_widget.config(state=tk.DISABLED)

        ttk.Button(ext_window, text="Закрыть",
                   command=ext_window.destroy).pack(pady=10)
