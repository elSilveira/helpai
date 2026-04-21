@echo off
title HelpAI Uninstaller
echo ============================================
echo   HelpAI — Uninstaller
echo ============================================
echo.

:: Check admin rights
net session >nul 2>&1
if %errorlevel% neq 0 (
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "INSTALL_DIR=%ProgramFiles%\HelpAI"
set "DESKTOP=%USERPROFILE%\Desktop"
set "START_MENU=%APPDATA%\Microsoft\Windows\Start Menu\Programs"

echo [*] Removing application files...
if exist "%INSTALL_DIR%" rmdir /s /q "%INSTALL_DIR%"

echo [*] Removing shortcuts...
if exist "%DESKTOP%\HelpAI.lnk" del "%DESKTOP%\HelpAI.lnk"
if exist "%START_MENU%\HelpAI.lnk" del "%START_MENU%\HelpAI.lnk"

echo [*] Removing registry entry...
reg delete "HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\HelpAI" /f >nul 2>&1

echo.
echo   HelpAI has been uninstalled.
echo.
pause
