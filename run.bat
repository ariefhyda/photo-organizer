@echo off
REM Launcher untuk Photo Organizer
cd /d "%~dp0"
python -m photo_organizer
if errorlevel 1 pause
