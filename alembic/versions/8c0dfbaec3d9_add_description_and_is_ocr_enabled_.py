"""Add description and is_ocr_enabled fields to CompressionMethod

Revision ID: 8c0dfbaec3d9
Revises: 
Create Date: 2026-02-11 11:26:32.560048

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector


# revision identifiers, used by Alembic.
revision: str = '8c0dfbaec3d9'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    
    # 1. Добавляем столбцы в compression_method
    with op.batch_alter_table('compression_method', schema=None) as batch_op:
        batch_op.add_column(sa.Column('description', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('is_ocr_enabled', sa.Boolean(), nullable=True, server_default='0'))
    
    # 2. Обновляем constraint в setting с использованием batch mode
    with op.batch_alter_table('setting', schema=None) as batch_op:
        # Сначала удаляем старый constraint если он существует
        batch_op.drop_constraint('uq_setting_combination', type_='unique')
        # Создаем новый с дополнительными полями
        batch_op.create_unique_constraint(
            'uq_setting_combination',
            ['nesting_depth_id', 'need_replace', 'compression_level', 
             'compression_method_id', 'compression_min_boundary', 
             'procession_timeout', 'timeout_iterations', 'timeout_interval_secs']
        )
    
    # 3. Обновляем данные в compression_method
    connection = op.get_bind()
    
    # Определяем методы сжатия
    methods_data = [
        {"id": 1, "name": "Ghostscript", "description": "Профессиональное сжатие PDF", "is_ocr_enabled": False},
        {"id": 2, "name": "Стандартное", "description": "Базовое сжатие", "is_ocr_enabled": False},
        {"id": 3, "name": "Только изображения", "description": "Оптимизация только изображений", "is_ocr_enabled": False},
        {"id": 4, "name": "Tesseract OCR", "description": "Распознавание текста и создание поискового PDF", "is_ocr_enabled": True},
        {"id": 5, "name": "Tesseract + Ghostscript", "description": "OCR + последующее сжатие", "is_ocr_enabled": True},
    ]
    
    # Обновляем каждый метод
    for method in methods_data:
        connection.execute(
            sa.text("""
                UPDATE compression_method 
                SET description = :description, is_ocr_enabled = :is_ocr_enabled 
                WHERE id = :id
            """),
            {
                "description": method["description"],
                "is_ocr_enabled": method["is_ocr_enabled"],
                "id": method["id"]
            }
        )
    
    # 4. Если таблица пуста, вставляем данные
    result = connection.execute(sa.text("SELECT COUNT(*) FROM compression_method")).fetchone()
    if result[0] == 0:
        for method in methods_data:
            connection.execute(
                sa.text("""
                    INSERT INTO compression_method (id, name, description, is_ocr_enabled)
                    VALUES (:id, :name, :description, :is_ocr_enabled)
                """),
                method
            )


def downgrade() -> None:
    """Downgrade schema."""
    
    # 1. Обновляем constraint в setting обратно
    with op.batch_alter_table('setting', schema=None) as batch_op:
        batch_op.drop_constraint('uq_setting_combination', type_='unique')
        batch_op.create_unique_constraint(
            'uq_setting_combination',
            ['nesting_depth_id', 'need_replace', 'compression_level', 
             'compression_method_id', 'compression_min_boundary', 'procession_timeout']
        )
    
    # 2. Удаляем столбцы из compression_method
    with op.batch_alter_table('compression_method', schema=None) as batch_op:
        batch_op.drop_column('is_ocr_enabled')
        batch_op.drop_column('description')
        