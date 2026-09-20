@echo off
title HELIOS-L1 Space Weather Suite
cd /d "%~dp0"
echo ================================================================
echo  Starting HELIOS-L1: Space Weather ^& L1 Heliophysics Observatory
echo ================================================================

if exist "HELIOS-L1.exe" (
    echo [*] Launching standalone executable...
    start "" "HELIOS-L1.exe" %*
    exit /b 0
)

if exist "dist\HELIOS-L1\HELIOS-L1.exe" (
    echo [*] Launching built executable from dist\HELIOS-L1...
    start "" "dist\HELIOS-L1\HELIOS-L1.exe" %*
    exit /b 0
)

echo [*] Launching via Python runtime...
python run.py %*
if errorlevel 1 (
    echo.
    echo [!] Python execution encountered an error.
    pause
)
