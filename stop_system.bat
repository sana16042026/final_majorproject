@echo off
title Stop MPLADS System

REM Port of the web app (override by setting APP_PORT before running)
if "%APP_PORT%"=="" set APP_PORT=5000

echo Stopping the web server listening on port %APP_PORT%...
set FOUND=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%APP_PORT% " ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
    set FOUND=1
)
if "%FOUND%"=="1" (echo Web server stopped.) else (echo Nothing was running on port %APP_PORT%.)

REM The database is left running because other projects may use it.
REM To stop it too, uncomment the next line:
REM taskkill /F /IM mariadbd.exe /T 2>nul

timeout /t 2 >nul
