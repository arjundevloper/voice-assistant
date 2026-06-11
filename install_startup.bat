@echo off
setlocal

echo.
echo  ╔══════════════════════════════════════╗
echo  ║   Emi Assistant — Startup Installer  ║
echo  ╚══════════════════════════════════════╝
echo.

set "SCRIPT_DIR=%~dp0"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "TARGET=%STARTUP%\start_emi.vbs"

:: Copy the VBS launcher to the Windows Startup folder
copy /Y "%SCRIPT_DIR%start_emi.vbs" "%TARGET%" >nul 2>&1

if exist "%TARGET%" (
    echo  [OK]  Emi will now start automatically with Windows.
    echo.
    echo  Startup folder: %STARTUP%
    echo  To remove:  run uninstall_startup.bat
) else (
    echo  [ERROR]  Could not write to Startup folder.
    echo           Try running this file as Administrator.
)

echo.
pause
endlocal
