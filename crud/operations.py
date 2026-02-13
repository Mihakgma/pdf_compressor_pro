# crud/operations.py

import os

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
            other_fail_reason: Optional[str] = None
    ) -> ProcessedFile:
        # Нормализуем путь перед сохранением
        normalized_path = self.normalize_path(file_full_path)

        processed_file = ProcessedFile(
            file_full_path=normalized_path,  # Сохраняем нормализованный путь
            is_successful=is_successful,
            fail_reason_id=fail_reason_id,
            setting_id=setting_id,
            file_compression_kbites=file_compression_kbites,
            other_fail_reason=other_fail_reason
        )
        self.db.add(processed_file)
        self.db.commit()
        self.db.refresh(processed_file)
        return processed_file

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
            ocr_max_pages: int  # ✅ ДОБАВЛЕНО
    ) -> Optional[Setting]:
        return self.db.query(Setting).filter(
            and_(
                Setting.nesting_depth_id == nesting_depth_id,
                Setting.need_replace == need_replace,
                Setting.compression_level == compression_level,
                Setting.compression_method_id == compression_method_id,
                Setting.compression_min_boundary == compression_min_boundary,
                Setting.procession_timeout == procession_timeout,
                Setting.timeout_iterations == timeout_iterations,
                Setting.timeout_interval_secs == timeout_interval_secs,
                Setting.ocr_max_pages == ocr_max_pages  # ✅ ДОБАВЛЕНО
            )
        ).first()

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
            ocr_max_pages: int = 120,  # ✅ НОВОЕ
            info: Optional[str] = None,
            activate: bool = True
    ) -> Setting:
        # Сначала проверяем, существует ли уже такая настройка
        existing_setting = self.find_existing_setting(
            nesting_depth_id=nesting_depth_id,
            need_replace=need_replace,
            compression_level=compression_level,
            compression_method_id=compression_method_id,
            compression_min_boundary=compression_min_boundary,
            procession_timeout=procession_timeout,
            timeout_iterations=timeout_iterations,
            timeout_interval_secs=timeout_interval_secs,
            ocr_max_pages=ocr_max_pages  # ✅
        )

        if existing_setting:
            # Если настройка уже существует, просто активируем ее
            if activate:
                return self.activate_setting(existing_setting.id)
            return existing_setting

        # Если настройки не существует, создаем новую
        setting = Setting(
            nesting_depth_id=nesting_depth_id,
            need_replace=need_replace,
            compression_level=compression_level,
            compression_method_id=compression_method_id,
            compression_min_boundary=compression_min_boundary,
            procession_timeout=procession_timeout,
            timeout_iterations=timeout_iterations,
            timeout_interval_secs=timeout_interval_secs,
            ocr_max_pages=ocr_max_pages,  # ✅
            is_active=activate,
            info=info or f"Создано {datetime.datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

        self.db.add(setting)
        
        if activate:
            # Деактивируем все текущие настройки ПОСЛЕ добавления новой
            self.db.query(Setting).filter(Setting.id != setting.id).update({Setting.is_active: False})
        
        self.db.commit()
        self.db.refresh(setting)
        return setting

    def activate_setting(self, setting_id: int) -> Setting:
        # Деактивируем все настройки
        self.db.query(Setting).update({Setting.is_active: False})

        # Активируем выбранную
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

    # Инициализация базовых данных
    def initialize_base_data(self):
        self.add_ocr_max_pages_column()
        # Создаем причины ошибок
        fail_reasons = [
            {"name": "размер увеличился при сжатии",
             "info": "Файл был пропущен, так как размер после сжатия увеличился"},
            {"name": "превышен таймаут обработки файла",
             "info": "Обработка файла заняла больше времени, чем установленный таймаут"},
            {"name": "прочая причина", "info": "Другие причины ошибок при обработки файла"}
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

        # Создаем методы сжатия с OCR-флагами
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
                # Обновляем существующий метод
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
                ocr_max_pages=120,  # ✅
                info="Настройка по умолчанию",
                activate=True
            )

    def normalize_path(self, file_path: str) -> str:
        """Нормализует путь для сравнения с учетом особенностей ОС"""
        try:
            # Приводим к абсолютному пути
            abs_path = os.path.abspath(file_path)

            # Нормализуем разделители
            normalized = abs_path.replace('\\', '/')

            # Для Windows приводим к нижнему регистру
            if os.name == 'nt':
                normalized = normalized.lower()

            # Убираем конечный слеш если есть
            normalized = normalized.rstrip('/')

            return normalized

        except Exception as e:
            print(f"Ошибка нормализации пути {file_path}: {e}")
            return file_path

    def normalize_existing_paths(self):
        """Нормализует пути в существующих записях и удаляет дубликаты"""
        try:
            # Получаем все записи
            all_files = self.db.query(ProcessedFile).all()
            print(f"Всего записей до нормализации: {len(all_files)}")

            # Словарь для отслеживания уникальных путей
            unique_paths = {}
            duplicates_to_remove = []

            for pf in all_files:
                normalized = self.normalize_path(pf.file_full_path)

                # Проверяем, есть ли уже запись с таким нормализованным путем
                if normalized in unique_paths:
                    print(f"Найден дубликат: {pf.file_full_path} -> {normalized}")
                    duplicates_to_remove.append(pf.id)
                else:
                    unique_paths[normalized] = pf.id
                    # Обновляем путь на нормализованный
                    if normalized != pf.file_full_path:
                        pf.file_full_path = normalized
                        print(f"Обновлен путь: {pf.file_full_path} -> {normalized}")

            # Удаляем дубликаты
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
        