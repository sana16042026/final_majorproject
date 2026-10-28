@echo off
title AI-Powered MPLADS Road Monitoring System
color 0b

echo =====================================================================
echo    AI-Powered MPLADS Road Construction Monitoring System (v1.0)
echo =====================================================================
echo.
echo Starting Database, AI Models, and Web Server...
echo Please wait a moment...
echo.

REM Run from the folder this file lives in (works on any machine)
cd /d "%~dp0"

REM Use the project's virtual environment if one exists
if exist "venv\Scripts\activate.bat" call "venv\Scripts\activate.bat"
if exist ".venv\Scripts\activate.bat" call ".venv\Scripts\activate.bat"

python run.py

pause
