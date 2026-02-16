# crud/operations.py


import os
import re

from sqlalchemy.orm import Session
from sqlalchemy import and_
from models.models import (
    ProcessedFile,
    Setting,
    FailReason,
    NestingDepth,
    CompressionMethod
)
from typing import Optional, List
import datetime


class DBOperations:
    def __init__(self, db: Session):
        self.db = db

    # Операции с ProcessedFile
    def get_processed_file_by_path(self, file_path: str) -> Optional[ProcessedFile]:
        normalized_path = self.normalize_path(file_path)
        return self.db.query(ProcessedFile).filter(
            ProcessedFile.file_full_path == normalized_path
        ).first()

    def create_processed_file(
            self,
            file_full_path: str,
            is_successful: bool,
            setting_id: int,
            file_compression_kbites: float = 0.0,
            fail_reason_id: Optional[int] = None,
            other_fail_reason: Optional[str] = None,
            file_pages: Optional[int] = None,
            file_origin_size_kbytes: Optional[float] = None
    ) -> ProcessedFile:
        # Нормализуем путь перед сохранением
        normalized_path = self.normalize_path(file_full_path)

        # Проверяем существование записи прямо перед сохранением
        existing = self.get_processed_file_by_path(normalized_path)
        if existing:
            print(f"⚠️ Запись уже существует для пути: {normalized_path}")
            return existing

        processed_file = ProcessedFile(
            file_full_path=normalized_path,
            is_successful=is_successful,
            fail_reason_id=fail_reason_id,
            setting_id=setting_id,
            file_compression_kbites=file_compression_kbites,
            other_fail_reason=other_fail_reason,
            file_pages=file_pages,
            file_origin_size_kbytes=file_origin_size_kbytes
        )
        self.db.add(processed_file)
        try:
            self.db.commit()
            self.db.refresh(processed_file)
            return processed_file
        except Exception as e:
            self.db.rollback()  # Важно! Откатываем транзакцию при ошибке
            print(f"❌ Ошибка сохранения в БД: {e}")
            raise

    # Операции с Setting
    def get_active_setting(self) -> Optional[Setting]:
        return self.db.query(Setting).filter(Setting.is_active == True).first()

    def find_existing_setting(
            self,
            nesting_depth_id: int,
            need_replace: bool,
            compression_level: int,
            compression_method_id: int,
            compression_min_boundary: int,
            procession_timeout: int,
            timeout_iterations: int,
            timeout_interval_secs: int,
            ocr_max_pages: int,
            kbytes_per_page_border: Optional[float] = None  # ✅ НОВОЕ
    ) -> Optional[Setting]:
        query = self.db.query(Setting).filter(
            and_(
                Setting.nesting_depth_id == nesting_depth_id,
                Setting.need_replace == need_replace,
                Setting.compression_level == compression_level,
                Setting.compression_method_id == compression_method_id,
                Setting.compression_min_boundary == compression_min_boundary,
                Setting.procession_timeout == procession_timeout,
                Setting.timeout_iterations == timeout_iterations,
                Setting.timeout_interval_secs == timeout_interval_secs,
                Setting.ocr_max_pages == ocr_max_pages
            )
        )
        
        # Обрабатываем NULL для kbytes_per_page_border
        if kbytes_per_page_border is None:
            query = query.filter(Setting.kbytes_per_page_border.is_(None))
        else:
            query = query.filter(Setting.kbytes_per_page_border == kbytes_per_page_border)
            
        return query.first()

    def create_setting(
            self,
            nesting_depth_id: int,
            need_replace: bool = True,
            compression_level: int = 2,
            compression_method_id: int = 1,
            compression_min_boundary: int = 1024,
            procession_timeout: int = 35,
            timeout_iterations: int = 350,
            timeout_interval_secs: int = 9,
            ocr_max_pages: int = 120,
            kbytes_per_page_border: Optional[float] = None,  # ✅ НОВОЕ
            info: Optional[str] = None,
            activate: bool = True
    ) -> Setting:
        # Проверяем, существует ли уже такая настройка
        existing_setting = self.find_existing_setting(
            nesting_depth_id=nesting_depth_id,
            need_replace=need_replace,
            compression_level=compression_level,
            compression_method_id=compression_method_id,
            compression_min_boundary=compression_min_boundary,
            procession_timeout=procession_timeout,
            timeout_iterations=timeout_iterations,
            timeout_interval_secs=timeout_interval_secs,
            ocr_max_pages=ocr_max_pages,
            kbytes_per_page_border=kbytes_per_page_border  # ✅
        )

        if existing_setting:
            if activate:
                return self.activate_setting(existing_setting.id)
            return existing_setting

        # Создаем новую настройку
        setting = Setting(
            nesting_depth_id=nesting_depth_id,
            need_replace=need_replace,
            compression_level=compression_level,
            compression_method_id=compression_method_id,
            compression_min_boundary=compression_min_boundary,
            procession_timeout=procession_timeout,
            timeout_iterations=timeout_iterations,
            timeout_interval_secs=timeout_interval_secs,
            ocr_max_pages=ocr_max_pages,
            kbytes_per_page_border=kbytes_per_page_border,  # ✅
            is_active=activate,
            info=info or f"Создано {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

        self.db.add(setting)
        
        if activate:
            self.db.query(Setting).filter(Setting.id != setting.id).update({Setting.is_active: False})
        
        self.db.commit()
        self.db.refresh(setting)
        return setting

    def activate_setting(self, setting_id: int) -> Setting:
        self.db.query(Setting).update({Setting.is_active: False})
        setting = self.db.query(Setting).filter(Setting.id == setting_id).first()
        if setting:
            setting.is_active = True
            self.db.commit()
            self.db.refresh(setting)
        return setting

    def get_all_settings(self) -> List[Setting]:
        return self.db.query(Setting).order_by(Setting.created_at.desc()).all()

    def update_setting_info(self, setting_id: int, info: str) -> Setting:
        setting = self.db.query(Setting).filter(Setting.id == setting_id).first()
        if setting:
            setting.info = info
            self.db.commit()
            self.db.refresh(setting)
        return setting

    # Операции с FailReason
    def get_fail_reason_by_name(self, name: str) -> Optional[FailReason]:
        return self.db.query(FailReason).filter(FailReason.name == name).first()

    def get_all_fail_reasons(self) -> List[FailReason]:
        return self.db.query(FailReason).all()

    def update_fail_reason_info(self, fail_reason_id: int, info: str) -> FailReason:
        fail_reason = self.db.query(FailReason).filter(FailReason.id == fail_reason_id).first()
        if fail_reason:
            fail_reason.info = info
            self.db.commit()
            self.db.refresh(fail_reason)
        return fail_reason

    # Операции с CompressionMethod
    def get_compression_method_by_name(self, name: str) -> Optional[CompressionMethod]:
        return self.db.query(CompressionMethod).filter(CompressionMethod.name == name).first()

    def get_all_compression_methods(self) -> List[CompressionMethod]:
        return self.db.query(CompressionMethod).all()

    def get_compression_method_by_id(self, method_id: int) -> Optional[CompressionMethod]:
        return self.db.query(CompressionMethod).filter(CompressionMethod.id == method_id).first()

    # Инициализация базовых данных и миграции
    def initialize_base_data(self):
        self.add_ocr_max_pages_column()
        self.add_kbytes_per_page_border_column()  # ✅ НОВОЕ
        self.add_file_pages_and_origin_size_columns()  # ✅ НОВОЕ
        
        # Создаем причины ошибок
        fail_reasons = [
            {"name": "размер увеличился при сжатии",
             "info": "Файл был пропущен, так как размер после сжатия увеличился"},
            {"name": "превышен таймаут обработки файла",
             "info": "Обработка файла заняла больше времени, чем установленный таймаут"},
            {"name": "прочая причина", 
             "info": "Другие причины ошибок при обработки файла"},
            {"name": "превышен лимит размера страницы",  # ✅ НОВОЕ
             "info": "Файл пропущен, так как размер страницы превышает установленный лимит"}
        ]

        for reason_data in fail_reasons:
            if not self.get_fail_reason_by_name(reason_data["name"]):
                fail_reason = FailReason(**reason_data)
                self.db.add(fail_reason)

        # Создаем методы глубины вложенности
        depth_names = ["Только текущая", "1 уровень", "2 уровня", "Все поддиректории"]
        for i, name in enumerate(depth_names, 1):
            if not self.db.query(NestingDepth).filter(NestingDepth.name == name).first():
                depth = NestingDepth(id=i, name=name)
                self.db.add(depth)

        # Создаем методы сжатия
        method_data = [
            {"id": 1, "name": "Ghostscript", "description": "Профессиональное сжатие PDF", "is_ocr_enabled": False},
            {"id": 2, "name": "Стандартное", "description": "Базовое сжатие", "is_ocr_enabled": False},
            {"id": 3, "name": "Только изображения", "description": "Оптимизация только изображений", "is_ocr_enabled": False},
            {"id": 4, "name": "Tesseract OCR", "description": "Распознавание текста и создание поискового PDF", "is_ocr_enabled": True},
            {"id": 5, "name": "Tesseract + Ghostscript", "description": "OCR + последующее сжатие", "is_ocr_enabled": True},
        ]
        
        for method_info in method_data:
            existing_method = self.db.query(CompressionMethod).filter(CompressionMethod.id == method_info["id"]).first()
            if not existing_method:
                method = CompressionMethod(
                    id=method_info["id"],
                    name=method_info["name"],
                    description=method_info["description"],
                    is_ocr_enabled=method_info["is_ocr_enabled"]
                )
                self.db.add(method)
            else:
                existing_method.description = method_info["description"]
                existing_method.is_ocr_enabled = method_info["is_ocr_enabled"]

        self.db.commit()

        # Создаем настройку по умолчанию, если нет активных
        if not self.get_active_setting():
            self.create_setting(
                nesting_depth_id=4,
                need_replace=True,
                compression_level=2,
                compression_method_id=1,
                compression_min_boundary=1024,
                procession_timeout=35,
                timeout_iterations=350,
                timeout_interval_secs=9,
                ocr_max_pages=120,
                kbytes_per_page_border=None,  # ✅ НОВОЕ - по умолчанию отключено
                info="Настройка по умолчанию",
                activate=True
            )

    def normalize_path(self, file_path: str) -> str:
        """
        Улучшенная нормализация пути для сетевых и локальных путей
        """
        try:
            # Приводим к абсолютному пути, если это возможно
            try:
                abs_path = os.path.abspath(file_path)
            except:
                abs_path = file_path
            
            # Заменяем обратные слеши на прямые
            normalized = abs_path.replace('\\', '/')
            
            # Для Windows путей (включая сетевые) приводим к нижнему регистру
            if os.name == 'nt' or normalized.startswith('//'):
                normalized = normalized.lower()
            
            # Удаляем лишние слеши в конце
            normalized = normalized.rstrip('/')
            
            # Нормализуем сетевые пути (//server/share -> //server/share)
            if normalized.startswith('//') and not normalized.startswith('///'):
                # Оставляем как есть, просто убираем лишние слеши
                normalized = re.sub(r'/+', '/', normalized)
            
            # Убираем возможные дублирующиеся слеши
            normalized = re.sub(r'/+', '/', normalized)
            
            return normalized
            
        except Exception as e:
            print(f"Ошибка нормализации пути {file_path}: {e}")
            # Возвращаем упрощенную версию в случае ошибки
            return file_path.replace('\\', '/').lower()

    def normalize_existing_paths(self):
        """Нормализует пути в существующих записях и удаляет дубликаты"""
        try:
            all_files = self.db.query(ProcessedFile).all()
            print(f"Всего записей до нормализации: {len(all_files)}")

            unique_paths = {}
            duplicates_to_remove = []

            for pf in all_files:
                normalized = self.normalize_path(pf.file_full_path)

                if normalized in unique_paths:
                    print(f"Найден дубликат: {pf.file_full_path} -> {normalized}")
                    duplicates_to_remove.append(pf.id)
                else:
                    unique_paths[normalized] = pf.id
                    if normalized != pf.file_full_path:
                        pf.file_full_path = normalized
                        print(f"Обновлен путь: {pf.file_full_path} -> {normalized}")

            if duplicates_to_remove:
                print(f"Удаляем {len(duplicates_to_remove)} дубликатов")
                self.db.query(ProcessedFile).filter(
                    ProcessedFile.id.in_(duplicates_to_remove)
                ).delete(synchronize_session=False)

            self.db.commit()
            print("Миграция завершена успешно")
        except Exception as e:
            print(f"Ошибка миграции: {e}")
            self.db.rollback()
            raise

    def check_duplicates(self):
        """Проверяет наличие дубликатов в базе"""
        from sqlalchemy import func

        duplicates = self.db.query(
            ProcessedFile.file_full_path,
            func.count(ProcessedFile.id)
        ).group_by(
            ProcessedFile.file_full_path
        ).having(
            func.count(ProcessedFile.id) > 1
        ).all()

        print(f"Найдено дубликатов: {len(duplicates)}")
        for path, count in duplicates:
            print(f"  {path}: {count} записей")

        return len(duplicates) == 0
    
    def add_ocr_max_pages_column(self):
        """Добавляет поле ocr_max_pages в таблицу setting, если его нет"""
        from sqlalchemy import inspect, text
        inspector = inspect(self.db.bind)
        columns = [col['name'] for col in inspector.get_columns('setting')]
        
        if 'ocr_max_pages' not in columns:
            self.db.execute(text("ALTER TABLE setting ADD COLUMN ocr_max_pages INTEGER DEFAULT 120 NOT NULL"))
            self.db.commit()
            print("✅ Поле ocr_max_pages добавлено в таблицу setting")
    
    # ✅ НОВЫЙ МЕТОД МИГРАЦИИ
    def add_kbytes_per_page_border_column(self):
        """Добавляет поле kbytes_per_page_border в таблицу setting, если его нет"""
        from sqlalchemy import inspect, text
        try:
            inspector = inspect(self.db.bind)
            columns = [col['name'] for col in inspector.get_columns('setting')]
            
            if 'kbytes_per_page_border' not in columns:
                self.db.execute(text(
                    "ALTER TABLE setting ADD COLUMN kbytes_per_page_border FLOAT DEFAULT NULL"
                ))
                self.db.commit()
                print("✅ Поле kbytes_per_page_border добавлено в таблицу setting")
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении kbytes_per_page_border: {e}")
            self.db.rollback()
    
    # ✅ НОВЫЙ МЕТОД МИГРАЦИИ
    def add_file_pages_and_origin_size_columns(self):
        """Добавляет поля file_pages и file_origin_size_kbytes в таблицу processed_files"""
        from sqlalchemy import inspect, text
        try:
            inspector = inspect(self.db.bind)
            columns = [col['name'] for col in inspector.get_columns('processed_files')]
            
            if 'file_pages' not in columns:
                self.db.execute(text(
                    "ALTER TABLE processed_files ADD COLUMN file_pages INTEGER DEFAULT NULL"
                ))
                print("✅ Поле file_pages добавлено в таблицу processed_files")
            
            if 'file_origin_size_kbytes' not in columns:
                self.db.execute(text(
                    "ALTER TABLE processed_files ADD COLUMN file_origin_size_kbytes FLOAT DEFAULT NULL"
                ))
                print("✅ Поле file_origin_size_kbytes добавлено в таблицу processed_files")
            
            self.db.commit()
        except Exception as e:
            print(f"⚠️ Ошибка при добавлении полей в processed_files: {e}")
            self.db.rollback()
            