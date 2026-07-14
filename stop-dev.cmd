@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\stop-dev.ps1"
if errorlevel 1 (
    echo.
    echo Stop failed. Review the local development logs and press any key to close.
    pause >nul
    exit /b 1
)
