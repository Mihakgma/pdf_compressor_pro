# models/models.py

import pytz
from sqlalchemy import (Column,
                        Integer,
                        String,
                        Boolean,
                        DateTime,
                        Float,
                        Text,
                        ForeignKey,
                        UniqueConstraint,
                        CheckConstraint)
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class NestingDepth(Base):
    __tablename__ = "nesting_depth"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, default="Все поддиректории")

    settings = relationship("Setting", back_populates="nesting_depth")


class CompressionMethod(Base):
    __tablename__ = "compression_method"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_ocr_enabled = Column(Boolean, default=False)

    settings = relationship("Setting", back_populates="compression_method")


class FailReason(Base):
    __tablename__ = "fail_reason"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), nullable=False, unique=True)
    info = Column(Text, nullable=True)

    processed_files = relationship("ProcessedFile", back_populates="fail_reason_rel")


class Setting(Base):
    __tablename__ = "setting"

    id = Column(Integer, primary_key=True, index=True)
    nesting_depth_id = Column(Integer, ForeignKey("nesting_depth.id"), nullable=False)
    need_replace = Column(Boolean, nullable=False, default=True)
    compression_level = Column(Integer, nullable=False, default=2)
    compression_method_id = Column(Integer, ForeignKey("compression_method.id"), nullable=False)
    compression_min_boundary = Column(Integer, nullable=False, default=1024)
    procession_timeout = Column(Integer, nullable=False, default=35)
    is_active = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True),
                        default=lambda: datetime.now(pytz.timezone('Asia/Novosibirsk')),
                        nullable=False)

    timeout_iterations = Column(Integer, nullable=False, default=350)
    timeout_interval_secs = Column(Integer, nullable=False, default=9)

    # ✅ OCR поле
    ocr_max_pages = Column(Integer, nullable=False, default=120)

    # ✅ НОВОЕ ПОЛЕ: максимально допустимый размер страницы, КБайт
    kbytes_per_page_border = Column(Float, nullable=True, default=None)

    info = Column(Text, nullable=True)

    # Constraint для уникальности комбинации полей
    __table_args__ = (
        UniqueConstraint(
            'nesting_depth_id',
            'need_replace',
            'compression_level',
            'compression_method_id',
            'compression_min_boundary',
            'procession_timeout',
            'timeout_iterations',
            'timeout_interval_secs',
            'ocr_max_pages',
            'kbytes_per_page_border',  # ✅ ДОБАВЛЕНО
            name='uq_setting_combination'
        ),
        CheckConstraint('compression_level >= 1 AND compression_level <= 3', name='chk_compression_level'),
        CheckConstraint('compression_min_boundary >= 1 AND compression_min_boundary <= 10000',
                        name='chk_compression_min_boundary'),
        CheckConstraint('procession_timeout >= 1 AND procession_timeout <= 3600', name='chk_procession_timeout'),
        CheckConstraint('timeout_iterations >= 1 AND timeout_iterations <= 1000', name='chk_timeout_iterations'),
        CheckConstraint('timeout_interval_secs >= 1 AND timeout_interval_secs <= 60', name='chk_timeout_interval_secs'),
        CheckConstraint('ocr_max_pages >= 1 AND ocr_max_pages <= 1000', name='chk_ocr_max_pages'),
        CheckConstraint('kbytes_per_page_border >= 1 OR kbytes_per_page_border IS NULL', 
                        name='chk_kbytes_per_page_border')
    )

    nesting_depth = relationship("NestingDepth", back_populates="settings")
    processed_files = relationship("ProcessedFile", back_populates="setting")
    compression_method = relationship("CompressionMethod")


class ProcessedFile(Base):
    __tablename__ = "processed_files"

    id = Column(Integer, primary_key=True, index=True)
    file_full_path = Column(String(200), nullable=False, unique=True)
    is_successful = Column(Boolean, nullable=False)
    fail_reason_id = Column(Integer, ForeignKey("fail_reason.id"), nullable=True)
    processed_date = Column(DateTime(timezone=True),
                            default=lambda: datetime.now(pytz.timezone('Asia/Novosibirsk')),
                            nullable=False)
    setting_id = Column(Integer, ForeignKey("setting.id"), nullable=False)
    file_compression_kbites = Column(Float, nullable=False, default=0.0)
    other_fail_reason = Column(Text, nullable=True)
    
    # ✅ НОВЫЕ ПОЛЯ
    file_pages = Column(Integer, nullable=True, default=None)  # количество страниц
    file_origin_size_kbytes = Column(Float, nullable=True, default=None)  # исходный размер в КБ

    setting = relationship("Setting", back_populates="processed_files")
    fail_reason_rel = relationship("FailReason", back_populates="processed_files")
