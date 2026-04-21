@echo off
setlocal

set "ROOT=%~dp0"
pushd "%ROOT%" >nul

set "APP_VERSION=unknown"
if exist "%ROOT%helpai_version.py" (
    for /f "tokens=2 delims== " %%V in ('findstr /r "^__version__ *= *\".*\"" "%ROOT%helpai_version.py"') do set "APP_VERSION=%%~V"
)

title HelpAI v%APP_VERSION% Build
echo ============================================
echo   HelpAI v%APP_VERSION% - Build
echo ============================================
echo.

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python 3.11+ was not found on PATH.
    popd >nul
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [*] Creating virtual environment...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to create virtual environment.
        popd >nul
        exit /b 1
    )
)

set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "PIP=%ROOT%.venv\Scripts\pip.exe"

echo [*] Installing build dependencies...
"%PIP%" install -q -r requirements.txt pyinstaller build
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install build dependencies.
    popd >nul
    exit /b 1
)

echo [*] Building Windows executable bundle...
"%PYTHON%" build_exe.py
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller build failed.
    popd >nul
    exit /b 1
)

if exist "dist\pip" (
    rmdir /s /q "dist\pip"
)
mkdir "dist\pip" >nul 2>&1

echo [*] Building pip wheel and source distribution...
"%PYTHON%" -m build --wheel --sdist --outdir dist\pip
if %errorlevel% neq 0 (
    echo [ERROR] pip package build failed.
    popd >nul
    exit /b 1
)

set "WHEEL_PATH="
set "SDIST_PATH="
for %%F in ("dist\pip\helpai-*.whl") do set "WHEEL_PATH=%%~fF"
for %%F in ("dist\pip\helpai-*.tar.gz") do set "SDIST_PATH=%%~fF"

echo.
echo ============================================
echo   Build Complete
echo ============================================
echo.
echo   EXE:   %ROOT%dist\HelpAI\HelpAI.exe
if defined WHEEL_PATH echo   WHEEL: %WHEEL_PATH%
if defined SDIST_PATH echo   SDIST: %SDIST_PATH%
echo.
if defined WHEEL_PATH echo   Install with: python -m pip install --user "%WHEEL_PATH%"
echo.

popd >nul
endlocal