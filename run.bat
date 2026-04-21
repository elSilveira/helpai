@echo off
set "APP_VERSION=unknown"
if exist "%~dp0config.py" (
    for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "$match = Select-String -Path '%~dp0config.py' -Pattern '^\s*APP_VERSION\s*=\s*\"([^\"]+)\"'; if ($match) { $match.Matches[0].Groups[1].Value } else { 'unknown' }"`) do set "APP_VERSION=%%V"
)
title HelpAI v%APP_VERSION% — Quick Run
echo ============================================
echo   HelpAI v%APP_VERSION% — Internal QA ^& Training Overlay
echo ============================================
echo.

:: Check Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] Python not found on PATH.
    echo     Checking common install locations...
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set "PYTHON=%LocalAppData%\Programs\Python\Python312\python.exe"
    ) else if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set "PYTHON=%LocalAppData%\Programs\Python\Python311\python.exe"
    ) else (
        echo [ERROR] Python 3.11+ is required. Install from https://python.org
        pause
        exit /b 1
    )
) else (
    set "PYTHON=python"
)

echo [*] Using: %PYTHON%

:: Create venv if missing
if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    %PYTHON% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create venv.
        pause
        exit /b 1
    )
)

:: Activate and install deps
echo [*] Installing dependencies...
.venv\Scripts\pip.exe install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    pause
    exit /b 1
)

echo [*] Launching HelpAI...
echo.
.venv\Scripts\python.exe launcher.py
pause
