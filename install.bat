@echo off
set "APP_VERSION=unknown"
if exist "%~dp0helpai_version.py" (
    for /f "tokens=2 delims== " %%V in ('findstr /r "^__version__ *= *\".*\"" "%~dp0helpai_version.py"') do set "APP_VERSION=%%~V"
)
title HelpAI Installer v%APP_VERSION%
echo ============================================
echo   HelpAI v%APP_VERSION% — Windows Installer
echo ============================================
echo.
echo This will install HelpAI on your computer.
echo.

:: ── Check admin rights (needed for Program Files install) ──
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo [*] Requesting administrator privileges...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

:: ── Configuration ──
set "APP_NAME=HelpAI"
set "INSTALL_DIR=%ProgramFiles%\HelpAI"
set "DESKTOP=%USERPROFILE%\Desktop"
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

:: ── Find source folder (where this installer is) ──
set "SOURCE_DIR=%~dp0"

:: Check HelpAI.exe exists in source
if not exist "%SOURCE_DIR%HelpAI.exe" (
    echo [ERROR] HelpAI.exe not found in %SOURCE_DIR%
    echo         Run build.bat or build_exe.py first to create the executable.
    pause
    exit /b 1
)

:: ── Install ──
echo [*] Installing to: %INSTALL_DIR%
if exist "%INSTALL_DIR%" (
    echo [*] Removing previous installation...
    rmdir /s /q "%INSTALL_DIR%"
)

echo [*] Copying files...
xcopy "%SOURCE_DIR%*" "%INSTALL_DIR%\" /e /i /q /y >nul
if %errorlevel% neq 0 (
    echo [ERROR] Failed to copy files.
    pause
    exit /b 1
)

:: ── Create Desktop Shortcut ──
echo [*] Creating desktop shortcut...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut('%DESKTOP%\HelpAI.lnk'); $lnk.TargetPath = '%INSTALL_DIR%\HelpAI.exe'; $lnk.WorkingDirectory = '%INSTALL_DIR%'; $lnk.Description = 'HelpAI - Internal QA and Training Overlay'; $lnk.Save()"

:: ── Create Start Menu Shortcut ──
echo [*] Creating Start Menu shortcut...
powershell -NoProfile -Command "$ws = New-Object -ComObject WScript.Shell; $lnk = $ws.CreateShortcut('%START_MENU%\HelpAI.lnk'); $lnk.TargetPath = '%INSTALL_DIR%\HelpAI.exe'; $lnk.WorkingDirectory = '%INSTALL_DIR%'; $lnk.Description = 'HelpAI - Internal QA and Training Overlay'; $lnk.Save()"

:: ── Add to Apps & Features (registry) ──
echo [*] Registering in Windows Apps...
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" ^
    /v "DisplayName" /t REG_SZ /d "HelpAI" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" ^
    /v "InstallLocation" /t REG_SZ /d "%INSTALL_DIR%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" ^
    /v "UninstallString" /t REG_SZ /d "%INSTALL_DIR%\uninstall.bat" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" ^
    /v "Publisher" /t REG_SZ /d "HelpAI Team" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" ^
    /v "DisplayVersion" /t REG_SZ /d "%APP_VERSION%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" ^
    /v "NoModify" /t REG_DWORD /d 1 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" ^
    /v "NoRepair" /t REG_DWORD /d 1 /f >nul

echo.
echo ============================================
echo   Installation Complete!
echo ============================================
echo.
echo   Version:   %APP_VERSION%
echo   Location:  %INSTALL_DIR%
echo   Shortcut:  Desktop ^& Start Menu
echo.
echo   Launch HelpAI from your Desktop or
echo   Start Menu.
echo.
pause
