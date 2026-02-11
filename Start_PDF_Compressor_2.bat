@echo off
setlocal

:: Проверка прав администратора
fltmc >nul 2>&1 || (
    echo Требуются права администратора. Запускаю с повышенными привилегиями...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

echo ========================================
echo    PDF Compressor Pro
echo ========================================
echo Запуск программы...

cd /d "C:\Projects\pdfCompressor"
"C:\Projects\pdfCompressor\venv\Scripts\python.exe" "C:\Projects\pdfCompressor\main.py"

echo.
echo Программа завершена.
pause