@echo off
cd /d "%~dp0"
python -c "import flask, pandas, openpyxl, xlrd" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Memasang dependensi aplikasi...
  python -m pip install -r requirements-app.txt
)
if errorlevel 1 (
  echo.
  echo Gagal memasang dependensi. Periksa koneksi internet dan instalasi Python.
  pause
  exit /b 1
)
python app.py
if errorlevel 1 (
  echo.
  echo Aplikasi gagal dijalankan. Periksa instalasi Python dan dependensi.
  pause
)
