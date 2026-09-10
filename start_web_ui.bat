@echo off
REM Rocketlane Clone Tool - Web UI Startup Script (Windows)

echo ================================================================================
echo ROCKETLANE CLONE TOOL - WEB UI LAUNCHER
echo ================================================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python is not installed
    echo Please install Python 3.9 or later from https://python.org
    pause
    exit /b 1
)

echo Python found
echo.

REM Check if Flask is installed
python -c "import flask" >nul 2>&1
if %errorlevel% neq 0 (
    echo Flask not found. Installing dependencies...
    echo.
    pip install -r requirements.txt
    echo.
)

echo Dependencies installed
echo.
echo Starting web server...
echo.
echo ================================================================================
echo.
echo Web UI will be available at: http://localhost:5000
echo.
echo Press Ctrl+C to stop the server
echo.
echo ================================================================================
echo.

REM Start the web UI
python web_ui.py

pause
