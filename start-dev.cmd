@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\start-dev.ps1"
if errorlevel 1 (
    echo.
    echo Startup failed. Review the local development logs and press any key to close.
    pause >nul
    exit /b 1
)
