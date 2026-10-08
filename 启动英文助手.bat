@echo off
cd /d "%~dp0"
python -c "import tkinter" >nul 2>nul
if errorlevel 1 (
    echo Python 3.10+ with Tkinter is required. See README.md.
    pause
    exit /b 1
)
python app.py
if errorlevel 1 pause
