# ocr_processor.py
import os
import io
import tempfile
import subprocess
import traceback
import shutil
from typing import Optional, List
import datetime

# Проверяем наличие зависимостей OCR
OCR_AVAILABLE = False
OCR_DEPENDENCIES = []

try:
    from pdf2image import convert_from_path
    OCR_DEPENDENCIES.append("pdf2image")
except ImportError:
    OCR_DEPENDENCIES.append("❌ pdf2image")

try:
    import pytesseract
    OCR_DEPENDENCIES.append("pytesseract")
except ImportError:
    OCR_DEPENDENCIES.append("❌ pytesseract")

try:
    from PyPDF2 import PdfMerger
    OCR_DEPENDENCIES.append("PyPDF2")
except ImportError:
    OCR_DEPENDENCIES.append("❌ PyPDF2")

# Проверяем, установлены ли все зависимости
if all("❌" not in dep for dep in OCR_DEPENDENCIES):
    OCR_AVAILABLE = True


class OCRProcessor:
    def __init__(self, db_ops=None, add_to_log_callback=None):
        self.db_ops = db_ops
        self.add_to_log = add_to_log_callback or (lambda msg, level="info": print(f"[{level}] {msg}"))
        
        # Путь к Tesseract (автоматически определится)
        self.tesseract_path = None
        
        if OCR_AVAILABLE:
            self.tesseract_path = self.get_tesseract_path()
            if self.tesseract_path:
                try:
                    pytesseract.pytesseract.tesseract_cmd = self.tesseract_path
                except Exception as e:
                    self._safe_log(f"Ошибка настройки Tesseract: {e}", "warning")
        else:
            self._safe_log("OCR зависимости не установлены: " + ", ".join(OCR_DEPENDENCIES), "warning")
        
        # Проверяем доступность OCR
        self.ocr_available = self.check_ocr_availability()
    
    def _safe_log(self, message, level="info"):
        """Безопасный логгер, который не падает если UI еще не создан"""
        try:
            if self.add_to_log:
                self.add_to_log(message, level)
            else:
                print(f"[{level}] {message}")
        except:
            print(f"[{level}] {message}")
    
    def get_tesseract_path(self):
        """Автоматически определяет путь к Tesseract"""
        if not OCR_AVAILABLE:
            return None
            
        possible_paths = [
            r'C:\Program Files\Tesseract-OCR\tesseract.exe',
            r'C:\Program Files\PDF24\tesseract\tesseract.exe',
            r'C:\Program Files (x86)\Tesseract-OCR\tesseract.exe',
            '/usr/bin/tesseract',
            '/usr/local/bin/tesseract',
            'tesseract'  # Если в PATH
        ]
        
        for path in possible_paths:
            if path == 'tesseract':
                # Проверяем наличие в PATH
                try:
                    result = subprocess.run(['which', 'tesseract'], capture_output=True, text=True, timeout=2)
                    if result.returncode == 0:
                        found_path = result.stdout.strip()
                        self._safe_log(f"Tesseract найден: {found_path}", "success")
                        return found_path
                except:
                    continue
            elif os.path.exists(path):
                self._safe_log(f"Tesseract найден: {path}", "success")
                return path
        
        self._safe_log("Tesseract не найден. Установите его для использования OCR-методов.", "warning")
        return None
    
    def check_ocr_availability(self):
        """Проверяет доступность всех компонентов OCR"""
        if not OCR_AVAILABLE:
            self._safe_log("Библиотеки OCR не установлены", "warning")
            return False
            
        if not self.tesseract_path:
            self._safe_log("Tesseract не найден. Установите его для использования OCR-методов.", "warning")
            return False
            
        try:
            # Проверяем, что Tesseract работает
            version = subprocess.run([self.tesseract_path, '--version'], 
                                    capture_output=True, text=True, timeout=5)
            if version.returncode == 0:
                self._safe_log(f"OCR доступен: Tesseract {version.stdout.split()[1]}", "success")
                return True
        except Exception as e:
            self._safe_log(f"Ошибка проверки Tesseract: {e}", "warning")
            
        return False
    
    def process_with_tesseract(self, input_path: str, output_path: str, dpi: int = 150, 
                              languages: List[str] = None) -> bool:
        """Обрабатывает PDF через Tesseract OCR"""
        if not self.ocr_available:
            self._safe_log("OCR недоступен. Установите зависимости и Tesseract.", "error")
            return False
            
        temp_files = []
        
        try:
            self._safe_log(f"Начало OCR-обработки файла: {os.path.basename(input_path)}")
            self._safe_log(f"Параметры: DPI={dpi}, Языки={languages or ['rus', 'eng']}")
            
            # Подготовка языков
            if languages is None:
                languages = ['rus', 'eng']
            lang_str = '+'.join(languages)
            
            # Для сетевых файлов копируем локально
            local_input = input_path
            if input_path.startswith('\\\\') or '://' in input_path:
                local_input = self.copy_to_local(input_path)
                if not local_input:
                    raise Exception("Не удалось скопировать сетевой файл")
                temp_files.append(local_input)
            
            # 1. Конвертируем PDF в изображения
            self._safe_log(f"Конвертация PDF в изображения (DPI: {dpi})...")
            start_time = datetime.datetime.now()
            
            pages = convert_from_path(local_input, dpi=dpi)
            conversion_time = (datetime.datetime.now() - start_time).total_seconds()
            
            self._safe_log(f"Получено {len(pages)} страниц за {conversion_time:.1f} секунд")
            
            if len(pages) == 0:
                raise Exception("PDF не содержит страниц или поврежден")
            
            # 2. Обрабатываем каждую страницу через Tesseract
            pdf_pages = []
            
            for i, page in enumerate(pages, 1):
                if i % 5 == 0 or i == len(pages):
                    self._safe_log(f"OCR страницы {i}/{len(pages)}...")
                
                # Создаем временный файл для изображения
                with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_img:
                    page.save(temp_img.name, 'PNG', optimize=True)
                    temp_files.append(temp_img.name)
                
                # Выполняем OCR и получаем PDF с текстовым слоем
                try:
                    page_pdf_bytes = pytesseract.image_to_pdf_or_hocr(
                        temp_img.name, 
                        extension='pdf', 
                        lang=lang_str,
                        config='--psm 1 --oem 3'
                    )
                    pdf_pages.append(page_pdf_bytes)
                except Exception as e:
                    self._safe_log(f"Ошибка OCR страницы {i}: {e}", "warning")
                    # Продолжаем со следующей страницы
                    continue
            
            if not pdf_pages:
                raise Exception("Не удалось обработать ни одну страницу")
            
            # 3. Объединяем PDF-страницы
            self._safe_log("Объединение страниц...")
            merger = PdfMerger()
            
            for page_bytes in pdf_pages:
                merger.append(io.BytesIO(page_bytes))
            
            # 4. Сохраняем результат
            with open(output_path, 'wb') as f:
                merger.write(f)
            
            merger.close()
            
            # 5. Проверяем результат
            if os.path.exists(output_path) and os.path.getsize(output_path) > 0:
                output_size = os.path.getsize(output_path)
                original_size = os.path.getsize(input_path)
                compression_ratio = (1 - output_size / original_size) * 100 if original_size > 0 else 0
                
                self._safe_log(f"OCR-обработка завершена успешно. Размер: {output_size/1024:.1f} KB", "success")
                self._safe_log(f"Сжатие: {compression_ratio:.1f}%", "info")
                return True
            else:
                raise Exception("Результирующий файл пуст или не создан")
            
        except Exception as e:
            self._safe_log(f"Ошибка OCR-обработки: {str(e)}", "error")
            if hasattr(e, '__traceback__'):
                self._safe_log(f"Трассировка: {traceback.format_exc()}", "error")
            return False
            
        finally:
            # Очистка временных файлов
            for temp_file in temp_files:
                try:
                    if os.path.exists(temp_file):
                        os.remove(temp_file)
                except Exception as e:
                    self._safe_log(f"Не удалось удалить временный файл {temp_file}: {e}", "warning")
    
    def process_with_tesseract_and_ghostscript(self, input_path: str, output_path: str, 
                                              compression_level: int = 2) -> bool:
        """Комбинированная обработка: OCR + Ghostscript сжатие"""
        if not self.ocr_available:
            self._safe_log("OCR недоступен. Установите зависимости и Tesseract.", "error")
            return False
            
        temp_dir = tempfile.gettempdir()
        temp_ocr_pdf = os.path.join(temp_dir, f"temp_ocr_{os.path.basename(input_path)}")
        
        try:
            # 1. OCR-обработка
            self._safe_log("Этап 1/2: OCR-обработка...")
            ocr_success = self.process_with_tesseract(input_path, temp_ocr_pdf)
            
            if not ocr_success:
                return False
            
            # 2. Сжатие через Ghostscript
            self._safe_log("Этап 2/2: Сжатие Ghostscript...")
            
            # Определяем команду Ghostscript
            gs_command = 'gswin64c' if os.name == 'nt' else 'gs'
            
            # Настройки сжатия
            if compression_level == 1:
                settings = ['-dPDFSETTINGS=/screen']
            elif compression_level == 2:
                settings = ['-dPDFSETTINGS=/ebook']
            else:
                settings = ['-dPDFSETTINGS=/prepress']
            
            command = [
                gs_command,
                '-sDEVICE=pdfwrite',
                '-dCompatibilityLevel=1.4',
                '-dNOPAUSE',
                '-dQUIET',
                '-dBATCH',
                *settings,
                '-dColorConversionStrategy=/sRGB',
                '-dProcessColorModel=/DeviceRGB',
                '-dEmbedAllFonts=true',
                '-dSubsetFonts=true',
                '-dAutoRotatePages=/PageByPage',
                '-dDownsampleColorImages=true',
                '-dDownsampleGrayImages=true',
                '-dDownsampleMonoImages=true',
                '-dColorImageResolution=150',
                '-dGrayImageResolution=150',
                '-dMonoImageResolution=300',
                f'-sOutputFile={output_path}',
                temp_ocr_pdf
            ]
            
            self._safe_log(f"Запуск Ghostscript с уровнем сжатия {compression_level}...")
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=600  # 10 минут таймаут для больших файлов
            )
            
            if result.returncode == 0:
                output_size = os.path.getsize(output_path)
                self._safe_log(f"Комбинированная обработка завершена успешно. Размер: {output_size/1024:.1f} KB", "success")
                return True
            else:
                error_msg = result.stderr[:500] if result.stderr else "Неизвестная ошибка"
                self._safe_log(f"Ошибка Ghostscript: {error_msg}", "error")
                return False
                
        except subprocess.TimeoutExpired:
            self._safe_log("Таймаут при сжатии Ghostscript (10 минут)", "error")
            return False
        except Exception as e:
            self._safe_log(f"Ошибка комбинированной обработки: {str(e)}", "error")
            return False
        finally:
            # Удаляем временный OCR-файл
            try:
                if os.path.exists(temp_ocr_pdf):
                    os.remove(temp_ocr_pdf)
            except Exception as e:
                self._safe_log(f"Не удалось удалить временный файл: {e}", "warning")
    
    def copy_to_local(self, network_path: str) -> Optional[str]:
        """Копирует файл на локальный диск"""
        try:
            temp_dir = tempfile.gettempdir()
            filename = os.path.basename(network_path)
            # Добавляем timestamp для уникальности
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            local_path = os.path.join(temp_dir, f"temp_{timestamp}_{filename}")
            
            self._safe_log(f"Копирование сетевого файла на локальный диск: {local_path}")
            shutil.copy2(network_path, local_path)
            
            return local_path
        except Exception as e:
            self._safe_log(f"Ошибка копирования сетевого файла: {e}", "error")
            return None
    
    def is_ocr_method(self, method_id: int) -> bool:
        """Проверяет, является ли метод OCR-методом"""
        if not self.db_ops:
            # Если нет доступа к БД, проверяем по ID
            return method_id in [4, 5]  # Tesseract и Tesseract+GS
            
        method = self.db_ops.get_compression_method_by_id(method_id)
        if method:
            return method.is_ocr_enabled
        return False
    