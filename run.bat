@echo off
setlocal

set "ROOT=%~dp0"
pushd "%ROOT%" >nul

set "APP_VERSION=unknown"
if exist "%ROOT%helpai_version.py" (
    for /f "tokens=2 delims== " %%V in ('findstr /r "^__version__ *= *\".*\"" "%ROOT%helpai_version.py"') do set "APP_VERSION=%%~V"
)

title HelpAI v%APP_VERSION% - Python Run
echo ============================================
echo   HelpAI v%APP_VERSION% - Python Run
echo ============================================
echo.

set "PYTHON_EXE="
set "PYTHON_ARGS="
where py >nul 2>&1
if %errorlevel% equ 0 (
    py -3.12 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=py"
        set "PYTHON_ARGS=-3.12"
    )
    if not defined PYTHON_EXE (
        py -3.11 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if %errorlevel% equ 0 (
            set "PYTHON_EXE=py"
            set "PYTHON_ARGS=-3.11"
        )
    )
)

if not defined PYTHON_EXE (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
        if %errorlevel% equ 0 set "PYTHON_EXE=python"
    )
)

if not defined PYTHON_EXE (
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
        set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
    ) else if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python 3.11 or newer was not found.
    echo         Install Python from https://python.org and enable "Add python.exe to PATH".
    popd >nul
    pause
    exit /b 1
)

echo [*] Using Python: "%PYTHON_EXE%" %PYTHON_ARGS%

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    "%PYTHON_EXE%" %PYTHON_ARGS% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        popd >nul
        pause
        exit /b 1
    )
)

set "VENV_PYTHON=%ROOT%.venv\Scripts\python.exe"
set "VENV_PIP=%ROOT%.venv\Scripts\pip.exe"

"%VENV_PYTHON%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Existing .venv is using an older Python.
    echo         Delete the .venv folder, then run this file again so it can rebuild with Python 3.11+.
    popd >nul
    pause
    exit /b 1
)

echo [*] Installing dependencies...
"%VENV_PIP%" install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install dependencies.
    popd >nul
    pause
    exit /b 1
)

echo [*] Launching HelpAI from source...
echo.
"%VENV_PYTHON%" launcher.py
set "EXIT_CODE=%errorlevel%"

popd >nul
pause
exit /b %EXIT_CODE%
