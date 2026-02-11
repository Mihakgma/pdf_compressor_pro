@echo off
setlocal

:: Проверка прав администратора
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Запуск от имени администратора...
    powershell -Command "Start-Process cmd -ArgumentList '/c %~dp0Start_PDF_Compressor.bat' -Verb RunAs"
    exit /b
)

echo Запуск PDF Compressor...
cd /d "C:\Projects\pdfCompressor"
"C:\Projects\pdfCompressor\venv\Scripts\python.exe" "C:\Projects\pdfCompressor\main.py"

pause