@echo off
REM ============================================================
REM  Build Photo Organizer (portable, Windows x64) -- onedir
REM ============================================================
cd /d "%~dp0"

echo [1/2] Memasang dependensi build...
pip install -r requirements.txt pyinstaller

REM Catatan: peta tertanam memakai QtWebEngine, jadi QtWebEngine/QtQml/QtQuick
REM TIDAK boleh dikecualikan. Build memakai --onedir (folder) agar andal &
REM cepat start. Hasil portable: seluruh folder dist\PhotoOrganizer\.
echo [2/2] Membangun PhotoOrganizer (onedir) ...
pyinstaller --noconfirm --onedir --windowed --name PhotoOrganizer ^
  --icon "assets/icon.ico" ^
  --add-data "models;models" ^
  --add-data "assets;assets" ^
  --exclude-module PySide6.Qt3DCore ^
  --exclude-module tkinter ^
  --exclude-module matplotlib ^
  app.py

echo.
echo Selesai. Aplikasi portable ada di folder:  dist\PhotoOrganizer\
echo Jalankan:  dist\PhotoOrganizer\PhotoOrganizer.exe
pause
