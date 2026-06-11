@echo off
setlocal

set "TARGET=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\start_emi.vbs"

if exist "%TARGET%" (
    del /F /Q "%TARGET%"
    echo  [OK]  Emi removed from Windows startup.
) else (
    echo  [INFO]  Emi was not in the startup folder.
)

echo.
pause
endlocal
