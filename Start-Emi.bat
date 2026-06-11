@echo off
title Emi Assistant Launcher
color 0B

echo.
echo ============================================
echo     Emi Assistant - Starting up...
echo ============================================
echo.

:: Check Ollama
where ollama >nul 2>&1
if errorlevel 1 (
    color 0C
    echo [ERROR] Ollama not found! Please install it.
    pause
    exit /b 1
)

:: Check Python
where python >nul 2>&1
if errorlevel 1 (
    color 0C
    echo [ERROR] Python not found!
    pause
    exit /b 1
)

echo [OK] Dependencies found.

:: Start Ollama
tasklist /fi "imagename eq ollama.exe" 2>nul | findstr /i "ollama.exe" >nul
if errorlevel 1 (
    echo [START] Starting Ollama server in background...
    start /min ollama serve
    timeout /t 5 /nobreak >nul
) else (
    echo [OK] Ollama is already running.
)

echo.
echo [LAUNCH] Starting Emi...
echo ============================================
echo.

:: Run Python and keep window open even if it crashes
python launch.py

echo.
echo ============================================
echo Emi has stopped.
echo Press any key to close...
pause >nul